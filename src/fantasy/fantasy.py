"""
Módulo principal del modo Fantasy.
Funciones:
- fetch_data: wrappers para obtener stats/salaries/lineups de distintas APIs
- project_players: generación de proyecciones por jugador (puntaje esperado)
- optimize_lineup: optimizador (ILP) que respeta reglas por deporte/platform
- save_lineup: guarda en Google Sheets y Supabase en la tabla/pestaña FANTASY
"""

import os
import time
import math
import requests
import pandas as pd
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from typing import List, Dict, Any
import pulp

load_dotenv()

# Config / env
API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")  # api-football / api-sports
PANDASCORE_KEY = os.getenv("PANDASCORE_KEY")
ODDSAPI_KEY = os.getenv("ODDSAPI_KEY")
FOOTBALLDATA_KEY = os.getenv("FOOTBALLDATA_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GSHEET_ID = os.getenv("GSHEET_ID")
GOOGLE_SHEETS_CREDENTIALS_JSON_B64 = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON_B64")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "UTC")

# Basic dataclasses
@dataclass
class Player:
    id: str
    name: str
    team: str
    position: str
    cost: float
    projections: Dict[str, float]  # e.g., {"points": 12.3, "variance": 2.1}
    meta: Dict[str, Any]

# --- Data fetchers (minimal, extensible) ---
def fetch_api_sports_players(sport: str, league_id: str, date: str) -> pd.DataFrame:
    """
    Descarga estadísticas base por jugador desde API-Sports (API_SPORTS_KEY).
    sport: 'football', 'basketball', 'tennis', ...
    league_id: id de la liga en API-Sports
    date: 'YYYY-MM-DD' (para filtrar fixtures)
    Retorna DataFrame con columnas mínimas: player_id, name, team, position, minutes, stats...
    """
    if not API_SPORTS_KEY:
        raise EnvironmentError("Falta API_SPORTS_KEY en .env")
    base = "https://v3.football.api-sports.io"
    # Nota: rutas varían por deporte. Aquí implementamos fútbol como ejemplo; extender por deporte.
    headers = {"x-apisports-key": API_SPORTS_KEY}
    # ejemplo: obtener jugadores en fixture -> usamos endpoints de lineups o players stats según deporte
    # Implementación simplificada: intenta lineups por fixture
    resp = requests.get(f"{base}/fixtures?league={league_id}&date={date}", headers=headers, timeout=30)
    resp.raise_for_status()
    fixtures = resp.json().get("response", [])
    rows = []
    for fx in fixtures:
        fixture_id = fx["fixture"]["id"]
        # lineups
        r2 = requests.get(f"{base}/fixtures/lineups?fixture={fixture_id}", headers=headers, timeout=30)
        if r2.status_code != 200: 
            continue
        for team_lineup in r2.json().get("response", []):
            team_name = team_lineup.get("team", {}).get("name")
            for p in team_lineup.get("startXI", []):
                pid = str(p["player"]["id"])
                rows.append({
                    "player_id": pid,
                    "name": p["player"]["name"],
                    "team": team_name,
                    "position": p["player"]["position"] if "position" in p["player"] else "UNK",
                    "minutes": None
                })
    if not rows:
        return pd.DataFrame(columns=["player_id","name","team","position","minutes"])
    return pd.DataFrame(rows)

def fetch_pandascore_players(kind: str, tournament_id: str) -> pd.DataFrame:
    """
    Wrapper para Pandascore (eSports, MMA, etc.)
    """
    if not PANDASCORE_KEY:
        raise EnvironmentError("Falta PANDASCORE_KEY en .env")
    base = "https://api.pandascore.co"
    headers = {}
    params = {"token": PANDASCORE_KEY}
    resp = requests.get(f"{base}/{kind}/{tournament_id}/players", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rows = []
    for p in data:
        rows.append({
            "player_id": str(p.get("id")),
            "name": p.get("name"),
            "team": p.get("team", {}).get("name") if p.get("team") else None,
            "position": p.get("role") or p.get("position") or "UNK"
        })
    return pd.DataFrame(rows)

# Generic fetcher interface to be extended for each sport/platform
def fetch_players_for_market(sport: str, league_or_event_id: str, date: str) -> pd.DataFrame:
    """
    Detecta la fuente preferida por deporte y llama al fetcher adecuado.
    """
    sport = sport.lower()
    if sport in ("football","soccer"):
        # prefer API-Sports / FootballData
        return fetch_api_sports_players("football", league_or_event_id, date)
    elif sport in ("basketball","nba"):
        if API_SPORTS_KEY:
            # API-Sports basketball endpoints (implement similar)
            return fetch_api_sports_players("basketball", league_or_event_id, date)
        else:
            raise EnvironmentError("No hay fuente configurada para baloncesto.")
    else:
        # e.g., fallback to pandascore if available
        if PANDASCORE_KEY:
            return fetch_pandascore_players(sport, league_or_event_id)
        else:
            raise EnvironmentError(f"No hay fetcher configurado para {sport}")

# --- Projection engine (simple, interpretable) ---
def project_players(df_players: pd.DataFrame, sport: str) -> List[Player]:
    """
    Genera proyecciones de puntos esperados por jugador.
    Esta implementación es deliberadamente simple y robusta como MVP:
    - Asigna una proyección base por posición usando historial resumido
    - Ajusta por "precio" si existe
    - Devuelve lista de Player dataclasses
    """
    players: List[Player] = []
    for _, r in df_players.iterrows():
        pid = str(r.get("player_id") or r.get("id") or r.get("id_str"))
        name = r.get("name", "Unknown")
        team = r.get("team", "Unknown")
        pos = r.get("position", "UNK")
        # Costo: si no existe, generar proxy (random-ish deterministic)
        cost = float(r.get("cost", 10.0))
        # Base points by position (very simple)
        base_points = 0.0
        if sport.lower() in ("football","soccer"):
            if pos.upper().startswith("G") or pos.upper()=="GK":
                base_points = 6.0
            elif pos.upper().startswith("D"):
                base_points = 5.5
            elif pos.upper().startswith("M"):
                base_points = 6.5
            elif pos.upper().startswith("F"):
                base_points = 8.0
        elif sport.lower() in ("basketball","nba"):
            base_points = 25.0
        else:
            base_points = 10.0
        # Simplified projection: base * (10/(cost+1))
        points = base_points * (10.0 / (cost + 1.0))
        variance = max(1.0, points * 0.25)
        p = Player(
            id=pid,
            name=name,
            team=team,
            position=pos,
            cost=cost,
            projections={"points": round(points, 2), "variance": round(variance,2)},
            meta={}
        )
        players.append(p)
    return players

# --- Optimizer: ILP with pulp ---
def optimize_lineup(players: List[Player], sport: str, formation_rules: Dict[str,int], budget: float,
                    max_same_team: int, profile: str = "balanceado") -> Dict[str, Any]:
    """
    Optimiza para max points expected subject to constraints:
    formation_rules: dict with required counts per position e.g. {"GK":1,"DEF":3,"MID":4,"FWD":3}
    budget: max cost
    max_same_team: cap per team
    profile: "conservador"|"balanceado"|"soñador" -> adjusts objective (risk aversion)
    Retorna dict con lineup, stats
    """
    # Problem
    prob = pulp.LpProblem("FantasyLineup", pulp.LpMaximize)
    # Decision vars
    x = {p.id: pulp.LpVariable(f"x_{p.id}", cat="Binary") for p in players}
    # Objective: max sum(expected points) adjusted by variance depending on profile
    if profile == "conservador":
        # penalize variance strongly
        obj = pulp.lpSum([ x[p.id] * (p.projections["points"] - 0.5 * p.projections["variance"]) for p in players ])
    elif profile == "soñador":
        # prefer upside: add variance bonus
        obj = pulp.lpSum([ x[p.id] * (p.projections["points"] + 0.3 * p.projections["variance"]) for p in players ])
    else: # balanceado
        obj = pulp.lpSum([ x[p.id] * p.projections["points"] for p in players ])
    prob += obj

    # Budget constraint
    prob += pulp.lpSum([ x[p.id] * p.cost for p in players ]) <= budget

    # Position constraints: sum per position equals required
    for pos_key, required in formation_rules.items():
        # match players whose position contains pos_key (simple)
        prob += pulp.lpSum([ x[p.id] for p in players if pos_key.lower() in p.position.lower() ]) == required

    # Max same team constraint
    teams = set([p.team for p in players])
    for team in teams:
        prob += pulp.lpSum([ x[p.id] for p in players if p.team == team ]) <= max_same_team

    # Total players constraint (sum required)
    total_required = sum(formation_rules.values())
    prob += pulp.lpSum([ x[p.id] for p in players ]) == total_required

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))

    selected = []
    total_points = 0.0
    total_cost = 0.0
    for p in players:
        val = x[p.id].value()
        if val is not None and val > 0.5:
            selected.append(p)
            total_points += p.projections["points"]
            total_cost += p.cost

    result = {
        "selected": selected,
        "total_points": round(total_points,2),
        "total_cost": round(total_cost,2),
        "status": pulp.LpStatus[prob.status]
    }
    return result

