import os
def env_str(name: str, default: str|None=None) -> str|None:
    v=os.getenv(name); 
    if v is None: return default
    v=v.strip(); return v if v!='' else default
def env_float(name: str, default: float) -> float:
    v=os.getenv(name)
    if v is None or str(v).strip()=='' : return float(default)
    try: return float(v)
    except: return float(default)
