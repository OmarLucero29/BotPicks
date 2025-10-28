"""
Ingesta histórica V1.0 EXTENDIDA (gratis).
"""
import csv, io, json, os, pathlib, requests
from datetime import datetime
from src.common.http import HttpClient, save_jsonl

ROOT = pathlib.Path("data/raw"); ROOT.mkdir(parents=True, exist_ok=True)

def ingest_nba(seasons=5):
    cli = HttpClient("https://www.balldontlie.io/api/v1")
    rows=[]
    for season in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        page=1
        while True:
            js = cli.get("games", params={"seasons[]":season,"per_page":100,"page":page}).json()
            for g in js.get("data", []):
                rows.append({
                    "date": g["date"], "league":"NBA",
                    "home": g["home_team"]["full_name"], "away": g["visitor_team"]["full_name"],
                    "home_score": g["home_team_score"], "away_score": g["visitor_team_score"]
                })
            if js.get("meta",{}).get("next_page") is None: break
            page += 1
    save_jsonl("data/raw/basketball/nba_games.jsonl", rows)

def ingest_mlb(seasons=5):
    cli = HttpClient("https://statsapi.mlb.com/api")
    rows=[]
    for year in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        js = cli.get(f"v1/schedule?sportId=1&season={year}").json()
        for d in js.get("dates", []):
            for g in d.get("games", []):
                rows.append({
                    "date": g.get("gameDate"), "league":"MLB",
                    "home": g["teams"]["home"]["team"]["name"], "away": g["teams"]["away"]["team"]["name"],
                    "home_score": g["teams"]["home"].get("score"), "away_score": g["teams"]["away"].get("score"),
                    "status": g.get("status",{}).get("detailedState")
                })
    save_jsonl("data/raw/baseball/mlb_games.jsonl", rows)

def ingest_nhl(seasons=5):
    cli = HttpClient("https://statsapi.web.nhl.com/api/v1")
    rows=[]
    for year in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        js = cli.get(f"schedule?season={year-1}{year}").json()
        for d in js.get("dates", []):
            for g in d.get("games", []):
                rows.append({
                    "date": g.get("gameDate"), "league":"NHL",
                    "home": g["teams"]["home"]["team"]["name"], "away": g["teams"]["away"]["team"]["name"],
                    "home_score": g["teams"]["home"].get("score"), "away_score": g["teams"]["away"].get("score")
                })
    save_jsonl("data/raw/hockey/nhl_games.jsonl", rows)

def ingest_f1(seasons=10):
    cli = HttpClient("https://ergast.com/api/f1"); rows=[]
    for year in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        res = cli.get(f"{year}.json").json()
        for race in res["MRData"]["RaceTable"].get("Races", []):
            rows.append({
                "date": race.get("date"), "league":"F1",
                "circuit": race.get("Circuit",{}).get("circuitName"),
                "country": race.get("Circuit",{}).get("Location",{}).get("country"),
                "round": race.get("round")
            })
    save_jsonl("data/raw/f1/f1_races.jsonl", rows)

def _read_csv(url: str):
    r = requests.get(url, timeout=60); r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8"))))

def ingest_nfl(seasons=5):
    base = "https://raw.githubusercontent.com/nflverse/nflfastR-data/master/data/games/"
    rows=[]; current=datetime.utcnow().year-1
    for year in range(current, current-seasons, -1):
        try:
            recs = _read_csv(f"{base}games_{year}.csv")
        except Exception:
            recs = [r for r in _read_csv(f"{base}games.csv") if r.get("season") and int(r["season"])==year]
        for g in recs:
            rows.append({
                "date": g.get("game_date"), "league":"NFL",
                "home": g.get("home_team"), "away": g.get("away_team"),
                "home_score": g.get("home_score"), "away_score": g.get("away_score")
            })
    save_jsonl("data/raw/football/nfl_games.jsonl", rows)

def ingest_tennis(years=5):
    base = "https://raw.githubusercontent.com/JeffSackmann/"
    tours = [("ATP","tennis_atp"), ("WTA","tennis_wta")]
    rows=[]; current=datetime.utcnow().year-1
    for tour_name, repo in tours:
        for y in range(current, current-years, -1):
            url = f"{base}{repo}/master/{repo.split('_')[1]}_matches_{y}.csv"
            try:
                r = requests.get(url, timeout=60); r.raise_for_status()
            except Exception:
                continue
            for rec in csv.DictReader(io.StringIO(r.content.decode("utf-8",errors="ignore"))):
                rows.append({
                    "date": rec.get("tourney_date"), "tour": tour_name,
                    "winner": rec.get("winner_name"), "loser": rec.get("loser_name"),
                    "surface": rec.get("surface"), "score": rec.get("score")
                })
    save_jsonl("data/raw/tennis/tennis_matches.jsonl", rows)

