"""
Entrenamiento baseline robusto.
Evita fallos cuando hay una sola clase o pocos datos.
"""
import os, json, pathlib, joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score

DATA_DIR = pathlib.Path("data/raw")
MODEL_DIR = pathlib.Path("models"); MODEL_DIR.mkdir(parents=True, exist_ok=True)

def load_training_data():
    # Leer datasets básicos disponibles
    files = list(DATA_DIR.rglob("*.jsonl"))
    rows = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    rows.append(json.loads(line))
        except Exception:
            continue
    df = pd.DataFrame(rows)
    return df

def train_all():
    df = load_training_data()
    if df.empty:
        print("No data found for training. Creating dummy model.")
        dummy_path = MODEL_DIR / "dummy.pkl"
        joblib.dump({"status": "dummy", "msg": "no data"}, dummy_path)
        return

    # Simulación simple: usamos home_score y away_score si existen
    if "home_score" not in df.columns or "away_score" not in df.columns:
        print("No valid score columns found, creating dummy model.")
        joblib.dump({"status": "dummy", "msg": "no valid columns"}, MODEL_DIR / "dummy.pkl")
        return

    df = df.dropna(subset=["home_score", "away_score"])
    df["label"] = (df["home_score"] > df["away_score"]).astype(int)
    if df["label"].nunique() < 2:
        print("Only one class present in training data. Creating dummy model.")
        joblib.dump({"status": "dummy", "msg": "single class"}, MODEL_DIR / "dummy.pkl")
        return

    # Features simples
    X = (df["home_score"] - df["away_score"]).to_numpy().reshape(-1,1)
    y = df["label"].to_numpy()

    lr = LogisticRegression(max_iter=500)
    lr.fit(X, y)

    preds = lr.predict_proba(X)[:, 1]
    metrics = {
        "brier": float(brier_score_loss(y, preds)),
        "logloss": float(log_loss(y, preds)),
        "acc": float(accuracy_score(y, (preds>0.5).astype(int))),
        "n": int(len(y))
    }

    model_path = MODEL_DIR / "baseline.pkl"
    joblib.dump({"model": lr, "metrics": metrics}, model_path)
    print("Model trained and saved:", model_path)
    print("Metrics:", metrics)

if __name__ == "__main__":
    train_all()
