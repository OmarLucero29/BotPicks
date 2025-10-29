# src/pipelines/sheets_append.py
# Publica filas en Google Sheets con columnas:
# ID, FECHA, DEPORTE, PARTIDO, MERCADO, PICK, CUOTA (PROB %), STAKE

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from src.common.sheets_io import write_rows


# ---------------------------- Utilidades ------------------------------------- #

def _now_iso() -> str:
    dt = datetime.now(timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def _to_decimal_odds(
    *, decimal: Optional[float] = None, american: Optional[float] = None, frac: Optional[str] = None
) -> Optional[float]:
    if decimal and decimal > 1.0:
        return float(decimal)
    if american is not None:
        a = float(american)
        if a > 0:
            return 1.0 + (a / 100.0)
        if a < 0:
            return 1.0 + (100.0 / abs(a))
        return None
    if frac:
        try:
            n, d = frac.split("/")
            return 1.0 + (float(n) / float(d))
        except Exception:
            return None
    return None


def _prob_from_decimal(odds: float) -> float:
    return 1.0 / float(odds) if odds and odds > 0 else 0.0


def _fmt_odds_prob(odds: Optional[float], prob: Optional[float]) -> str:
    if odds is None and (prob is None or prob <= 0):
        return ""
    if odds is None and prob is not None:
        return f"( {prob*100:.1f}% )"
    if prob is None or prob <= 0:
        return f"{odds:.2f}"
    return f"{odds:.2f} ({prob*100:.1f}%)"


def _hash_id(parts: Iterable[str]) -> str:
    base = "||".join([p.strip() for p in parts if p is not None])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def _num(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        return float(s)
    except Exception:
        return default


# ---------------------------- Carga de picks --------------------------------- #

def _load_picks() -> List[Dict[str, Any]]:
    """
    Orígenes:
      1) env PICK_ROWS_JSON (string JSON con lista o {"picks":[...]})
      2) archivo env PICKS_INPUT_PATH (default artifacts/picks.json)
      3) fallback outputs/picks.json
    """
    env_json = os.getenv("PICK_ROWS_JSON", "").strip()
    if env_json:
        data = json.loads(env_json)
        if isinstance(data, dict):
            data = data.get("picks", [])
        if not isinstance(data, list):
            raise RuntimeError("PICK_ROWS_JSON debe ser lista o {picks:[...]}")
        return data

    path = os.getenv("PICKS_INPUT_PATH", "artifacts/picks.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("picks", [])
        if not isinstance(data, list):
            raise RuntimeError(f"{path} debe ser lista o {{picks:[...]}}")
        return data

    alt = "outputs/picks.json"
    if os.path.exists(alt):
        with open(alt, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("picks", [])
        if not isinstance(data, list):
            raise RuntimeError(f"{alt} debe ser lista o {{picks:[...]}}")
        return data

    return []


# ---------------------------- Formateo filas --------------------------------- #

def _resolve_decimal_and_prob(item: Dict[str, Any]) -> (Optional[float], Optional[float]):
    dec = item.get("odds") or item.get("decimal_odds")
    am = item.get("american_odds")
    fr = item.get("fractional_odds")
    decimal = _to_decimal_odds(decimal=_num(dec), american=_num(am), frac=fr)

    prob = item.get("prob")
    if prob is None:
        prob = item.get("probability")
    prob = _num(prob)

    if (prob is None or prob <= 0) and decimal:
        prob = _prob_from_decimal(decimal)

    return decimal, prob


def _compute_stake(item: Dict[str, Any]) -> float:
    if "stake" in item and item["stake"] is not None:
        return float(item["stake"])
    bankroll = _num(os.getenv("DEFAULT_BANKROLL", "500"), 500.0) or 500.0
    pct = _num(os.getenv("DEFAULT_STAKE_PCT", "0.05"), 0.05) or 0.05
    return round(bankroll * pct, 2)


def _ensure_id(item: Dict[str, Any], fecha: str, deporte: str, partido: str,
               mercado: str, pick: str) -> str:
    if item.get("id"):
        return str(item["id"])
    return _hash_id([fecha, deporte, partido, mercado, pick])


def _to_row(item: Dict[str, Any]) -> List[str]:
    deporte = str(item.get("deporte") or item.get("sport") or "").strip()
    partido = str(item.get("partido") or item.get("match") or "").strip()
    mercado = str(item.get("mercado") or item.get("market") or "").strip()
    pick = str(item.get("pick") or "").strip()
    fecha = str(item.get("fecha") or item.get("date") or _now_iso()).strip()

    decimal, prob = _resolve_decimal_and_prob(item)
    cuota_prob = _fmt_odds_prob(decimal, prob)
    stake = _compute_stake(item)
    _id = _ensure_id(item, fecha, deporte, partido, mercado, pick)

    return [
        _id,
        fecha,
        deporte,
        partido,
        mercado,
        pick,
        cuota_prob,
        f"{stake:.2f}",
    ]


def _format_rows(picks: List[Dict[str, Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for p in picks:
        try:
            rows.append(_to_row(p))
        except Exception as e:
            print(f"[WARN] pick descartado por error de formato: {e}")
    return rows


# ---------------------------- Publicación ------------------------------------ #

def publish_to_sheets(rows: List[List[str]]) -> None:
    sheet_id = os.getenv("GSHEET_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("GSHEET_ID no definido.")
    tab = os.getenv("GSHEET_PICKS_TAB", "PICKS").strip() or "PICKS"
    write_rows(sheet_id, tab, rows)
    print(f"[OK] {len(rows)} filas enviadas a Google Sheets → pestaña '{tab}'.")