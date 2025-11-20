# src/ml/utils.py
import numpy as np
import pandas as pd

def prepare_features_from_df(df: pd.DataFrame):
    X = pd.DataFrame()
    X["home_goals"] = df.get("home_goals", 0).fillna(0).astype(float)
    X["away_goals"] = df.get("away_goals", 0).fillna(0).astype(float)
    X["goal_diff"] = X["home_goals"] - X["away_goals"]
    X["odds_home"] = df.get("odds_home", 2.0).fillna(2.0).astype(float)
    X["odds_draw"] = df.get("odds_draw", 3.0).fillna(3.0).astype(float)
    X["odds_away"] = df.get("odds_away", 2.5).fillna(2.5).astype(float)

    def enc(o):
        o = str(o).lower()
        if o in ("home", "1"):
            return 0
        if o in ("draw", "x"):
            return 1
        return 2

    if "outcome" in df:
        y = df["outcome"].apply(enc).astype(int)
    else:
        y = pd.Series([pd.NA] * len(df)).astype("Int64")

    return X, y

def multiclass_brier(y_true_onehot, y_prob):
    return float(((y_prob - y_true_onehot) ** 2).sum(axis=1).mean())
