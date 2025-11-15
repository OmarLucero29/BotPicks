# scripts/backtest.py
import os, sys, joblib
import pandas as pd
import numpy as np
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ml.utils import prepare_features_from_df

load_dotenv()
MODEL_PATH = "models/model_baseline.pkl"

def read_local():
    if os.path.exists("data/sample_matches.csv"):
        return pd.read_csv("data/sample_matches.csv")
    return pd.DataFrame()

def backtest():
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError("No hay modelo entrenado. Ejecuta src/ml/train_baseline.py")
    df = read_local()
    if df.empty:
        raise RuntimeError("No hay datos para backtest")
    arte = joblib.load(MODEL_PATH)
    model = arte["model"]
    feature_cols = arte["feature_cols"]
    X, y = prepare_features_from_df(df)
    probs = model.predict_proba(X[feature_cols])
    # simple logloss
    import math
    ll = -sum(math.log(max(1e-15, probs[i][y.iloc[i]])) for i in range(len(y))) / len(y)
    print("LogLoss:", ll)
if __name__ == '__main__':
    backtest()
