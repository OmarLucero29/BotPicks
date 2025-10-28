from dataclasses import dataclass
from typing import Optional

@dataclass
class KellyConfig:
    bankroll: float
    fraction: float = 0.25
    min_pct: float = 0.01
    max_pct: float = 0.10
    brier_floor: float = 0.10
    brier_ceiling: float = 0.25

def _kelly_raw(p: float, odds_dec: float) -> float:
    b = max(odds_dec - 1.0, 1e-9)
    return (b*p - (1-p)) / b

def _brier_scale(brier: Optional[float], floor: float, ceil: float) -> float:
    if brier is None or brier <= floor: return 1.0
    if brier >= ceil: return 0.5
    r = (ceil - brier) / (ceil - floor)
    return 0.5 + 0.5*r

def compute_kelly(p: float, odds_dec: float, cfg: KellyConfig, brier: Optional[float]=None) -> tuple[float,float,float]:
    k = _kelly_raw(p, odds_dec)
    if k <= 0: return 0.0, 0.0, k
    pct = k * cfg.fraction * _brier_scale(brier, cfg.brier_floor, cfg.brier_ceiling)
    pct = max(cfg.min_pct, min(cfg.max_pct, pct))
    return round(cfg.bankroll*pct, 2), pct, k
