import os, json, random
from datetime import datetime
from src.common.stake_kelly import KellyConfig, compute_kelly
from src.common.sheets_io import write_rows

def dummy_picks(n=5):
    picks=[]
    for i in range(n):
        p=round(random.uniform(0.45,0.65),3); dec=round(random.uniform(1.5,2.2),2)
        picks.append({'deporte':'basketball','liga':'NBA','partido':f'TeamA vs TeamB #{i+1}','mercado':'Moneyline','pick':'TeamA','prob':p,'odds_dec':dec})
    return picks

if __name__=='__main__':
    cfg=json.load(open('config/menu_config.json','r',encoding='utf-8'))
    bankroll=float(os.getenv('DEFAULT_BANKROLL', cfg.get('bankroll',500)))
    fraction=float(os.getenv('DEFAULT_KELLY_FRACTION', 0.25))
    top=int(os.getenv('DEFAULT_TOP_PICKS', cfg.get('top_picks',5)))
    kc=KellyConfig(bankroll, fraction, cfg.get('stake_min',0.01), cfg.get('stake_max',0.10))
    rows=[]
    for pk in dummy_picks(top):
        stake=compute_kelly(pk['prob'], pk['odds_dec'], kc)
        rows.append([datetime.utcnow().isoformat(), pk['deporte'], pk['liga'], pk['partido'], pk['mercado'], pk['pick'], f"{pk['odds_dec']} ({int(pk['prob']*100)}%)", stake])
    write_rows(os.getenv('GSHEET_ID'), os.getenv('GSHEET_PICKS_TAB','PICKS'), rows)
    print('Published', len(rows))
