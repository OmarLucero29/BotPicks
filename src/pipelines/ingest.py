import time, pathlib
from datetime import datetime
from src.common.http import HttpClient, save_jsonl

ROOT=pathlib.Path('data/raw')
def ingest_nba(seasons=3):
    cli=HttpClient('https://www.balldontlie.io/api/v1'); rows=[]
    yr=datetime.utcnow().year-1
    for season in range(yr, yr-seasons, -1):
        page=1
        while True:
            js=cli.get_json('games', params={'seasons[]':season,'per_page':100,'page':page})
            if not js or 'data' not in js: break
            for g in js['data']:
                rows.append({
                    'date': g.get('date'), 'league':'NBA',
                    'home': (g.get('home_team') or {}).get('full_name'),
                    'away': (g.get('visitor_team') or {}).get('full_name'),
                    'home_score': g.get('home_team_score'),
                    'away_score': g.get('visitor_team_score')
                })
            if js.get('meta',{}).get('next_page') is None: break
            page+=1; time.sleep(0.25)
    save_jsonl('data/raw/basketball/nba.jsonl', rows)

def ingest_all(years=3):
    ROOT.mkdir(parents=True, exist_ok=True)
    try: ingest_nba(years)
    except Exception as e: print('WARN ingest nba:', e)
    print('OK ingest.')

if __name__=='__main__': ingest_all(3)
