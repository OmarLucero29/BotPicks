# src/common/sheets_io.py
import os
import json
import base64
from typing import List, Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _try_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _load_sa_info() -> dict:
    """
    Acepta el secreto tal cual:
      - JSON multilínea pegado (tu caso)
      - JSON con \n escapados
      - Base64 (línea única)
      - Ruta a archivo .json
    """
    raw = os.getenv("GCP_SA_JSON")
    if not raw:
        raise RuntimeError("GCP_SA_JSON no está definido.")

    raw = raw.lstrip("\ufeff")  # quita BOM si existe

    # 0) Si parece JSON (empieza con '{'), intenta tal cual SIN modificar
    trimmed = raw.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        parsed = _try_json(trimmed)
        if parsed is not None:
            return parsed

    # 1) ¿Es Base64?
    try:
        decoded = base64.b64decode(trimmed, validate=True).decode("utf-8-sig")
        parsed = _try_json(decoded.strip())
        if parsed is not None:
            return parsed
    except Exception:
        pass

    # 2) ¿Es ruta a archivo?
    if trimmed.endswith(".json") and os.path.exists(trimmed):
        with open(trimmed, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    # 3) Reparaciones mínimas sobre texto “casi JSON”
    # - Quita comillas envolventes accidentales
    repaired = trimmed
    if repaired and repaired[0] in ("'", '"', "`") and repaired[-1] == repaired[0]:
        repaired = repaired[1:-1]

    # - Reemplaza \\n por saltos reales SOLO dentro del valor de private_key si es necesario
    #   (pero antes probamos una vez más por si ya es válido)
    parsed = _try_json(repaired)
    if parsed is not None:
        return parsed

    # Si aún no parsea, intenta una última reparación:
    # algunos runners entregan todo con backslashes duplicados.
    candidate = repaired.replace("\\n", "\n")
    parsed = _try_json(candidate)
    if parsed is not None:
        return parsed

    # Error claro con snippet seguro (sin exponer todo el secreto)
    snippet = (trimmed[:120]).encode("unicode_escape", "ignore")
    raise RuntimeError(
        "Error parseando GCP_SA_JSON: formato no reconocido. "
        f"Inicio del contenido={snippet}"
    )


def _authorize() -> gspread.Client:
    info = _load_sa_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def write_rows(sheet_id: str, tab: str, rows: List[List[Any]]) -> None:
    if not rows:
        return
    gc = _authorize()
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(tab)
    ws.append_rows(
        rows,
        value_input_option="USER_ENTERED",
        insert_data_option="INSERT_ROWS",
        table_range=None,
    )