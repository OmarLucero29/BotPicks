---
title: PicksBot
emoji: 🔮
colorFrom: indigo
colorTo: blue
sdk: docker
pinned: false
---

# PicksBot — Gratis • Nube • Automático

Este Space usa **SDK Docker**. El contenedor arranca el bot de Telegram y lee variables desde
Settings → Secrets/Variables del Space: `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`GCP_SA_JSON`, `GSHEET_ID`, `PANDASCORE_TOKEN` (y opcionales `DEFAULT_*`, `GSHEET_*_TAB`).

> No hay UI web; el proceso principal es el bot (long-polling).
