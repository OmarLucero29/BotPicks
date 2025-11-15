from __future__ import annotations

import os
import sys
import uuid
import joblib
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ml.utils import prepare_features_from_df
from src.utils.kelly import kelly_fraction

try:
    from supabase import create_client
except Exception:
    create_client = None

load_dotenv()

MODEL_PATH = "models/model_baseline.pkl"


def read_local_upcoming():
    path = "data/next_events.csv"
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def expected_value(prob, odds):
    return (prob * (odds - 1)) - (1 - prob)


def main(ev_threshold=0.0, kelly_frac=0.25, dry_run=False):

    if not os.path.exists(MODEL_PATH):
        raise RuntimeError("No hay modelo entrenado. Ejecuta src/ml/train_baseline.py primero.")

    df = read_local_upcoming()
    if df.empty:
        print("No hay eventos próximos en data/next_events.csv")
        return []

    arte = joblib.load(MODEL_PATH)
    model = arte["model"]
    feature_cols = arte["feature_cols"]

    X = pd.DataFrame()
    X["home_goals"] = df.get("home_goals", 0).fillna(0).astype(float)
    X["away_goals"] = df.get("away_goals", 0).fillna(0).astype(float)
    X["goal_diff"] = X["home_goals"] - X["away_goals"]
    X["odds_home"] = df["odds_home"].astype(float)
    X["odds_draw"] = df["odds_draw"].astype(float)
    X["odds_away"] = df["odds_away"].astype(float)

    for c in feature_cols:
        if c not in X.columns:
            X[c] = 0.0

    probs = model.predict_proba(X[feature_cols])

    sb = None
    if create_client and os.getenv("SUPABASE_URL"):
        try:
            sb = create_client(
                os.getenv("SUPABASE_URL"),
                os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            )
        except Exception:
            sb = None

    picks = []

    for i, row in df.iterrows():
        ph, pd_, pa = probs[i]

        evs = {
            "home": expected_value(ph, float(row["odds_home"])),
            "draw": expected_value(pd_, float(row["odds_draw"])),
            "away": expected_value(pa, float(row["odds_away"])),
        }

        side = max(evs, key=evs.get)
        ev_val = evs[side]

        if ev_val < ev_threshold:
            continue

        if side == "home":
            prob, odds = ph, float(row["odds_home"])
        elif side == "draw":
            prob, odds = pd_, float(row["odds_draw"])
        else:
            prob, odds = pa, float(row["odds_away"])

        stake_pct = round(kelly_fraction(prob, odds, frac=kelly_frac) * 100, 2)
        stake_pct = max(stake_pct, 0)

        pick = {
            "id": str(uuid.uuid4()),
            "fecha": datetime.now(timezone.utc).isoformat(),
            "deporte": row.get("deporte", "soccer"),
            "partido": f"{row.get('home_team')} vs {row.get('away_team')}",
            "mercado": "1X2",
            "pick": side,
            "cuota": odds,
            "stake": stake_pct,
        }

        if sb and not dry_run:
            try:
                sb.table("picks").insert(pick).execute()
            except Exception as e:
                print("Insert error:", e)
        else:
            print("PICK (dry-run):", pick)

        picks.append(pick)

    print("Picks creados:", len(picks))
    return picks


if __name__ == "__main__":
    ev = float(os.getenv("EV_THRESHOLD", "0.0"))
    kf = float(os.getenv("KELLY_FRACTION", "0.25"))
    main(ev_threshold=ev, kelly_frac=kf, dry_run=False)
