# src/common/sheets_io.py
import os
import re
import json
import base64
from typing import List, Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _between_braces(text: str) -> str | None:
    """Extrae lo que hay entre el primer '{' y el último '}' (incluyéndolos)."""
    if not text:
        return None
    try:
        i = text.index("{")
        j = text.rindex("}")
        return text[i : j + 1]
    except ValueError:
        return None


def _looks_like_json_line(s: str) -> bool:
    """Heurística: una línea JSON suele contener llaves, comillas, coma, o ':'."""
    t = s.strip()
    if not t:
        return False
    if t in ("{", "}", "[", "]"):
        return True
    if t.startswith("{") or t.endswith("}") or t.endswith(","):
        return True
    if t.startswith('"') or t.startswith("'"):
        return True
    if '":' in t or "':" in t or ":" in t:
        return True
    # Permite valores PEM dentro del JSON
    if "-----BEGIN " in t or "-----END " in t:
        return True
    return False


def _super_clean(raw: str) -> str:
    """
    Limpieza agresiva:
    - quita BOM, \r
    - borra líneas con sólo asteriscos (máscaras de GitHub) o ruido
    - recorta a bloque { ... }
    - normaliza \\n a saltos reales sólo cuando conviene
    """
    raw = (raw or "").lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()

    # Si el secret viene entre comillas, quítalas
    if len(raw) >= 2 and raw[0] in ("'", '"') and raw[-1] == raw[0]:
        raw = raw[1:-1].strip()

    # Si tiene secuencias escapadas globales, NO las desescapes aún;
    # primero recorta al bloque JSON y filtra ruido.
    block = _between_braces(raw) or raw

    # Elimina líneas tipo '***' (máscara de secretos) o ruido evidente
    cleaned_lines: list[str] = []
    for line in block.split("\n"):
        s = line.strip()
        if not s:
            continue
        # línea con sólo asteriscos y/o espacios
        if set(s) <= {"*"}:
            continue
        # algunas máscaras imprimen '***\x1b[0m', remueve secuencias ANSI
        s = re.sub(r"\x1b\[[0-9;]*m", "", s).strip()
        # si tras limpiar quedó sólo asteriscos, sáltala
        if set(s) <= {"*"}:
            continue
        # conserva sólo líneas que parecen JSON/PEM
        if _looks_like_json_line(s):
            cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()

    # Si aún no empieza con {, vuelve a intentar con el bloque entre llaves
    block2 = _between_braces(cleaned)
    if block2:
        cleaned = block2.strip()

    # En este punto pueden quedar valores con '\\n' dentro (ej. private_key).
    # Intento 1: parsear tal cual
    try:
        return json.dumps(json.loads(cleaned), ensure_ascii=False)
    except Exception:
        pass

    # Intento 2: reemplazar secuencias \\n por saltos reales (sin tocar otras barras)
    repaired = cleaned.replace("\\n", "\n").replace("\\r", "")
    # Arregla escapes dobles que a veces llegan en private_key
    repaired = repaired.replace("\\\\n", "\n")
    return repaired.strip()


def _parse_secret(raw: str) -> dict:
    """
    Lógica de parseo por etapas:
      1) JSON directo
      2) Base64
      3) Ruta .json
      4) Limpieza agresiva + JSON
    """
    if not raw:
        raise RuntimeError("GCP_SA_JSON no está definido o está vacío.")

    # 1) JSON directo
    first = raw.strip().lstrip("\ufeff")
    if first.startswith("{") and first.endswith("}"):
        try:
            return json.loads(first)
        except Exception:
            pass

    # 2) Base64
    try:
        decoded = base64.b64decode(first, validate=True).decode("utf-8-sig").strip()
        if decoded.startswith("{") and decoded.endswith("}"):
            return json.loads(decoded)
    except Exception:
        pass

    # 3) Ruta a archivo
    if first.endswith(".json") and os.path.exists(first):
        with open(first, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    # 4) Limpieza agresiva
    cleaned = _super_clean(first)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            # último intento: si todavía hay \n escapados, desescapar y reintentar
            try_text = cleaned.replace("\\n", "\n").replace("\\r", "")
            try:
                return json.loads(try_text)
            except Exception:
                snippet = cleaned[:200].encode("unicode_escape", "ignore")
                raise RuntimeError(
                    f"Error parseando GCP_SA_JSON (línea {e.lineno}, col {e.colno}): {e.msg}\n"
                    f"Inicio del contenido={snippet}"
                ) from e

    raise RuntimeError("Formato desconocido en GCP_SA_JSON (no es JSON, Base64 ni ruta a .json).")


def _authorize() -> gspread.Client:
    info = _parse_secret(os.getenv("GCP_SA_JSON", ""))
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