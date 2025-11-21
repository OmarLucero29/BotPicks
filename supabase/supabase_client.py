# BotPicks/supabase/supabase_client.py

from typing import Any, Dict, List, Optional
import os
import logging
from datetime import datetime
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("supabase_client")

# Cargar variables desde entorno
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL no está definido en las variables de entorno.")

if not SUPABASE_ANON_KEY:
    logger.warning("SUPABASE_ANON_KEY no está definido. Lecturas públicas pueden fallar.")

if not SUPABASE_SERVICE_ROLE_KEY:
    logger.info("SUPABASE_SERVICE_ROLE_KEY no está definido. Inserciones privilegiadas no estarán disponibles.")


# Instancias del cliente
client_anon: Optional[Client] = None
client_service: Optional[Client] = None


def init_clients():
    """Inicializa los clientes de Supabase (anon y service role)."""
    global client_anon, client_service

    if SUPABASE_ANON_KEY:
        client_anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    if SUPABASE_SERVICE_ROLE_KEY:
        client_service = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


init_clients()


# Utilidad interna
def _timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


##############################################
#  PICKS
##############################################

def insert_pick(pick: Dict[str, Any]) -> Dict[str, Any]:
    """Inserta un pick en la tabla picks usando service role."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    payload = {
        "deporte": pick["deporte"],
        "partido": pick["partido"],
        "mercado": pick["mercado"],
        "pick": pick["pick"],
        "cuota": float(pick.get("cuota", 0)),
        "stake": float(pick.get("stake", 0)),
        "ev": float(pick.get("ev", 0)) if pick.get("ev") is not None else None,
        "meta": pick.get("meta", {})
    }

    res = client_service.table("picks").insert(payload).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data[0]


def get_top_picks(limit: int = 10, deporte: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene los mejores picks ordenados por EV."""
    cli = client_anon or client_service
    if cli is None:
        raise RuntimeError("No hay cliente Supabase disponible.")

    query = cli.table("picks").select("*").order("ev", desc=True).order("fecha", desc=True).limit(limit)

    if deporte:
        query = query.eq("deporte", deporte)

    res = query.execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data


def update_pick_status(pick_id: str, status: str) -> Dict[str, Any]:
    """Actualiza el estado de un pick."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    res = client_service.table("picks").update({"status": status}).eq("id", pick_id).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data[0]


##############################################
#  PARLAYS
##############################################

def insert_parlay(parlay: Dict[str, Any]) -> Dict[str, Any]:
    """Inserta un parlay completo."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    payload = {
        "nombre": parlay.get("nombre"),
        "legs": parlay["legs"],
        "cuota_total": float(parlay.get("cuota_total", 0)),
        "stake": float(parlay.get("stake", 0)),
        "meta": parlay.get("meta", {})
    }

    res = client_service.table("parlays").insert(payload).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data[0]


def get_parlay(parlay_id: str) -> Optional[Dict[str, Any]]:
    cli = client_anon or client_service

    res = cli.table("parlays").select("*").eq("id", parlay_id).limit(1).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data[0] if res.data else None


##############################################
#  GUARDADOS
##############################################

def save_guardado(user_id: str, tipo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Guarda cualquier pick o parlay en el módulo GUARDADOS."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    row = {
        "user_id": user_id,
        "tipo": tipo,
        "payload": payload
    }

    res = client_service.table("guardados").insert(row).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data[0]


def list_guardados(user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    cli = client_anon or client_service

    q = cli.table("guardados").select("*").order("fecha", desc=True).limit(limit)

    if user_id:
        q = q.eq("user_id", user_id)

    res = q.execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data


##############################################
#  CONFIG & KEYS
##############################################

def upsert_key(nombre: str, value: str) -> Dict[str, Any]:
    """Inserta o actualiza una key interna del sistema."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    # Intento de insert
    res = client_service.table("keys").insert({"nombre": nombre, "value": value}).execute()

    # Si falla por duplicado, actualiza
    if res.error:
        existing = client_service.table("keys").select("*").eq("nombre", nombre).execute()

        if existing.data:
            record_id = existing.data[0]["id"]
            update_res = client_service.table("keys").update({"value": value}).eq("id", record_id).execute()

            if update_res.error:
                raise RuntimeError(update_res.error.message)

            return update_res.data[0]

        raise RuntimeError(res.error.message)

    return res.data[0]


def get_config(key: str) -> Optional[Dict[str, Any]]:
    cli = client_anon or client_service

    res = cli.table("config").select("*").eq("key", key).limit(1).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data[0] if res.data else None


def upsert_config(key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    """Inserta o actualiza configuraciones del bot."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    res = client_service.table("config").insert({"key": key, "value": value}).execute()

    if res.error:
        existing = client_service.table("config").select("*").eq("key", key).execute()

        if existing.data:
            update_res = client_service.table("config").update(
                {"value": value, "updated_at": _timestamp()}
            ).eq("key", key).execute()

            if update_res.error:
                raise RuntimeError(update_res.error.message)

            return update_res.data[0]

        raise RuntimeError(res.error.message)

    return res.data[0]


##############################################
#  INGESTA BULK
##############################################

def ingest_bulk_picks(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ingesta masiva de picks desde APIs."""
    if client_service is None:
        raise RuntimeError("Client service role no inicializado.")

    rows = []

    for p in picks:
        rows.append({
            "deporte": p["deporte"],
            "partido": p["partido"],
            "mercado": p["mercado"],
            "pick": p["pick"],
            "cuota": float(p.get("cuota", 0)),
            "stake": float(p.get("stake", 0)),
            "ev": float(p.get("ev", 0)) if p.get("ev") is not None else None,
            "meta": p.get("meta", {})
        })

    res = client_service.table("picks").insert(rows).execute()

    if res.error:
        raise RuntimeError(res.error.message)

    return res.data


##############################################
#  Script test manual
##############################################

if __name__ == "__main__":
    try:
        init_clients()
        print("Supabase inicializado correctamente:", SUPABASE_URL)
    except Exception as e:
        logger.exception("Error al inicializar:", e)
