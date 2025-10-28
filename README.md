# BotPicks V1.0 EXT (gratis • nube • automático)

## Secrets usados
TELEGRAM_BOT_TOKEN, GSHEET_ID, GCP_SA_JSON, SUPABASE_URL, SUPABASE_ANON_KEY, PANDASCORE_TOKEN.
Opcionales: TELEGRAM_CHAT_ID, SUPABASE_SERVICE_ROLE, GSHEET_PICKS_TAB, GSHEET_PARLAY_TAB, GSHEET_GUARDADOS, GH_PAT, HF_TOKEN.

## Tabs por defecto
PICKS, PARLAYS, PICKS_GUARDADOS (puedes cambiar con GSHEET_*_TAB).

## Comandos locales
pip install -r requirements.txt
python -m src.pipelines.ingest
python -m src.pipelines.train_baseline
python -m src.pipelines.predict_and_publish
python bot/telegram_bot.py
