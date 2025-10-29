# src/common/sheets_io.py
import os
import io
import json
import base64
from typing import List, Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _load_sa_info() -> dict:
    """
    Carga la key del Service Account desde:
    - GCP_SA_JSON en Base64 (recomendado para CI)
    - GCP_SA_JSON como JSON plano (con o sin \n escapados, con o sin BOM/quotes)
    - GCP_SA_JSON apuntando a una ruta *.json existente
    """
    raw = (os.getenv("GCP_SA_JSON") or "").strip()
    if not raw:
        raise RuntimeError("GCP_SA_JSON está vacío o no definido.")

    # 1) ¿Es Base64?
    try:
        decoded = base64.b64decode(raw, validate=True)
        text = decoded.decode("utf-8-sig").strip()
        if text.startswith("{") and text.endswith("}"):
            return json.loads(text)
    except Exception:
        pass

    # 2) ¿Es ruta a archivo?
    if raw.endswith(".json") and os.path.exists(raw):
        with open(raw, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    # 3) ¿Es JSON plano? Limpia posibles quotes envolventes y BOM
    cleaned = raw
    if cleaned and cleaned[0] in ("'", '"', "`") and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1]
    # Reemplaza \n escapados por saltos reales, y quita BOM si existe
    cleaned = cleaned.replace("\\n", "\n").lstrip("\ufeff").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        snippet = cleaned[:80].encode("unicode_escape", "ignore")
        raise RuntimeError(
            f"Error parseando GCP_SA_JSON: {e}. Inicio del contenido={snippet}"
        ) from e


def _authorize() -> gspread.Client:
    info = _load_sa_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def write_rows(sheet_id: str, tab: str, rows: List[List[Any]]) -> None:
    """
    Append de filas en una hoja específica.
    - sheet_id: ID del Google Sheet
    - tab: nombre de la pestaña
    - rows: lista de filas (listas)
    """
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