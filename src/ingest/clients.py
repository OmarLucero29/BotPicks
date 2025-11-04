# src/ingest/clients.py
from __future__ import annotations
import os
import time
import requests
from typing import Any, Dict, List, Optional

FD_BASE = "https://api.football-data.org/v4"
ODDS_BASE = "https://api.the-odds-api.com/v4"

FD_KEY = os.getenv("FOOTBALLDATA_KEY", "")
ODDS_KEY = os.getenv("ODDSAPI_KEY", "")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BotPicks/1.0"})

def _get(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
    """GET con reintentos y backoff leve."""
    for i in range(4):
        try:
            resp = SESSION.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 429:  # rate limit
                time.sleep(1.5 * (i + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if i == 3:
                raise
            time.sleep(1.5 * (i + 1))
    return None

# ------------ Football-Data (FÚTBOL) ------------
def fd_list_matches(competitions: List[str]) -> List[Dict[str, Any]]:
    """
    competitions: IDs o códigos de ligas, p.ej. ["PL","PD","BL1","SA","FL1","CL"].
    Devuelve lista de partidos próximos con equipos y hora programada.
    """
    if not FD_KEY:
        return []
    hdr = {"X-Auth-Token": FD_KEY}
    out: List[Dict[str, Any]] = []
    for comp in competitions:
        url = f"{FD_BASE}/competitions/{comp}/matches"
        data = _get(url, headers=hdr, params={"status": "SCHEDULED"})
        if not data:
            continue
        for m in data.get("matches", []):
            out.append(
                {
                    "source": "football-data",
                    "competition": comp,
                    "utcDate": m.get("utcDate"),
                    "home": m.get("homeTeam", {}).get("name"),
                    "away": m.get("awayTeam", {}).get("name"),
                    "id": m.get("id"),
                }
            )
        time.sleep(0.3)  # cuida el rate limit free
    return out

# ------------ OddsAPI (CUOTAS) ------------
def odds_list_events(sport_key: str, regions: str = "mx", markets: str = "h2h,spreads,totals") -> List[Dict[str, Any]]:
    """
    sport_key: 'soccer', 'basketball_nba', 'americanfootball_nfl', 'tennis'
    regions: 'mx' (México), 'us', 'eu'... según cobertura.
    """
    if not ODDS_KEY:
        return []
    url = f"{ODDS_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_KEY,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    data = _get(url, params=params)
    if not isinstance(data, list):
        return []
    return data

def odds_list_sports() -> List[Dict[str, Any]]:
    if not ODDS_KEY:
        return []
    url = f"{ODDS_BASE}/sports"
    data = _get(url, params={"apiKey": ODDS_KEY})
    if not isinstance(data, list):
        return []
    return data
