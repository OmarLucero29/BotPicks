# src/parlay/evaluator.py
from typing import Dict, Any, Optional
import re

"""
Evaluador de resultados de una 'leg'.
Entrada leg: {
  "market": "Moneyline" | "Over/Under 2.5" | "Both Teams To Score" | "Handicap -1" | "Correct Score" | ...,
  "selection": "Home" | "Away" | "Over 2.5" | "Yes" | "2-1" | "TeamName" | "Home -1" ...
  "metadata": {...} optional (p. ej. {"line":2.5, "side":"over"})
}

Entrada match_final (desde match_cache):
{
  "status": "finished"|"inplay"|"not_started",
  "home": "Team A",
  "away": "Team B",
  "home_score": 2,
  "away_score": 1,
  "maps": [{"home_score":2,"away_score":1},...],  // para esports/bo3 etc.
  "winner": "home"|"away"|"draw",  // si disponible
  "final_result": {...} optional provider-specific
}
Retorna: True (ganado), False (perdido), None (no decidido / no soportado)
"""

def normalize_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s.strip().lower())

def parse_over_under(selection: str) -> Optional[Dict[str, Any]]:
    # selection examples: "Over 2.5", "Under 3", "o2.5", "u3"
    s = normalize_text(selection)
    m = re.search(r'(over|o)\s*([0-9]+(?:\.[05])?)', s)
    if m:
        return {"type":"over_under", "side":"over", "line":float(m.group(2))}
    m = re.search(r'(under|u)\s*([0-9]+(?:\.[05])?)', s)
    if m:
        return {"type":"over_under", "side":"under", "line":float(m.group(2))}
    return None

def parse_handicap(selection: str) -> Optional[Dict[str, Any]]:
    # "Home -1" , "-1 Away", "TeamA -0.5"
    s = normalize_text(selection)
    m = re.search(r'([^\d\-\+]+)?\s*([+-]?[0-9]+(?:\.[05])?)\s*$', selection)
    if m:
        # try detect side by presence of team name vs sign
        # fallback: if selection contains home/away words
        side = None
        if 'home' in s:
            side = 'home'
        elif 'away' in s:
            side = 'away'
        return {"type":"handicap", "line":float(m.group(2)), "side":side}
    return None

def parse_correct_score(selection: str) -> Optional[Dict[str, Any]]:
    # formats: "2-1", "1 : 0", "3:2"
    s = normalize_text(selection)
    m = re.search(r'(\d+)\s*[:\-]\s*(\d+)', s)
    if m:
        return {"type":"correct_score", "home":int(m.group(1)), "away":int(m.group(2))}
    return None

def parse_btts(selection: str) -> Optional[Dict[str, Any]]:
    s = normalize_text(selection)
    if s in ('yes','si','sí','y'):
        return {"type":"btts","side":"yes"}
    if s in ('no','n'):
        return {"type":"btts","side":"no"}
    return None

def parse_moneyline(selection: str, match_final: Dict[str,Any]) -> Optional[Dict[str,Any]]:
    s = normalize_text(selection)
    # Accept "home", "away", "draw", team names
    if s in ('home','away','draw'):
        return {"type":"moneyline", "side":s}
    # try match team names
    home = normalize_text(match_final.get("home","") or "")
    away = normalize_text(match_final.get("away","") or "")
    if s == home or s == normalize_text(match_final.get("home","")):
        return {"type":"moneyline","side":"home"}
    if s == away:
        return {"type":"moneyline","side":"away"}
    return None

def parse_total_team(selection: str) -> Optional[Dict[str,Any]]:
    # Team total like "TeamA Over 1.5" or "Home Over 1.5"
    s = normalize_text(selection)
    m = re.search(r'(home|away|team\s*[a-z0-9]+|[a-z ]+)\s+(over|under)\s*([0-9]+(?:\.[05])?)', s)
    if m:
        return {"type":"team_total", "side":m.group(2), "line":float(m.group(3)), "team":m.group(1)}
    return None

def parse_map_total(selection: str) -> Optional[Dict[str,Any]]:
    # For esports map totals, e.g. "Over 2.5 maps" or "Map winner Home"
    return None  # placeholder, expand if specific samples provided

