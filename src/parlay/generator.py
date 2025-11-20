# src/parlay/generator.py
import os
import math
import json
import asyncio
from decimal import Decimal
from typing import List, Dict, Any
import asyncpg
from datetime import datetime, timezone

# Configs from env (respect exact names)
EV_THRESHOLD = float(os.getenv("EV_THRESHOLD", "0.0"))
MIN_PARLAY_LEGS = int(os.getenv("MIN_PARLAY_LEGS", "2"))
MAX_PARLAY_LEGS = int(os.getenv("MAX_PARLAY_LEGS", "8"))
DEFAULT_BANKROLL = float(os.getenv("BANKROLL", "100.0"))
DEFAULT_STAKE_PCT = float(os.getenv("STAKE_PCT", "2.0"))  # percent

# Utility: implied prob
def implied_prob(odds: float) -> float:
    if odds <= 0:
        return 0.0
    return 1.0 / odds

# Heuristic estimator for p_hat (can be replaced by model)
def estimate_prob_from_market(market: str, odds: float) -> float:
    """
    Very basic heuristic:
    - For moneyline: invert odds and slightly bias towards implied (no model available)
    - For totals: assume implied_prob with margin, small smoothing
    """
    ip = implied_prob(odds)
    # smooth toward 0.5 slightly to avoid extreme edges
    p_hat = (ip * 0.9) + 0.05
    return max(0.01, min(0.99, p_hat))

def compute_ev(p_hat: float, odds: float) -> float:
    # EV per unit stake
    return p_hat * (odds - 1) - (1 - p_hat)

def product_odds(odds_list: List[float]) -> float:
    prod = 1.0
    for o in odds_list:
        prod *= float(o)
    return prod

# Fetch candidate legs from match_cache table
async def fetch_candidate_legs(conn: asyncpg.Connection, included_sports: List[str] = None) -> List[Dict[str, Any]]:
    q = "SELECT match_id, sport, home, away, markets FROM match_cache WHERE markets IS NOT NULL AND start_time > now() - interval '1 day'"
    rows = await conn.fetch(q)
    candidates = []
    for r in rows:
        markets = r["markets"] or {}
        # markets stored as JSON: iterate common markets
        for market_name, selection_list in markets.items():
            # selection_list expected [{selection, odds}, ...]
            for s in selection_list:
                odds = s.get("odds")
                if not odds:
                    continue
                odds = float(odds)
                market = market_name
                selection = s.get("selection") or s.get("pick") or ""
                p_hat = estimate_prob_from_market(market, odds)
                ev = compute_ev(p_hat, odds)
                candidate = {
                    "match_id": r["match_id"],
                    "sport": r["sport"],
                    "home": r["home"],
                    "away": r["away"],
                    "market": market,
                    "selection": selection,
                    "odds": odds,
                    "ev": ev,
                    "p_hat": p_hat,
                    "metadata": s.get("metadata", {})
                }
                candidates.append(candidate)
    return candidates

# Insert parlay and legs into DB and return parlay id
async def persist_parlay(conn: asyncpg.Connection, user_id: int, mode: str, legs: List[Dict[str, Any]], stake: float) -> Dict[str, Any]:
    total_odds = product_odds([leg["odds"] for leg in legs])
    expected_return = total_odds * stake
    settings_snapshot = {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_total_odds": total_odds,
        "max_legs": len(legs)
    }
    row = await conn.fetchrow(
        "INSERT INTO parlays (user_id, mode, total_odds, legs_count, stake, expected_return, settings_snapshot) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
        user_id, mode, Decimal(str(total_odds)), len(legs), Decimal(str(stake)), Decimal(str(expected_return)), json.dumps(settings_snapshot)
    )
    parlay_id = row["id"]
    for leg in legs:
        await conn.execute(
            "INSERT INTO parlay_legs (parlay_id, match_id, sport, market, selection, odds, ev, metadata) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            parlay_id, str(leg["match_id"]), leg["sport"], leg["market"], str(leg["selection"]), Decimal(str(leg["odds"])), Decimal(str(leg["ev"])), json.dumps(leg.get("metadata", {}))
        )
    return {
        "id": parlay_id,
        "total_odds": total_odds,
        "stake": stake,
        "expected_return": expected_return,
        "settings_snapshot": settings_snapshot
    }

# Simple stake calc using bankroll percent (can be extended)
def calc_stake(bankroll: float, stake_pct: float) -> float:
    return round(bankroll * (stake_pct / 100.0), 2)

