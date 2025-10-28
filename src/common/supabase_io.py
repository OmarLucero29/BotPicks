import os
from supabase import create_client

def supabase():
    url = os.environ.get("SUPABASE_URL"); key=os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key: 
        raise RuntimeError("Supabase env faltante")
    return create_client(url, key)

def insert_pick(row: dict):
    return supabase().table("picks").insert(row).execute()