# Generic parser tries several market parsers
def parse_selection(market: str, selection: str, match_final: Dict[str,Any]) -> Optional[Dict[str,Any]]:
    market_norm = normalize_text(market)
    sel_norm = normalize_text(selection)
    # Over/Under markets
    if 'over' in market_norm or 'under' in market_norm or 'total' in market_norm:
        res = parse_over_under(selection)
        if res:
            return res
    # Both Teams To Score
    if 'both' in market_norm and 'score' in market_norm:
        res = parse_btts(selection)
        if res:
            return res
    # Correct score
    if 'correct' in market_norm or 'score' in market_norm and '-' in selection:
        res = parse_correct_score(selection)
        if res:
            return res
    # Handicap / spread
    if 'handicap' in market_norm or 'spread' in market_norm or ('-' in selection and any(ch.isdigit() for ch in selection)):
        res = parse_handicap(selection)
        if res:
            return res
    # Moneyline / match winner
    if any(k in market_norm for k in ['moneyline','winner','match winner','ml','1x2']):
        res = parse_moneyline(selection, match_final)
        if res:
            return res
    # Team total
    res = parse_total_team(selection)
    if res:
        return res
    # Fallback: try moneyline by team names
    res = parse_moneyline(selection, match_final)
    if res:
        return res
    return None

def evaluate_leg(leg: Dict[str, Any], match_final: Dict[str, Any]) -> Optional[bool]:
    """
    Devuelve True si la leg está ganada, False si perdida, None si no hay datos/soporte.
    """
    if not match_final or not match_final.get("status"):
        return None
    status = match_final.get("status").lower()
    if status != "finished" and status != "post":  # permitir 'post' o 'finished'
        return None

    # Normalize basic scores
    try:
        home_score = int(match_final.get("home_score", 0) or 0)
        away_score = int(match_final.get("away_score", 0) or 0)
    except Exception:
        home_score = None
        away_score = None

    parsed = parse_selection(leg.get("market",""), str(leg.get("selection","")), match_final)
    if not parsed:
        return None

    t = parsed.get("type")
    # Moneyline
    if t == "moneyline":
        winner = match_final.get("winner")
        if not winner:
            # derive winner from scores
            if home_score is None or away_score is None:
                return None
            if home_score > away_score:
                winner = "home"
            elif away_score > home_score:
                winner = "away"
            else:
                winner = "draw"
        side = parsed.get("side")
        return winner == side

    # Over/Under
    if t == "over_under":
        if home_score is None or away_score is None:
            return None
        total = home_score + away_score
        line = parsed.get("line")
        side = parsed.get("side")
        if side == "over":
            return total > line
        else:
            return total < line

    # BTTS
    if t == "btts":
        if home_score is None or away_score is None:
            return None
        if parsed.get("side") == "yes":
            return (home_score > 0 and away_score > 0)
        return not (home_score > 0 and away_score > 0)

    # Correct score
    if t == "correct_score":
        if home_score is None or away_score is None:
            return None
        return (home_score == parsed.get("home") and away_score == parsed.get("away"))

    # Handicap
    if t == "handicap":
        if home_score is None or away_score is None:
            return None
        line = float(parsed.get("line",0.0))
        # Determine side: if parsed.side is None, deduce by presence of home/away in selection string
        side = parsed.get("side")
        # compute goal difference from perspective of side
        # standard handicap: home_score + (-line) vs away_score  (if side home and line negative means give goals)
        # We'll compute margin = (home_score - away_score) and compare with line
        margin = home_score - away_score
        # If line is applied to home (side home)
        if side == "home" or side is None:
            # Example: 'Home -1' means margin > 1 -> home covers
            return margin + line > 0  # if line is negative, adding increases
        else:
            # side away
            return (-margin) + line > 0

    # Team total (Home/Away team over/under X)
    if t == "team_total":
        team = parsed.get("team")
        if team is None:
            return None
        # figure which team: home/away by matching 'home'/'away' or name
        target_score = None
        if 'home' in normalize_text(team):
            target_score = home_score
        elif 'away' in normalize_text(team):
            target_score = away_score
        else:
            # try name match
            if normalize_text(team) == normalize_text(match_final.get("home","")):
                target_score = home_score
            elif normalize_text(team) == normalize_text(match_final.get("away","")):
                target_score = away_score
            else:
                # unknown team token
                return None
        side = parsed.get("side")
        line = parsed.get("line")
        if side == "over":
            return target_score > line
        else:
            return target_score < line

    # Map / esports / sets: attempt naive evaluation if maps field present and selection mentions map total/covers
    if t == "map_total" or 'maps' in match_final:
        # Not implemented fully without concrete formats. Return None for now.
        return None

    return None
