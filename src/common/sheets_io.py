# src/common/sheets_io.py
import os
import json
import base64
from typing import List, Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _clean_secret(raw: str) -> str:
    """Limpia caracteres, saltos y líneas basura (***, etc.) del Secret."""
    if not raw:
        return raw
    raw = raw.strip().lstrip("\ufeff")
    # Si hay líneas con *** o vacías al inicio, elimínalas
    lines = []
    for line in raw.splitlines():
        if line.strip().startswith("***"):
            continue
        if line.strip() == "":
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    # Quita comillas envolventes si existen
    if (cleaned[0] in ["'", '"']) and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1]
    # Normaliza secuencias de escape
    cleaned = cleaned.replace("\\n", "\n").replace("\\r", "").strip()
    return cleaned


def _load_sa_info() -> dict:
    """
    Carga credenciales GCP soportando:
      - JSON multilínea (pegado directamente en Secret)
      - JSON con \n escapados
      - Base64
      - Ruta a archivo
    """
    raw = os.getenv("GCP_SA_JSON")
    if not raw:
        raise RuntimeError("GCP_SA_JSON no está definido o está vacío.")

    raw = _clean_secret(raw)

    # 1. Intento directo como JSON
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except Exception:
            pass

    # 2. Intento Base64
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8-sig").strip()
        if decoded.startswith("{"):
            return json.loads(decoded)
    except Exception:
        pass

    # 3. Si es ruta a archivo
    if raw.endswith(".json") and os.path.exists(raw):
        with open(raw, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    # 4. Último intento: limpiar más profundamente
    candidate = _clean_secret(raw)
    if candidate.startswith("{"):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            snippet = candidate[:200].encode("unicode_escape", "ignore")
            raise RuntimeError(
                f"Error parseando GCP_SA_JSON (línea {e.lineno}, col {e.colno}): {e.msg}\n"
                f"Inicio del contenido={snippet}"
            ) from e

    # 5. Si no es JSON ni Base64 ni archivo
    raise RuntimeError("Formato desconocido en GCP_SA_JSON.")


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