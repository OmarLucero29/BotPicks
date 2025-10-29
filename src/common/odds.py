def from_decimal(dec: float):
    return {'decimal': dec, 'american': round((dec-1)*100) if dec>=2 else round(-100/(dec-1))}
