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
