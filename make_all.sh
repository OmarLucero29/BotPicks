#!/usr/bin/env bash
set -euo pipefail

echo "🔧 Creando entorno virtual (.venv) y paquetes…"
python3 -m venv .venv
source .venv/bin/activate

# Evita CRLF en CI si el script se subió desde Windows (no es crítico en local)
if command -v sed >/dev/null 2>&1; then
  sed -i 's/\r$//' requirements.txt || true
fi

python -m pip install --upgrade pip

REQ_FILE="${REQ_FILE:-requirements.txt}"
if [ -f "$REQ_FILE" ]; then
  echo "📦 Instalando dependencias desde $REQ_FILE …"
  pip install -r "$REQ_FILE"
else
  echo "⚠️  No encontré $REQ_FILE; continuo sin instalar dependencias."
fi

# Cargar .env si existe (exporta todas las variables)
if [ -f ".env" ]; then
  echo "🔐 Cargando variables desde .env"
  set -a
  . ./.env
  set +a
else
  echo "ℹ️  No hay .env; usa .env.example como referencia o secrets en CI."
fi

# ---------- TU LÓGICA A PARTIR DE AQUÍ ----------
# Ejemplos:
# python scripts/ingest.py
# python scripts/select_picks.py
# bash scripts/build_parlays.sh
echo "✅ make_all.sh completado"