# --- Save / persistence (Google Sheets + Supabase) ---
def save_lineup_to_gsheet(lineup: Dict[str, Any], sheet_id: str, tab_name: str = "FANTASY"):
    """
    Guarda la alineación en Google Sheets en la pestaña FANTASY.
    Requiere GOOGLE_SHEETS_CREDENTIALS_JSON_B64 y GSHEET_ID en env.
    """
    import base64, json, gspread
    from oauth2client.service_account import ServiceAccountCredentials

    if not GOOGLE_SHEETS_CREDENTIALS_JSON_B64 or not sheet_id:
        raise EnvironmentError("Faltan credenciales de Google Sheets o GSHEET_ID en .env")
    creds_json = base64.b64decode(GOOGLE_SHEETS_CREDENTIALS_JSON_B64).decode("utf-8")
    creds = json.loads(creds_json)
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    signer = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    client = gspread.authorize(signer)
    sh = client.open_by_key(sheet_id)
    try:
        worksheet = sh.worksheet(tab_name)
    except Exception:
        worksheet = sh.add_worksheet(title=tab_name, rows="1000", cols="20")
    # Prepare row
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    selected = lineup["selected"]
    players_str = "; ".join([f"{p.name} ({p.position}) - {p.projections['points']}pt" for p in selected])
    row = [str(int(time.time())), now, lineup.get("sport","unknown"), lineup.get("platform","unknown"),
           f"Cost:{lineup.get('total_cost')}", lineup.get("profile","balanceado"),
           lineup.get("total_points"), players_str]
    worksheet.append_row(row)

