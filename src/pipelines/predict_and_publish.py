# src/pipelines/predict_and_publish.py
# Pipeline minimalista: carga picks → prepara filas → publica a Google Sheets.
# Compatibilidad total con src/pipelines/sheets_append.py y src/common/sheets_io.py

from typing import List, Dict, Any

from src.pipelines.sheets_append import (
    _load_picks,      # carga desde env/archivo
    _format_rows,     # convierte picks a filas destino
    publish_to_sheets # escribe en Google Sheets
)


def run() -> None:
    picks: List[Dict[str, Any]] = _load_picks()
    if not picks:
        print("[INFO] No hay picks para publicar. Termina sin errores.")
        return

    rows = _format_rows(picks)
    if not rows:
        print("[INFO] No se generaron filas válidas. Termina sin errores.")
        return

    publish_to_sheets(rows)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"[ERROR] predict_and_publish falló: {exc}")
        raise