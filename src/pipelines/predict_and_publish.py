# src/pipelines/predict_and_publish.py
# Carga picks → convierte a filas → publica a Google Sheets

from typing import List, Dict, Any

from .sheets_append import (
    _load_picks,
    _format_rows,
    publish_to_sheets,
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