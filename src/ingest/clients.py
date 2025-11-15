"""
Wrapper/adapter que expone funciones de ingestión usando api_sports_client
y fallbacks a proveedores alternativos (p. ej. PandaScore).
"""

import os
import logging
from typing import Dict, Any, Optional

from src.ingest import api_sports_client  # nuevo módulo
import requests

logger = logging.getLogger(__name__)

PANDASCORE_KEY = os.getenv("PANDASCORE_KEY")

def get_sport_fixtures(sport: str, league: Optional[int] = None, season: Optional[int] = None, **kwargs) -> Dict[str, Any]:
    """
    Obtiene fixtures para un deporte. Intenta API-Sports primero; si
    no está disponible o da error, intenta un fallback (si existe).
    """
    try:
        return api_sports_client.get_fixtures(sport, league=league, season=season, **kwargs)
    except ValueError:
        logger.info("Sport %s no mapeado en API-Sports → intentando fallback", sport)
        return _fallback_get_fixtures(sport, league=league, season=season, **kwargs)
    except Exception as e:
        logger.warning("API-Sports fallo para %s: %s. Intentando fallback.", sport, e)
        return _fallback_get_fixtures(sport, league=league, season=season, **kwargs)

def _fallback_get_fixtures(sport: str, **kwargs) -> Dict[str, Any]:
    """
    Implementa fallbacks para deportes no cubiertos por API-Sports.
    Actualmente soporta 'esports' vía PandaScore (si está configurado).
    """
    sport_l = sport.lower()
    if sport_l in ("esports", "efutbol", "efútbol", "esports:valorant", "cs2"):
        if not PANDASCORE_KEY:
            raise RuntimeError("PANDASCORE_KEY no configurado para fallback de esports")
        headers = {"Authorization": f"Bearer {PANDASCORE_KEY}"}
        url = "https://api.pandascore.co/matches"
        resp = requests.get(url, headers=headers, params=kwargs, timeout=int(os.getenv("HTTP_TIMEOUT", "30")))
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"No hay fallback configurado para deporte: {sport}")

def get_teams(sport: str, league: Optional[int] = None, season: Optional[int] = None, **kwargs) -> Dict[str, Any]:
    try:
        return api_sports_client.get_teams(sport, league=league, season=season, **kwargs)
    except Exception:
        return _fallback_get_teams(sport, league=league, season=season, **kwargs)

def _fallback_get_teams(sport: str, **kwargs) -> Dict[str, Any]:
    raise RuntimeError("Fallback get_teams no implementado para %s" % sport)
