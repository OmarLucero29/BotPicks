# scripts/ingest_daily.py
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import os

from dotenv import load_dotenv
from src.ingest.clients import fd_list_matches, odds_list_events

load_dotenv()
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/Merida"))

# Mapa de deportes -> clave OddsAPI (para cuotas)
ODDS_SPORTS = {
    "futbol": "soccer",
    "baloncesto": "basketball_nba",
    "americano": "americanfootball_nfl",
    "tenis": "tennis",
    # puedes ir sumando hockey/beisbol si deseas
}

# Competiciones Football-Data (gratis): Premier League=PL, LaLiga=PD, Bundesliga=BL1, Serie A=SA, Ligue 1=FL1, Champions=CL
FD_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1"]  # ajusta a tu gusto

def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

def ingest_futbol(out_dir: Path) -> None:
    fixtures = fd_list_matches(FD_COMPETITIONS)
    save_json(out_dir / "futbol_fixtures.json", {"items": fixtures})
    # Cuotas de soccer (si hay cobertura)
    odds = odds_list_events("soccer", regions="mx", markets="h2h,spreads,totals")
    save_json(out_dir / "futbol_odds.json", {"items": odds})

def ingest_with_oddsapi(sport_name: str, sport_key: str, out_dir: Path) -> None:
    odds = odds_list_events(sport_key, regions="mx", markets="h2h,spreads,totals")
    save_json(out_dir / f"{sport_name}.json", {"items": odds})

def main() -> None:
    today = datetime.now(TZ).date().isoformat()
    out_dir = Path("data") / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Fútbol: partidos (Football-Data) + cuotas (OddsAPI)
    ingest_futbol(out_dir)

    # 2) Otros deportes vía OddsAPI (si tu plan/región lo permite)
    for name, key in ODDS_SPORTS.items():
        if name == "futbol":
            continue  # ya lo cubrimos arriba con fixtures + odds
        ingest_with_oddsapi(name, key, out_dir)

    print(f"OK -> {out_dir}")

if __name__ == "__main__":
    main()
