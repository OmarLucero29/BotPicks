# scripts/select_picks.py
from __future__ import annotations
import json, os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from statistics import mean
from typing import Dict, List

from dotenv import load_dotenv
from src.utils.kelly import kelly_fraction

load_dotenv()
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/Merida"))

BANK = float(os.getenv("BANK", "500"))
KELLY_FRAC = float(os.getenv("KELLY_FRACTION", "0.25"))   # 0.125/0.25/0.5
CAP_PCT = float(os.getenv("STAKE_CAP_PCT", "0.05"))       # 5% del bank
EV_THRESHOLD = float(os.getenv("EV_THRESHOLD", "0.02"))   # +2% por defecto
PREFER_BET365 = os.getenv("PREFER_BET365", "true").lower() == "true"

TODAY = datetime.now(TZ).date().isoformat()
SRC = Path("data") / TODAY
OUT = Path("data") / f"picks_{TODAY}.json"
SRC.mkdir(parents=True, exist_ok=True)

# Archivos esperados por deporte (como los creó ingest_daily.py)
FILES = [
    "futbol_odds.json",
    "baloncesto.json",
    "americano.json",
    "tenis.json",
]

def _load_items(fp: Path) -> List[Dict]:
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text())
        items = data.get("items", [])
        return items if isinstance(items, list) else []
    except Exception:
        return []

def _is_bet365(name: str) -> bool:
    return "bet365" in name.replace(" ", "").lower()

def _fair_probs_from_market(outcomes: List[Dict]) -> Dict[str, float]:
    """
    outcomes (agregadas de TODOS los bookies) => lista de dicts con 'name' y 'price'
    1) promedio de prob. implícitas por selección: mean(1/odds)
    2) normalizamos para remover margen: p_i / sum(p_i)
    """
    names = {}
    for o in outcomes:
        n = o.get("name")
        price = o.get("price")
        if not (n and isinstance(price, (int, float)) and price > 1.0):
            continue
        names.setdefault(n, []).append(1.0 / float(price))
    if not names:
        return {}
    avg_imp = {n: mean(vs) for n, vs in names.items()}
    z = sum(avg_imp.values())
    if z <= 0:
        return {}
    return {n: v / z for n, v in avg_imp.items()}

def _best_bookmaker(bookmakers: List[Dict]) -> Dict:
    """
    Si PREFER_BET365 y existe, usamos ese; de lo contrario, devolvemos el bookmaker
    que ofrezca mejores odds promedio en el mercado h2h.
    """
    if not bookmakers:
        return {}
    if PREFER_BET365:
        for b in bookmakers:
            if _is_bet365(b.get("title", "")):
                return b
    # fallback: mejor disponible por promedio de h2h
    best = None
    best_avg = -1.0
    for b in bookmakers:
        markets = b.get("markets", [])
        for m in markets:
            if m.get("key") != "h2h":
                continue
            outs = m.get("outcomes", [])
            prices = [o.get("price") for o in outs if isinstance(o.get("price"), (int, float))]
            if not prices:
                continue
            avg = sum(prices) / len(prices)
            if avg > best_avg:
                best_avg = avg
                best = b
    return best or bookmakers[0]

def _collect_h2h_outcomes_all_books(bookmakers: List[Dict]) -> List[Dict]:
    res = []
    for b in bookmakers:
        for m in b.get("markets", []):
            if m.get("key") == "h2h":
                for o in m.get("outcomes", []):
                    res.append({"name": o.get("name"), "price": o.get("price")})
    return res

def _h2h_outcomes_from_book(book: Dict) -> List[Dict]:
    for m in book.get("markets", []):
        if m.get("key") == "h2h":
            return m.get("outcomes", [])
    return []

def _build_pick(event: Dict, outcome: Dict, fair_p: float, sport: str, bookmaker_name: str) -> Dict:
    odds = float(outcome["price"])
    p = float(fair_p)
    ev = p * (odds - 1.0) - (1.0 - p)
    stake_frac = min(kelly_fraction(p, odds, KELLY_FRAC), CAP_PCT)
    stake_amt = round(BANK * stake_frac, 2)
    return {
        "date": TODAY,
        "sport": sport,
        "league": event.get("sport_key", ""),
        "event": event.get("id", ""),
        "home": event.get("home_team", ""),
        "away": event.get("away_team", ""),
        "market": "h2h",
        "bookmaker": bookmaker_name,
        "selection": outcome.get("name", ""),
        "odds": odds,
        "prob_fair": round(p, 4),
        "ev": round(ev, 4),
        "stake_mxn": stake_amt,
        "kelly_frac": KELLY_FRAC,
        "cap_pct": CAP_PCT,
    }

def _sport_label_from_file(fname: str) -> str:
    if fname.startswith("futbol"): return "futbol"
    if fname.startswith("baloncesto"): return "baloncesto"
    if fname.startswith("americano"): return "americano"
    if fname.startswith("tenis"): return "tenis"
    return "desconocido"

def main() -> None:
    picks: List[Dict] = []

    for fname in FILES:
        items = _load_items(SRC / fname)
        if not items:
            continue

        sport_label = _sport_label_from_file(fname)
        for evn in items:
            bms = evn.get("bookmakers", [])
            if not bms:
                continue

            # Precio justo desde TODO el mercado (normalizado)
            all_h2h = _collect_h2h_outcomes_all_books(bms)
            fair = _fair_probs_from_market(all_h2h)
            if not fair:
                continue

            # Casa preferida (Bet365) o mejor disponible
            book = _best_bookmaker(bms)
            outcomes = _h2h_outcomes_from_book(book)
            if not outcomes:
                continue

            for o in outcomes:
                name = o.get("name", "")
                if name not in fair:
                    continue
                pick = _build_pick(evn, o, fair[name], sport_label, book.get("title", "book"))
                if pick["ev"] >= EV_THRESHOLD:
                    picks.append(pick)

    OUT.write_text(json.dumps({"date": TODAY, "picks": picks}, ensure_ascii=False, indent=2))
    print(f"Picks -> {OUT} ({len(picks)} seleccionados con EV ≥ {EV_THRESHOLD:.2%})")

if __name__ == "__main__":
    main()
