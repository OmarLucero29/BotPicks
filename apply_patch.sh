#!/usr/bin/env bash
set -euo pipefail

echo "==> Creando estructura de archivos para api_sports_client y adaptadores"

# Directorios
mkdir -p src/ingest tests .github/workflows

# __init__ para que python los trate como paquetes
cat > src/__init__.py <<'PY'
# package marker for src
PY

cat > src/ingest/__init__.py <<'PY'
# package marker for src.ingest
PY

# 1) src/ingest/api_sports_client.py
cat > src/ingest/api_sports_client.py <<'PY'
"""
Cliente centralizado para API-Sports.
Usa UNA sola key (API_SPORTS_KEY) y enruta requests según el deporte.
Incluye reintentos, backoff exponencial básico, y manejo de errores comunes.
"""

import os
import time
import logging
from typing import Dict, Optional, Any
import requests

logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_SPORTS_KEY")
if not API_KEY:
    raise RuntimeError("Falta API_SPORTS_KEY en variables de entorno")

# Mapea el deporte lógico a host (dominios API-Sports por deporte)
SPORT_HOST: Dict[str, str] = {
    "football": "v3.football.api-sports.io",
    "soccer": "v3.football.api-sports.io",
    "basketball": "v1.basketball.api-sports.io",
    "baseball": "v1.baseball.api-sports.io",
    "tennis": "v1.tennis.api-sports.io",
    "hockey": "v1.hockey.api-sports.io",
    "americanfootball": "v1.americanfootball.api-sports.io",
    "mma": "v1.mma.api-sports.io",
}

DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "2"))
HTTP_BACKOFF = float(os.getenv("HTTP_BACKOFF", "0.7"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "BotPicks/1.0")

class APIClientError(Exception):
    pass

def _build_headers() -> Dict[str, str]:
    return {
        "x-apisports-key": API_KEY,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

def _do_get(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    last_exc = None
    for attempt in range(1, HTTP_RETRIES + 2):  # retries + first try
        try:
            resp = requests.get(url, headers=_build_headers(), params=params or {}, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 429:
                wait = HTTP_BACKOFF * (2 ** (attempt - 1))
                logger.warning("Rate limited (%s). Backing off %.2fs (attempt %d).", url, wait, attempt)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            last_exc = e
            status = getattr(e.response, "status_code", None)
            if status and 400 <= status < 500 and status != 429:
                logger.error("HTTP error %s for %s: %s", status, url, e)
                raise APIClientError(f"Request failed {status}: {e}") from e
            wait = HTTP_BACKOFF * (2 ** (attempt - 1))
            logger.warning("HTTP error for %s (attempt %d). Waiting %.2fs and retrying. Error: %s", url, attempt, wait, e)
            time.sleep(wait)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            wait = HTTP_BACKOFF * (2 ** (attempt - 1))
            logger.warning("Connection/Timeout for %s (attempt %d). Waiting %.2fs and retrying. Error: %s", url, attempt, wait, e)
            time.sleep(wait)
    raise APIClientError(f"Failed to GET {url} after {HTTP_RETRIES+1} attempts") from last_exc

def get_for_sport(sport: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Realiza una GET a API-Sports para el deporte solicitado.

    Args:
        sport: clave lógica del deporte, p.ej. 'football', 'basketball'
        path: path que comienza con '/', p.ej. '/fixtures' o '/teams'
        params: query params (dict)

    Returns:
        JSON decodificado (dict) de la respuesta.
    Raises:
        ValueError: si sport no está mapeado.
        APIClientError: fallo persistente en la request.
    """
    key = sport.lower()
    if key not in SPORT_HOST:
        raise ValueError(f"Sport '{sport}' sin host configurado en SPORT_HOST")
    host = SPORT_HOST[key]
    if not path.startswith("/"):
        raise ValueError("path debe comenzar con '/'")
    url = f"https://{host}{path}"
    return _do_get(url, params=params)

def get_fixtures(sport: str, league: Optional[int] = None, season: Optional[int] = None, **extra) -> Dict[str, Any]:
    params = {}
    if league is not None:
        params["league"] = league
    if season is not None:
        params["season"] = season
    params.update(extra)
    return get_for_sport(sport, "/fixtures", params=params)

def get_teams(sport: str, league: Optional[int] = None, season: Optional[int] = None, **extra) -> Dict[str, Any]:
    params = {}
    if league is not None:
        params["league"] = league
    if season is not None:
        params["season"] = season
    params.update(extra)
    return get_for_sport(sport, "/teams", params=params)

if __name__ == "__main__":
    import json
    try:
        r = get_fixtures("football", league=39, season=2025)
        print(json.dumps(r.get("response", [])[:2], indent=2))
    except Exception as e:
        print("Error demo:", e)
PY

# 2) src/ingest/clients.py
cat > src/ingest/clients.py <<'PY'
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
PY

# 3) tests/test_api_sports_client.py
cat > tests/test_api_sports_client.py <<'PY'
import pytest
from unittest import mock

import src.ingest.api_sports_client as client

def test_sport_host_map_contains_football():
    assert "football" in client.SPORT_HOST

def test_get_for_sport_invalid():
    with pytest.raises(ValueError):
        client.get_for_sport("sport_que_no_existe", "/fixtures")

@mock.patch("src.ingest.api_sports_client.requests.get")
def test_do_get_success(mock_get):
    class DummyResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"response": [{"id": 1}]}
    mock_get.return_value = DummyResp()
    res = client.get_for_sport("football", "/fixtures", params={"league": 1})
    assert isinstance(res, dict)
    assert "response" in res
PY

# 4) README_API_SPORTS.md
cat > README_API_SPORTS.md <<'MD'
# API-Sports client (BotPicks)

Este archivo explica cómo usar `src/ingest/api_sports_client.py`.

- Usa UNA variable de entorno: `API_SPORTS_KEY`.
- Llama a la función `get_for_sport(sport, path, params)`:
  - `sport`: 'football', 'basketball', 'baseball', 'tennis', etc.
  - `path`: path del endpoint (ej. '/fixtures')
  - `params`: dict con query params (ej. {"league":39, "season":2025})

Ejemplo:
```py
from src.ingest.api_sports_client import get_fixtures
resp = get_fixtures("football", league=39, season=2025)
