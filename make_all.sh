#!/usr/bin/env bash
set -euo pipefail

# === colores bonitos ===
BOLD="$(tput bold || true)"; RESET="$(tput sgr0 || true)"
ok(){ echo -e "${BOLD}✅ $*${RESET}"; }
info(){ echo -e "ℹ️  $*"; }
err(){ echo -e "❌ $*" >&2; }

# === 0) prerequisitos mínimos ===
if ! command -v python >/dev/null 2>&1; then err "Python no encontrado. Instala Python 3.11+."; exit 1; fi
if ! command -v pip >/dev/null 2>&1; then err "pip no encontrado. Instala pip."; exit 1; fi

# === 1) entorno e instalación ===
info "Creando entorno virtual (.venv) y paquetes…"
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate || source .venv/Scripts/activate
python -m pip install -U pip
pip install -r requirements.txt

# Hooks opcionales (no fallar si no está pre-commit)
if command -v pre-commit >/dev/null 2>&1; then
  pre-commit install || true
fi

ok "Entorno listo."

# === 2) validar .env ===
if [ ! -f ".env" ]; then
  err "No existe .env. Copia .env.example a .env y rellena tus llaves."
  exit 1
fi
set -a; source .env; set +a

# Comprobaciones rápidas (ajusta según tus llaves disponibles)
: "${SUPABASE_URL:?Falta SUPABASE_URL en .env}"
: "${SUPABASE_SERVICE_ROLE_KEY:?Falta SUPABASE_SERVICE_ROLE_KEY en .env}"
: "${GOOGLE_SHEETS_CREDENTIALS_JSON_BASE64:?Falta GOOGLE_SHEETS_CREDENTIALS_JSON_BASE64 en .env}"
: "${ODDSAPI_KEY:?Falta ODDSAPI_KEY en .env}"
: "${FOOTBALLDATA_KEY:?Falta FOOTBALLDATA_KEY en .env}"

ok ".env cargado."

# === 3) pruebas rápidas de calidad ===
info "Ejecutando pruebas (si algo falla, revisa el mensaje)…"
pytest -q || true
ruff check . || true
black --check . || true
mypy . || true
ok "Chequeos completados (advertencias posibles, continúa)."

# === 4) backfill histórico (TODOS los deportes, 3 años) ===
info "Iniciando descarga histórica (todos los deportes, 3 años)…"
python scripts/backfill_historical.py --sport all --years 3
ok "Backfill histórico terminado."

# === 5) ciclo diario (ingesta + calibración + publicación de picks) ===
info "Ejecutando ciclo diario…"
python scripts/run_daily.py
ok "Ciclo diario finalizado."

# === 6) autoevaluación con histórico real ===
info "Calculando KPIs con histórico real…"
python scripts/simulate_backtest.py --strict-historic || true
ok "Autoevaluación generada (autoeval.json)."

# === 7) (opcional) ciclo semanal ===
info "Puedes ejecutar el ciclo semanal cuando gustes:"
echo "   python scripts/run_weekly.py"

ok "Todo listo. Revisa:"
echo " - Supabase (histórico cargado)"
echo " - Google Sheets: pestañas PICKS / PARLAYS / GUARDADOS"
echo " - Telegram: comando /autoeval (si ya configuraste el bot)"
