import os, json, pathlib, joblib, random
from datetime import datetime
from src.common.odds import from_decimal
from src.common.stake_kelly import KellyConfig, compute_kelly
from src.common.supabase_io import insert_pick
from src.common.sheets_io import write_rows
from src.common.env import env_float
from src.common.settings import get_bankroll

MODELS = pathlib.Path("models")
CFG = json.load(open("config/menu_config.json","r",encoding="utf-8"))

def _mock_candidates(sport_key:str, n:int):
    out=[]
    for i in range(n):
        odds = round(1.40 + random.random()*1.6, 2)
        p = min(max(0.48 + random.random()*0.22, 0.01), 0.99)
        out.append({"partido": f"{sport_key.upper()}-{i} vs {i+1}", "odds": odds, "prob": p, "brier": 0.14+random.random()*0.08})
    return out

def _load_model(sport_key: str):
    cand = [sport_key, "basketball", "soccer", "baseball"]
    for c in cand:
        f = MODELS / f"{c}.joblib"
        if f.exists(): return joblib.load(f)
    return None

def _parlay_buckets(picks: list[dict], cfg: dict):
    seg, son = [], []
    min_odds = cfg["parlay"]["segurito"]["min_odds"]
    max_legs_seg = cfg["parlay"]["segurito"]["max_legs"]
    target_son = cfg["parlay"]["sonador"]["target_odds"]
    max_legs_son = cfg["parlay"]["sonador"]["max_legs"]

    for p in picks:
        if p["cuota"] >= min_odds and len(seg) < max_legs_seg:
            seg.append(p)

    total = 1.0
    for p in sorted(picks, key=lambda x: -x["cuota"]):
        if len(son) >= max_legs_son: break
        son.append(p); total *= p["cuota"]
        if total >= target_son: break
    return seg, son

def _format_parlay_row(ptype:str, deporte:str, legs:list[dict], odds_fmt:str):
    total_odds = 1.0
    legs_desc = []
    for l in legs:
        total_odds *= l["cuota"]
        legs_desc.append(f"{l['partido']}@{from_decimal(l['cuota'], odds_fmt)}")
    return [
        datetime.utcnow().isoformat(), ptype, deporte, len(legs),
        " + ".join(legs_desc), f"{from_decimal(total_odds, odds_fmt)}"
    ]

def publish_today(odds_fmt:str, bankroll:float, fraction:float, top:int):
    rows_picks, rows_parlays = [], []
    for sport_key, on in CFG["sports_active"].items():
        if not on: continue
        model = _load_model(sport_key)
        cfg_k = KellyConfig(bankroll=bankroll, fraction=fraction,
                            min_pct=float(os.getenv("DEFAULT_STAKE_MIN","0.01")),
                            max_pct=float(os.getenv("DEFAULT_STAKE_MAX","0.10")))
        picks = _mock_candidates(sport_key, top)
        enriched=[]
        for pk in picks:
            dec = pk["odds"]
            p_cal = float(model["iso"].transform([pk["prob"]])[0]) if model else pk["prob"]
            ev = p_cal*dec - 1.0
            edge = p_cal - (1.0/dec)
            amount, pct, kraw = compute_kelly(p_cal, dec, cfg_k, brier=pk["brier"])
            conf = "A" if pk["brier"]<=0.12 else ("B" if pk["brier"]<=0.20 else "C")

            row_db = {
              "fecha": datetime.utcnow().isoformat(), "deporte": sport_key, "liga": "general",
              "partido": pk["partido"], "mercado": "Moneyline", "pick": pk["partido"].split(" vs ")[0],
              "cuota": dec, "prob_modelo": round(p_cal,4), "brier": round(pk["brier"],3),
              "stake": amount, "stake_pct": pct, "confianza": conf, "ev": round(ev,4),
              "resultado": "pending", "roi": None, "kelly_raw": round(kraw,4), "kelly_fraction": fraction,
              "extra": {"edge": round(edge,4)}
            }
            try: insert_pick(row_db)
            except Exception: pass

            rows_picks.append([
              datetime.utcnow().isoformat(), sport_key, "general", pk["partido"], "Moneyline",
              row_db["pick"], from_decimal(dec, odds_fmt), f"{p_cal:.2f}", f"{amount:.2f}", conf, f"{ev:.3f}"
            ])
            enriched.append({"cuota": dec, "partido": pk["partido"]})

        seg, son = _parlay_buckets(enriched, CFG)
        if seg:
            rows_parlays.append(_format_parlay_row("Segurito", sport_key, seg, odds_fmt))
        if son:
            rows_parlays.append(_format_parlay_row("Soñador", sport_key, son, odds_fmt))

    if os.getenv("SEND_DAILY_TO_SHEETS","true").lower()=="true":
        sheet_id = os.getenv("GSHEET_ID") or os.getenv("SHEET_ID")
        if sheet_id:
            if rows_picks:
                write_rows(sheet_id, os.getenv("GSHEET_PICKS_TAB","PICKS"), "PICKS", rows_picks)
            if rows_parlays:
                write_rows(sheet_id, os.getenv("GSHEET_PARLAY_TAB","PARLAYS"), "PARLAYS", rows_parlays)
    print("OK predict & publish EXTENDED.")

if __name__=="__main__":
    odds_fmt = os.getenv("DEFAULT_ODDS_FORMAT","decimal")
    # Fallback robusto: ENV → Supabase → CFG → 500
    bankroll_default = float(CFG.get("bankroll", 500))
    bankroll = env_float("DEFAULT_BANKROLL", get_bankroll(bankroll_default))
    fraction = env_float("DEFAULT_KELLY_FRACTION", 0.25)
    top = int(os.getenv("DEFAULT_TOP_PICKS", str(CFG.get("top_picks", 5))))
    publish_today(odds_fmt, bankroll, fraction, top)