# Greedy Segurito: choose low odds legs until reach target_total_odds or max_legs
async def generate_parlay_segurito(db_pool, user_id: int, target_total_odds: float = 2.5, max_legs: int = 3) -> Dict[str, Any]:
    async with db_pool.acquire() as conn:
        candidates = await fetch_candidate_legs(conn)
        # filter EV>threshold and small odds
        candidates = [c for c in candidates if c["ev"] >= EV_THRESHOLD and c["odds"] <= 2.5]
        # sort ascending odds, then by ev desc
        candidates.sort(key=lambda x: (x["odds"], -x["ev"]))
        chosen = []
        current_odds = 1.0
        used_matches = set()
        for c in candidates:
            if len(chosen) >= max_legs:
                break
            # allow same match by config in future: for now allow duplicates
            chosen.append(c)
            current_odds = product_odds([leg["odds"] for leg in chosen])
            if current_odds >= target_total_odds and len(chosen) >= 2:
                break
        # fallback: if not enough, relax odds filter
        if product_odds([leg["odds"] for leg in chosen]) < target_total_odds:
            candidates_relaxed = [c for c in await fetch_candidate_legs(conn) if c["ev"] >= EV_THRESHOLD]
            candidates_relaxed.sort(key=lambda x: -x["ev"])
            chosen = []
            for c in candidates_relaxed:
                if len(chosen) >= max_legs:
                    break
                chosen.append(c)
                if product_odds([leg["odds"] for leg in chosen]) >= target_total_odds and len(chosen) >= 2:
                    break
        # stake calc: fetch user's bankroll from users table if exists
        bankroll_row = await conn.fetchrow("SELECT bankroll FROM users WHERE id=$1", user_id)
        bankroll = float(bankroll_row["bankroll"]) if bankroll_row and bankroll_row.get("bankroll") else DEFAULT_BANKROLL
        stake = calc_stake(bankroll, DEFAULT_STAKE_PCT)
        persisted = await persist_parlay(conn, user_id, "segurito", chosen, stake)
        # Build text
        text_lines = [f"🔥 Parlay Segurito (Cuota objetivo: {target_total_odds})", "Generado automáticamente por BotPicks", ""]
        text_lines.append(f"Legs seleccionadas: {len(chosen)}")
        text_lines.append(f"Cuota total: {float(persisted['total_odds']):.2f}")
        text_lines.append(f"Stake sugerido: ${persisted['stake']} ({DEFAULT_STAKE_PCT}%)\n")
        for leg in chosen:
            text_lines.append("-------------------------------------")
            text_lines.append(f"{leg['sport']} — {leg['home']} vs {leg['away']}")
            text_lines.append(f"Mercado: {leg['market']}")
            text_lines.append(f"Pick: {leg['selection']}")
            text_lines.append(f"Cuota: {leg['odds']:.2f}  EV: {'🟢' if leg['ev']>0 else '🔴'} {leg['ev']:.2f}")
            text_lines.append(f"Explicación: (heurística) EV {leg['ev']:.2f}")
        text_lines.append("\n💰 Potencial retorno: ${:.2f}".format(persisted["expected_return"]))
        text_lines.append("📊 Probabilidad estimada: (calculada internamente)")
        return {"id": persisted["id"], "text": "\n".join(text_lines), "mode": "segurito"}

# Beam search Soñador: try combinations to reach high total odds with EV>threshold
import itertools
async def generate_parlay_sonador(db_pool, user_id: int, target_total_odds: float = 10.0, max_legs: int = 8, beam_width: int = 200) -> Dict[str, Any]:
    async with db_pool.acquire() as conn:
        candidates = await fetch_candidate_legs(conn)
        candidates = [c for c in candidates if c["ev"] >= EV_THRESHOLD and c["odds"] > 1.2]
        # sort by ev desc and odds desc to prioritize high momio+edge
        candidates.sort(key=lambda x: (-x["ev"], -x["odds"]))
        # Limit candidates to top-N to avoid explosion
        candidates = candidates[:min(len(candidates), 60)]
        # Beam search across increasing lengths up to max_legs
        best_combo = None
        best_odds = 0.0
        beam = [([], 1.0)]
        for _ in range(1, min(max_legs, 8) + 1):
            new_beam = []
            for combo, combo_odds in beam:
                for c in candidates:
                    if c in combo:
                        continue
                    new_combo = combo + [c]
                    new_odds = combo_odds * c["odds"]
                    if new_odds >= target_total_odds:
                        # prefer combos with higher aggregated EV sum and higher odds
                        ev_sum = sum([x["ev"] for x in new_combo])
                        score = (new_odds * (1 + ev_sum))
                        if new_odds > best_odds:
                            best_combo = new_combo
                            best_odds = new_odds
                    new_beam.append((new_combo, new_odds))
            # keep top beam_width by odds * sum(ev)
            new_beam.sort(key=lambda tup: - (tup[1] * (1 + sum(x["ev"] for x in tup[0]))))
            beam = new_beam[:beam_width]
            if best_combo:
                break
        chosen = best_combo if best_combo else (beam[0][0] if beam else [])
        # stake calc
        bankroll_row = await conn.fetchrow("SELECT bankroll FROM users WHERE id=$1", user_id)
        bankroll = float(bankroll_row["bankroll"]) if bankroll_row and bankroll_row.get("bankroll") else DEFAULT_BANKROLL
        stake = calc_stake(bankroll, DEFAULT_STAKE_PCT)
        persisted = await persist_parlay(conn, user_id, "sonador", chosen, stake)
        # Build text
        text_lines = [f"💥 Parlay Soñador (Cuota objetivo: {target_total_odds})", "Generado automáticamente por BotPicks", ""]
        text_lines.append(f"Legs seleccionadas: {len(chosen)}")
        text_lines.append(f"Cuota total: {float(persisted['total_odds']):.2f}")
        text_lines.append(f"Stake sugerido: ${persisted['stake']} ({DEFAULT_STAKE_PCT}%)\n")
        for leg in chosen:
            text_lines.append("-------------------------------------")
            text_lines.append(f"{leg['sport']} — {leg['home']} vs {leg['away']}")
            text_lines.append(f"Mercado: {leg['market']}")
            text_lines.append(f"Pick: {leg['selection']}")
            text_lines.append(f"Cuota: {leg['odds']:.2f}  EV: {'🟢' if leg['ev']>0 else '🔴'} {leg['ev']:.2f}")
            text_lines.append(f"Explicación: (heurística) EV {leg['ev']:.2f}")
        text_lines.append("\n💰 Potencial retorno: ${:.2f}".format(persisted["expected_return"]))
        text_lines.append("📊 Probabilidad estimada: (calculada internamente)")
        return {"id": persisted["id"], "text": "\n".join(text_lines), "mode": "sonador"}
