from dataclasses import dataclass
@dataclass
class KellyConfig:
    bankroll: float
    fraction: float = 0.25
    min_pct: float = 0.01
    max_pct: float = 0.10
def compute_kelly(p: float, dec_odds: float, cfg: KellyConfig) -> float:
    b=dec_odds-1.0
    k=(p*b - (1-p))/b if b>0 else 0.0
    k=max(0.0,k)*cfg.fraction
    k=min(max(k, cfg.min_pct), cfg.max_pct)
    return round(cfg.bankroll*k, 2)
