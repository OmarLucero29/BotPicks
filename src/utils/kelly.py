# src/utils/kelly.py
from __future__ import annotations

def kelly_fraction(p: float, odds_decimal: float, frac: float = 0.25) -> float:
    """
    f* = (b*p - (1-p)) / b   con b = odds-1   (Kelly)
    Luego aplicamos 'frac' (0.125 / 0.25 / 0.5).
    """
    b = max(odds_decimal - 1.0, 1e-9)
    q = 1.0 - p
    f_star = (b * p - q) / b
    return max(0.0, f_star * frac)
