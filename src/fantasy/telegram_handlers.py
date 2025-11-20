"""
Handlers de Telegram para el flujo Fantasy.
Reglas:
- El perfil (conservador/balanceado/soñador) viene del menú Configuración global (reutiliza CONFIG en Supabase/GSHEET).
- No existe la opción 'generar 3 equipos' (se genera un equipo según perfil activo).
"""

import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from .fantasy import generate_and_store_lineup

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Simple mapping of sport -> default formation rules and budget (adjustable)
DEFAULTS = {
    "futbol": {"formation":{"GK":1,"DEF":4,"MID":4,"FWD":2}, "budget":100.0},
    "basketball": {"formation":{"G":2,"F":3,"C":2}, "budget":50000.0},
    "nfl": {"formation":{"QB":1,"RB":2,"WR":3,"TE":1}, "budget":50000.0},
    # ... añadir reglas por deporte
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Bet365", callback_data="platform:Bet365"),
         InlineKeyboardButton("Draftea", callback_data="platform:Draftea"),
         InlineKeyboardButton("DraftKings", callback_data="platform:DraftKings")],
        [InlineKeyboardButton("Volver", callback_data="menu:main")]
    ]
    await update.message.reply_text("Selecciona plataforma:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("platform:"):
        platform = data.split(":",1)[1]
        # ask sport
        k = []
        row = []
        for idx,s in enumerate(["Futbol","Basketball","NFL","MLB","NHL","Tenis","eSports","F1"]):
            row.append(InlineKeyboardButton(s, callback_data=f"sport:{s.lower()}|{platform}"))
            if (idx+1)%3==0:
                k.append(row); row=[]
        if row: k.append(row)
        k.append([InlineKeyboardButton("Atrás", callback_data="menu:main")])
        await q.edit_message_text(f"Plataforma: {platform}\nElige deporte:", reply_markup=InlineKeyboardMarkup(k))
    elif data.startswith("sport:"):
        payload = data.split(":",1)[1]
        sport, platform = payload.split("|")
        # read user profile from config (for MVP: default 'balanceado')
        profile = "balanceado"
        # Use defaults
        defaults = DEFAULTS.get(sport, {"formation":{"GK":1,"DEF":4,"MID":4,"FWD":2}, "budget":100.0})
        formation = defaults["formation"]
        budget = defaults["budget"]
        # Ask to confirm generate
        kb = [
            [InlineKeyboardButton("Generar equipo (perfil actual)", callback_data=f"generate:{sport}|{platform}|{profile}")],
            [InlineKeyboardButton("Ver plantilla de scoring", callback_data=f"scoring:{sport}|{platform}")],
            [InlineKeyboardButton("Atrás", callback_data="start")]
        ]
        await q.edit_message_text(f"Generar Fantasy para {sport.upper()} en {platform}\nPerfil actual: {profile}", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("generate:"):
        payload = data.split(":",1)[1]
        sport, platform, profile = payload.split("|")
        # For MVP: use today's date and league id placeholder "all"
        date = time.strftime("%Y-%m-%d")
        league_or_event_id = "all"
        defaults = DEFAULTS.get(sport, {"formation":{"GK":1,"DEF":4,"MID":4,"FWD":2}, "budget":100.0})
        formation = defaults["formation"]
        budget = defaults["budget"]
        # send interim message
        await q.edit_message_text("Calculando proyecciones y optimizando alineación...")
        try:
            result = generate_and_store_lineup(sport, league_or_event_id, date, platform, profile, budget, formation, max_same_team=3)
        except Exception as e:
            await q.edit_message_text(f"Error generando alineación: {e}")
            return
        # Build message
        lines = [f"🎯 {platform} — {sport.upper()}",
                 f"Formación (preset) • Coste: {result.get('total_cost')} • Proyección: {result.get('total_points')} pts",
                 f"Perfil: {profile.capitalize()}\n"]
        for p in result.get("selected", []):
            lines.append(f"• {p.name} — {p.position} — {p.projections['points']} pts — Cost: {p.cost}")
        msg = "\n".join(lines)
        kb = [
            [InlineKeyboardButton("Guardar (FANTASY tab)", callback_data="noop")],
            [InlineKeyboardButton("Avísame (monitor)", callback_data="noop"), InlineKeyboardButton("Explicación breve", callback_data="explain:placeholder")],
            [InlineKeyboardButton("Principal", callback_data="menu:main")]
        ]
        await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await q.edit_message_text("Acción no soportada (MVP).")

def build_app():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("fantasy", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    return app

if __name__ == "__main__":
    import time
    app = build_app()
    print("Starting Telegram Fantasy bot (MVP)...")
    app.run_polling()
