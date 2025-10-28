"""Ingesta EXTENDIDA con fallbacks robustos"""
import csv, io, os, pathlib, time, requests
from datetime import datetime
from src.common.http import HttpClient, save_jsonl

ROOT = pathlib.Path("data/raw"); ROOT.mkdir(parents=True, exist_ok=True)

def ingest_nba(seasons=5):
    cli = HttpClient("https://www.balldontlie.io/api/v1")
    rows=[]
    for season in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        page=1
        while True:
            js = cli.get_json("games", params={"seasons[]":season,"per_page":100,"page":page})
            if not js or "data" not in js:
                break
            for g in js.get("data", []):
                rows.append({
                    "date": g.get("date"), "league":"NBA",
                    "home": (g.get("home_team") or {}).get("full_name"),
                    "away": (g.get("visitor_team") or {}).get("full_name"),
                    "home_score": g.get("home_team_score"),
                    "away_score": g.get("visitor_team_score")
                })
            if js.get("meta",{}).get("next_page") is None: break
            page += 1
            time.sleep(0.25)
    save_jsonl("data/raw/basketball/nba_games.jsonl", rows)

def ingest_mlb(seasons=5):
    cli = HttpClient("https://statsapi.mlb.com/api")
    rows=[]
    for year in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        js = cli.get_json("v1/schedule", params={"sportId":1,"season":year})
        if not js: continue
        for d in js.get("dates", []):
            for g in d.get("games", []):
                rows.append({
                    "date": g.get("gameDate"), "league":"MLB",
                    "home": ((g.get("teams") or {}).get("home") or {}).get("team",{}).get("name"),
                    "away": ((g.get("teams") or {}).get("away") or {}).get("team",{}).get("name"),
                    "home_score": ((g.get("teams") or {}).get("home") or {}).get("score"),
                    "away_score": ((g.get("teams") or {}).get("away") or {}).get("score"),
                    "status": (g.get("status") or {}).get("detailedState")
                })
    save_jsonl("data/raw/baseball/mlb_games.jsonl", rows)

def ingest_nhl(seasons=5):
    cli = HttpClient("https://statsapi.web.nhl.com/api/v1")
    rows=[]
    for year in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        js = cli.get_json("schedule", params={"season": f"{year-1}{year}"})
        if not js: continue
        for d in js.get("dates", []):
            for g in d.get("games", []):
                rows.append({
                    "date": g.get("gameDate"), "league":"NHL",
                    "home": ((g.get("teams") or {}).get("home") or {}).get("team",{}).get("name"),
                    "away": ((g.get("teams") or {}).get("away") or {}).get("team",{}).get("name"),
                    "home_score": ((g.get("teams") or {}).get("home") or {}).get("score"),
                    "away_score": ((g.get("teams") or {}).get("away") or {}).get("score")
                })
    save_jsonl("data/raw/hockey/nhl_games.jsonl", rows)

def ingest_f1(seasons=10):
    cli = HttpClient("https://ergast.com/api/f1"); rows=[]
    for year in range(datetime.utcnow().year-1, datetime.utcnow().year-1-seasons, -1):
        res = cli.get_json(f"{year}.json")
        if not res: continue
        for race in ((res.get("MRData") or {}).get("RaceTable") or {}).get("Races", []):
            rows.append({
                "date": race.get("date"), "league":"F1",
                "circuit": ((race.get("Circuit") or {}).get("circuitName")),
                "country": ((race.get("Circuit") or {}).get("Location") or {}).get("country"),
                "round": race.get("round")
            })
    save_jsonl("data/raw/f1/f1_races.jsonl", rows)

def _read_csv(url: str):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8",errors="ignore"))))

def ingest_nfl(seasons=5):
    base = "https://raw.githubusercontent.com/nflverse/nflfastR-data/master/data/games/"
    rows=[]; current=datetime.utcnow().year-1
    for year in range(current, current-seasons, -1):
        try:
            recs = _read_csv(f"{base}games_{year}.csv")
        except Exception:
            try:
                recs = [r for r in _read_csv(f"{base}games.csv") if r.get("season") and int(r["season"])==year]
            except Exception:
                recs = []
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
                for rec in _read_csv(url):
                    rows.append({
                        "date": rec.get("tourney_date"), "tour": tour_name,
                        "winner": rec.get("winner_name"), "loser": rec.get("loser_name"),
                        "surface": rec.get("surface"), "score": rec.get("score")
                    })
            except Exception:
                continue
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
        save_jsonl("data/raw/esports/pandascore_matches.jsonl", []); 
        return
    headers={"Authorization": f"Bearer {token}"}
    titles = ["lol","cs2","dota2","valorant"]
    rows=[]
    for t in titles:
        page=1
        while page<=3:
            url = f"{base}/{t}/matches?page={page}&per_page=100&sort=begin_at"
            r = requests.get(url, headers=headers, timeout=45)
            if r.status_code>=400:
                break
            try:
                data = r.json()
            except Exception:
                break
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
            time.sleep(0.3)
    save_jsonl("data/raw/esports/pandascore_matches.jsonl", rows)

def ingest_efutbol_stub(): save_jsonl("data/raw/efutbol/efutbol.jsonl", [])
def ingest_pingpong_stub(): save_jsonl("data/raw/pingpong/pingpong.jsonl", [])
def ingest_mma_stub(): save_jsonl("data/raw/mma/mma.jsonl", [])
def ingest_box_stub(): save_jsonl("data/raw/boxing/boxing.jsonl", [])
def ingest_fantasy():
    save_jsonl("data/raw/fantasy_soccer/fantasy.jsonl", [{"date":datetime.utcnow().isoformat(),"mode":"fantasy"}])

def ingest_all(years=3):
    ROOT.mkdir(parents=True, exist_ok=True)
    steps = [
        lambda: ingest_nba(seasons=years),
        lambda: ingest_mlb(seasons=years),
        lambda: ingest_nhl(seasons=years),
        lambda: ingest_f1(seasons=years*2),
        lambda: ingest_nfl(seasons=years),
        lambda: ingest_tennis(years=years),
        lambda: ingest_soccer(seasons=years),
        lambda: ingest_esports_pandascore(years=years),
        ingest_efutbol_stub, ingest_pingpong_stub, ingest_mma_stub, ingest_box_stub, ingest_fantasy
    ]
    for fn in steps:
        try:
            fn()
        except Exception as e:
            print("WARN ingest step failed:", getattr(fn, "__name__", "step"), str(e))
    print("OK ingest EXTENDED with safe fallbacks.")

if __name__=="__main__":
    ingest_all(years=3)