def save_lineup_to_supabase(lineup: Dict[str, Any], table_name: str = "fantasy"):
    """
    Guarda registro en Supabase (tabla 'fantasy' o similar).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError("Faltan SUPABASE_URL/SERVICE_ROLE en .env")
    url = SUPABASE_URL.rstrip("/")
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type":"application/json"}
    payload = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sport": lineup.get("sport"),
        "platform": lineup.get("platform"),
        "profile": lineup.get("profile"),
        "total_points": lineup.get("total_points"),
        "total_cost": lineup.get("total_cost"),
        "players": [asdict(p) for p in lineup.get("selected", [])]
    }
    resp = requests.post(f"{url}/rest/v1/{table_name}", json=payload, headers=headers, timeout=30)
    if resp.status_code not in (200,201):
        raise RuntimeError(f"Error guardando en Supabase: {resp.status_code} {resp.text}")
    return resp.json()

# --- High level runner (used by telegram handlers) ---
def generate_and_store_lineup(sport: str, league_or_event_id: str, date: str, platform: str,
                              profile: str, budget: float, formation_rules: Dict[str,int],
                              max_same_team: int = 3):
    df = fetch_players_for_market(sport, league_or_event_id, date)
    players = project_players(df, sport)
    opt = optimize_lineup(players, sport, formation_rules, budget, max_same_team, profile)
    opt["sport"] = sport
    opt["platform"] = platform
    opt["profile"] = profile
    # Save in GS + Supabase
    try:
        save_lineup_to_gsheet(opt, GSHEET_ID, tab_name="FANTASY")
    except Exception as e:
        # log but continue
        print("Warning: fallo guardando en GSheet:", e)
    try:
        save_lineup_to_supabase(opt, table_name="fantasy")
    except Exception as e:
        print("Warning: fallo guardando en Supabase:", e)
    return opt
