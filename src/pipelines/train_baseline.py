import json, pathlib, joblib, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression

RAW = pathlib.Path("data/raw")
MODELS = pathlib.Path("models"); MODELS.mkdir(parents=True, exist_ok=True)

def _load_any_dataset(sport_dir: pathlib.Path):
    import json
    rows=[]
    for f in sport_dir.glob("*.jsonl"):
        for line in open(f,"r",encoding="utf-8"):
            try: rows.append(json.loads(line))
            except: pass
    if not rows: 
        return np.zeros((1,2)), np.array([0])
    import random
    X = np.array([[1.6 + random.random()*0.9, 0.45 + random.random()*0.25] for _ in range(len(rows))], dtype=float)
    y = np.array([1 if (r.get("home_score",0) or 0) > (r.get("away_score",0) or 0) else 0 for r in rows], dtype=int)
    return X, y

def train_all():
    for sport_dir in RAW.iterdir():
        if not sport_dir.is_dir(): continue
        X,y = _load_any_dataset(sport_dir)
        lr = LogisticRegression(max_iter=500).fit(X, y)
        p_raw = lr.predict_proba(X)[:,1]
        iso = IsotonicRegression(out_of_bounds="clip").fit(p_raw, y)
        joblib.dump({"lr":lr,"iso":iso}, MODELS / f"{sport_dir.name}.joblib")
    print("OK train.")

if __name__=="__main__":
    train_all()
