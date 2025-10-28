from __future__ import annotations
import json
from typing import Any
from src.common.env import env_float
from src.common.supabase_io import supabase

def get_setting(key: str, default: Any | None = None) -> Any:
    try:
        data = supabase().table("settings").select("value").eq("key", key).limit(1).execute()
        items = getattr(data, "data", []) or []
        if not items:
            return default
        return items[0].get("value", default)
    except Exception:
        return default

def set_setting(key: str, value: Any) -> None:
    try:
        s = supabase()
        # upsert
        s.table("settings").upsert({"key": key, "value": str(value)}).execute()
    except Exception:
        pass

def get_bankroll(default_cfg: float = 500.0) -> float:
    # ENV (robusto) → Supabase → config.json (se lo pasas como default) → 500
    from src.common.env import env_float
    v_env = env_float("DEFAULT_BANKROLL", default_cfg)
    if v_env != default_cfg:
        return float(v_env)
    v_db = get_setting("bankroll", None)
    if v_db is not None:
        try:
            return float(v_db)
        except Exception:
            pass
    return float(default_cfg)