_SOCCER_MAP = {
    "premier": ("england","premier-league"),
    "laliga": ("spain","la-liga"),
    "bundesliga": ("germany","bundesliga"),
    "seriea": ("italy","serie-a"),
    "ligue1": ("france","ligue-1"),
    "primeira": ("portugal","primeira-liga"),
    "ucl": ("europe-champions-league","uefa-champions-league"),
    "ligamx": ("mexico","liga-mx"),
    "mls": ("usa","major-league-soccer"),
    "libertadores": ("south-america-copa-libertadores","copa-libertadores")
}
def ingest_soccer(seasons=5):
    base = "https://raw.githubusercontent.com/openfootball"
    rows=[]; current=datetime.utcnow().year-1
    for code,(org,repo) in _SOCCER_MAP.items():
        for y in range(current, current-seasons, -1):
            url = f"{base}/{org}/master/{repo}/{y-1}-{y}.json"
            try:
                r = requests.get(url, timeout=60); r.raise_for_status()
                js = r.json()
            except Exception:
                continue
            for m in js.get("matches", []):
                rows.append({
                    "date": m.get("date"), "league": code.upper(),
                    "home": m.get("team1"), "away": m.get("team2"),
                    "home_score": m.get("score1"), "away_score": m.get("score2")
                })
    save_jsonl("data/raw/soccer/soccer_matches.jsonl", rows)

def ingest_esports_pandascore(years=2):
    base = "https://api.pandascore.co"
    token = os.getenv("PANDASCORE_TOKEN")
    if not token:
        print("WARN: PANDASCORE_TOKEN no configurado, saltando e-Sports."); 
        save_jsonl("data/raw/esports/esports.jsonl", []); 
        return
    headers={"Authorization": f"Bearer {token}"}
    titles = ["lol","cs2","dota2","valorant"]
    rows=[]
    for t in titles:
        page=1
        while page<=3:
            url = f"{base}/{t}/matches?page={page}&per_page=100&sort=begin_at"
            r = requests.get(url, headers=headers, timeout=45)
            if r.status_code>=400: break
            data = r.json()
            if not data: break
            for m in data:
                rows.append({
                    "title": t.upper(),
                    "date": m.get("begin_at"),
                    "league": (m.get("league") or {}).get("name"),
                    "tournament": (m.get("tournament") or {}).get("name"),
                    "op1": (m.get("opponents")[0]["opponent"]["name"] if m.get("opponents") else None),
                    "op2": (m.get("opponents")[1]["opponent"]["name"] if m.get("opponents") and len(m["opponents"])>1 else None),
                    "status": m.get("status"), "winner_id": m.get("winner_id")
                })
            page += 1
    save_jsonl("data/raw/esports/pandascore_matches.jsonl", rows)

def ingest_efutbol_stub(): save_jsonl("data/raw/efutbol/efutbol.jsonl", [])
def ingest_pingpong_stub(): save_jsonl("data/raw/pingpong/pingpong.jsonl", [])
def ingest_mma_stub(): save_jsonl("data/raw/mma/mma.jsonl", [])
def ingest_box_stub(): save_jsonl("data/raw/boxing/boxing.jsonl", [])
def ingest_fantasy(): 
    from datetime import datetime
    save_jsonl("data/raw/fantasy_soccer/fantasy.jsonl", [{"date":datetime.utcnow().isoformat(),"mode":"fantasy"}])

def ingest_all(years=3):
    ROOT.mkdir(parents=True, exist_ok=True)
    ingest_nba(seasons=years)
    ingest_mlb(seasons=years)
    ingest_nhl(seasons=years)
    ingest_f1(seasons=years*2)
    ingest_nfl(seasons=years)
    ingest_tennis(years=years)
    ingest_soccer(seasons=years)
    ingest_esports_pandascore(years=years)
    ingest_efutbol_stub(); ingest_pingpong_stub(); ingest_mma_stub(); ingest_box_stub(); ingest_fantasy()
    print("OK ingest EXTENDED.")

if __name__=="__main__":
    ingest_all(years=3)
