# Pasos de despliegue (GitHub, HF, Supabase, Telegram)

## Telegram
1. @BotFather → /newbot → copia TELEGRAM_BOT_TOKEN.
2. Prueba local: `python bot/telegram_bot.py` y manda /start.

## Supabase
1. Crea proyecto → ejecuta `sql/01_picks.sql`.
2. Copia SUPABASE_URL y SUPABASE_ANON_KEY.

## Google Sheets
1. Crea hoja con tabs: PICKS, PARLAYS, PICKS_GUARDADOS.
2. Comparte con el correo de la service account del JSON que pondrás en GCP_SA_JSON.

## GitHub Actions
1. Crea repo y sube el contenido del zip.
2. Settings → Secrets and variables → Actions:
   - Secrets: SUPABASE_URL, SUPABASE_ANON_KEY, GCP_SA_JSON, GSHEET_ID, PANDASCORE_TOKEN
   - (Opcional) Variables: DEFAULT_* si quieres cambiar por defecto.
3. Habilita los workflows (daily/weekly/monthly) o ejecútalos manual.

## Hugging Face (Space con Docker)
1. Spaces → New Space → SDK: Docker → sube el repo.
2. Settings → Variables (Secrets):
   - TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY, GCP_SA_JSON, GSHEET_ID, PANDASCORE_TOKEN
3. Rebuild del Space → ver logs hasta “polling”.
4. En Telegram, /start al bot.

## Primera corrida (históricos)
- Ejecuta el workflow **Daily Pipeline** o local:
  - `python -m src.pipelines.ingest`
  - `python -m src.pipelines.train_baseline`
  - `python -m src.pipelines.predict_and_publish`
- Verifica en Sheets (PICKS/PARLAYS) y en Supabase (tabla picks).
