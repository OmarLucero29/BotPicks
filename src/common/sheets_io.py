# src/common/sheets_io.py
import os
import json
import base64
from typing import List, Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _load_sa_info() -> dict:
    """
    Carga credenciales GCP de múltiples formatos:
      - JSON multilínea pegado (GitHub Secrets con saltos)
      - JSON con '\n' escapados
      - Base64
      - Ruta a archivo .json
    """
    raw = os.getenv("GCP_SA_JSON")
    if not raw:
        raise RuntimeError("GCP_SA_JSON no está definido.")
    raw = raw.strip().lstrip("\ufeff")

    # Si empieza con { intenta directo (JSON plano)
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except Exception:
            pass

    # Si parece Base64
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8-sig")
        if decoded.strip().startswith("{"):
            return json.loads(decoded)
    except Exception:
        pass

    # Si parece ruta de archivo
    if raw.endswith(".json") and os.path.exists(raw):
        with open(raw, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    # Normaliza saltos: reemplaza secuencias literales '\n' o reales por saltos reales
    cleaned = raw.replace("\\n", "\n").replace('\r\n', '\n')
    # Quita comillas envolventes si las hay
    if (cleaned[0] in ['"', "'"]) and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1]

    # Quita asteriscos o prefijos accidentales (*** etc.)
    cleaned = "\n".join(
        line for line in cleaned.splitlines() if not line.strip().startswith("***")
    ).strip()

    # Intenta parsear de nuevo
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        snippet = cleaned[:200].encode("unicode_escape", "ignore")
        raise RuntimeError(
            f"Error parseando GCP_SA_JSON (línea {e.lineno}, col {e.colno}): {e.msg}\n"
            f"Inicio del contenido={snippet}"
        ) from e


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
    )