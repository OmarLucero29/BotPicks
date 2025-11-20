# src/ml/train_baseline.py
from __future__ import annotations
import os
import sys
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import lightgbm as lgb
from lightgbm import early_stopping, log_evaluation
from sklearn.metrics import accuracy_score, log_loss
from dotenv import load_dotenv

# Hacer visible la carpeta raíz para imports tipo src.*
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ml.utils import prepare_features_from_df, multiclass_brier
from supabase import create_client

load_dotenv()

MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "model_baseline.pkl")


def read_local_sample():
    path = "data/sample_matches.csv"
    if os.path.exists(path):
        return pd.read_csv(path, parse_dates=["fecha"])
    return pd.DataFrame()


def read_historical_from_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        sb = create_client(url, key)
        res = sb.table("historical_matches").select("*").execute()
        rows = res.data or []
        if len(rows) == 0:
            return None
        return pd.DataFrame(rows)
    except Exception:
        return None


def safe_split(X, y):
    """
    Versión segura de train/test split:
    - No usa stratify si hay pocas muestras o clases con 1 solo valor.
    - Sobre datasets muy pequeños usa test_size=0.5.
    """
    try:
        vc = y.value_counts()
        min_count = int(vc.min()) if not vc.empty else 0
        n_classes = len(vc)
    except Exception:
        min_count = 0
        n_classes = 0

    n = len(y)
    if n < 4 or min_count < 2 or n_classes < 2:
        test_size = 0.5 if n < 10 else 0.2
        return train_test_split(X, y, test_size=test_size, random_state=42, shuffle=True)
    return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)


def train():
    # Cargar datos (Supabase o sample local)
    df = read_historical_from_supabase()
    if df is None or df.empty:
        print("No hay datos históricos en Supabase, usando data/sample_matches.csv")
        df = read_local_sample()

    if df.empty:
        raise RuntimeError("No hay datos para entrenar. Revisa data/sample_matches.csv")

    # Features y etiquetas
    X, y = prepare_features_from_df(df)
    if X.empty or (hasattr(y, "isna") and y.isna().all()):
        raise RuntimeError("Dataset inválido: no existen labels válidos en outcome.")

    # Split robusto
    X_train, X_val, y_train, y_val = safe_split(X, y)

    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=300,
        learning_rate=0.05,
        random_state=42,
    )

    # Si y_train no contiene todas las clases presentes en y_val => evitar eval_set
    classes_train = set(np.unique(y_train))
    classes_val = set(np.unique(y_val))
    use_eval = classes_val.issubset(classes_train) and len(X_val) > 0

    if use_eval:
        # usar callbacks compatibles
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[early_stopping(stopping_rounds=30), log_evaluation(period=0)],
        )
    else:
        # dataset pequeño / train no tiene todas las clases -> entrenar sin eval_set
        print("Advertencia: y_train no contiene todas las clases del conjunto de validación o no hay validación.")
        print("Entrenando sin eval_set (sin early stopping).")
        model.fit(X_train, y_train)

    # Predicciones y métricas (si X_val no está vacío)
    if len(X_val) > 0:
        y_pred = model.predict(X_val)
        y_prob_full = model.predict_proba(X_val)

        # model.classes_ contiene el orden de las columnas en y_prob_full
        model_classes = list(model.classes_)
        # clases presentes en y_val (enteros)
        val_classes = sorted(list(set(int(x) for x in y_val)))

        # índices de las columnas de probabilidad que corresponden a las clases en validation
        idxs = [model_classes.index(c) for c in val_classes if c in model_classes]

        if len(idxs) == 0:
            print("No hay coincidencia de clases entre modelo y y_val; omitiendo métricas.")
        else:
            # seleccionar solo las columnas pertinentes en el orden de val_classes
            y_prob = y_prob_full[:, idxs]

            # calcular accuracy (usa predicciones mapeadas a enteros)
            acc = accuracy_score(y_val, y_pred)

            # log_loss: pasar labels explícitos que correspondan al orden de columnas usadas
            ll = log_loss(y_val, y_prob, labels=val_classes)

            # construir one-hot con tamaño igual al número de clases en validación
            y_onehot = np.zeros((len(y_val), len(val_classes)))
            lab_to_idx = {lab: i for i, lab in enumerate(val_classes)}
            for i, lab in enumerate(y_val):
                y_onehot[i, lab_to_idx[int(lab)]] = 1.0

            brier = multiclass_brier(y_onehot, y_prob)

            print("\n=== MÉTRICAS DEL MODELO ===")
            print(f"Accuracy:          {acc:.4f}")
            print(f"LogLoss:           {ll:.4f}")
            print(f"Multiclass Brier:  {brier:.6f}")
    else:
        print("No hay conjunto de validación disponible para métricas.")

    # Guardar modelo
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump({"model": model, "feature_cols": list(X.columns)}, MODEL_PATH)
    print("\nModelo guardado en:", MODEL_PATH)


if __name__ == "__main__":
    train()
