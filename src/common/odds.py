from typing import Literal, Tuple
OddsFormat = Literal["decimal","american","fractional"]

def american_to_decimal(a: float) -> float:
    return 1 + (a/100.0 if a>0 else 100.0/abs(a))
def decimal_to_american(d: float) -> float:
    if d <= 1: raise ValueError("Decimal debe ser > 1")
    return round((d-1)*100) if d>=2 else round(-100/(d-1))
def fractional_to_decimal(n: int, m: int) -> float:
    if m<=0: raise ValueError("Denominador > 0")
    return 1.0 + n/m
def decimal_to_fractional(d: float) -> Tuple[int,int]:
    if d<=1: raise ValueError("Decimal > 1")
    import fractions
    fr = fractions.Fraction(d-1).limit_denominator(1000)
    return fr.numerator, fr.denominator

def to_decimal(value: str, fmt: OddsFormat) -> float:
    v = value.strip().lower()
    if fmt=="decimal": return float(v)
    if fmt=="american": return american_to_decimal(float(v))
    if fmt=="fractional":
        n,m = v.split("/"); return fractional_to_decimal(int(n), int(m))
    raise ValueError("Formato no soportado")

def from_decimal(d: float, fmt: OddsFormat) -> str:
    if fmt=="decimal": return f"{d:.2f}"
    if fmt=="american": return f"{decimal_to_american(d):+d}"
    if fmt=="fractional":
        n,m = decimal_to_fractional(d); return f"{n}/{m}"
    raise ValueError("Formato no soportado")
