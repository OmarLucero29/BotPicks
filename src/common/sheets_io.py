# src/pipelines/sheets_append.py
# Compat: Bot Americano → BotPicks
# Publica filas en Google Sheets con columnas:
# ID, FECHA, DEPORTE, PARTIDO, MERCADO, PICK, CUOTA (PROB %), STAKE

import os
import json
import math
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


# ---------------------------- Utilidades ------------------------------------- #

def _now_iso(date_tz: Optional[str] = None) -> str:
    # Guardamos en UTC iso corto YYYY-MM-DD HH:MM
    dt = datetime.now(timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def _to_decimal_odds(
    *,
    decimal: Optional[float] = None,
    american: Optional[float] = None,
    frac: Optional[str] = None,
) -> Optional[float]:
    if decimal and decimal > 1.0:
        return float(decimal)
    if american is not None:
        a = float(american)
        if a > 0:
            return 1.0 + (a / 100.0)
        elif a < 0:
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
    # Probabilidad implícita
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


def _num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        return float(str(x).strip())
    except Exception:
        return default


# ---------------------------- Carga de picks --------------------------------- #

def _load_picks() -> List[Dict[str, Any]]:
    """
    Orígenes soportados (en orden):
      1) env PICK_ROWS_JSON (string JSON con lista de picks)
      2) archivo en env PICKS_INPUT_PATH (default artifacts/picks.json)
      3) fallback outputs/picks.json
    Formato esperado por pick (keys flexibles):
      {
        "id": str (opcional),
        "fecha": "YYYY-MM-DD HH:MM" (opcional),
        "sport"|"deporte": str,
        "match"|"partido": str,
        "market"|"mercado": str,
        "pick": str,
        "odds"|"decimal_odds": float (opcional),
        "american_odds": int (opcional),
        "fractional_odds": "a/b" (opcional),
        "prob"|"probability": float 0-1 (opcional),
        "stake": float (opcional)
      }
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
    decimal = _to_decimal_odds(decimal=_num(dec, None), american=_num(am, None), frac=fr)

    prob = item.get("prob")
    if prob is None:
        prob = item.get("probability")
    prob = _num(prob, None)

    if (prob is None or prob <= 0) and decimal:
        prob = _prob_from_decimal(decimal)

    return decimal, prob


def _compute_stake(item: Dict[str, Any]) -> float:
    # Staking fijo por env o default 5% del bankroll
    if "stake" in item and item["stake"] is not None:
        return float(item["stake"])
    bankroll = _num(os.getenv("DEFAULT_BANKROLL", "500"), 500.0)
    pct = _num(os.getenv("DEFAULT_STAKE_PCT", "0.05"), 0.05)
    stake = bankroll * pct
    return round(stake, 2)


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

    # Columnas finales (checkpoint "cabezas")
    # ID, FECHA, DEPORTE, PARTIDO, MERCADO, PICK, CUOTA (PROB %), STAKE
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
            row = _to_row(p)
            rows.append(row)
        except Exception as e:
            # Falla suave: salta pick malformado
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


# --------------------------------- Main -------------------------------------- #

def main() -> None:
    picks = _load_picks()
    if not picks:
        print("[INFO] No hay picks para publicar. Termina sin errores.")
        return
    rows = _format_rows(picks)
    if not rows:
        print("[INFO] No se generaron filas válidas. Termina sin errores.")
        return
    publish_to_sheets(rows)


if __name__ == "__main__":
    # Verificación de sintaxis y ejecución controlada
    try:
        main()
    except Exception as exc:
        # Mensaje claro para logs de CI
        print(f"[ERROR] sheets_append falló: {exc}")
        raise