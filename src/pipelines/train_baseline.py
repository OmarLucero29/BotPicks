import json, pathlib, joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score

DATA_DIR=pathlib.Path('data/raw'); MODEL_DIR=pathlib.Path('models'); MODEL_DIR.mkdir(parents=True, exist_ok=True)

def load_df():
    rows=[]
    for f in DATA_DIR.rglob('*.jsonl'):
        with open(f,'r',encoding='utf-8') as fh:
            for line in fh:
                try: rows.append(json.loads(line))
                except: pass
    return pd.DataFrame(rows)

def train_all():
    df=load_df()
    if df.empty or 'home_score' not in df or 'away_score' not in df:
        joblib.dump({'status':'dummy','msg':'no data'}, MODEL_DIR/'dummy.pkl'); print('Dummy model'); return
    df=df.dropna(subset=['home_score','away_score'])
    df['label']=(df['home_score']>df['away_score']).astype(int)
    if df['label'].nunique()<2:
        joblib.dump({'status':'dummy','msg':'single class'}, MODEL_DIR/'dummy.pkl'); print('Dummy model single class'); return
    X=(df['home_score']-df['away_score']).to_numpy().reshape(-1,1); y=df['label'].to_numpy()
    lr=LogisticRegression(max_iter=500).fit(X,y)
    preds=lr.predict_proba(X)[:,1]
    metrics={'brier':float(brier_score_loss(y,preds)),'logloss':float(log_loss(y,preds)),'acc':float((preds>0.5).mean())}
    joblib.dump({'model':lr,'metrics':metrics}, MODEL_DIR/'baseline.pkl'); print('Model saved',metrics)

if __name__=='__main__': train_all()
