import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from src.common.settings import get_bankroll, set_setting

load_dotenv()

def config_keyboard(current_bank: float):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Bank actual: {int(current_bank)}", callback_data="noop")],
        [
            InlineKeyboardButton("300", callback_data="bank:300"),
            InlineKeyboardButton("500", callback_data="bank:500"),
            InlineKeyboardButton("1000", callback_data="bank:1000"),
            InlineKeyboardButton("2000", callback_data="bank:2000")
        ],
        [InlineKeyboardButton("Ingresar valor personalizado", callback_data="bank:custom")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("BotPicks en línea ✅\nUsa /config para abrir Configuración.")

async def config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bank = get_bankroll()
    await update.message.reply_text("⚙️ Configuración\nAjusta tu Bank inicial:", reply_markup=config_keyboard(bank))

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data.startswith("bank:"):
        val = data.split(":",1)[1]
        if val == "custom":
            await q.message.reply_text("Escribe el valor de Bank inicial (solo números), ej: 750")
            context.user_data["await_bank"] = True
            return
        try:
            set_setting("bankroll", float(val))
            await q.message.reply_text(f"✅ Bank inicial actualizado a {val}")
        except Exception:
            await q.message.reply_text("❌ No pude guardar el bank. Intenta de nuevo.")
        # Refresca el menú
        bank = get_bankroll()
        await q.message.reply_text("⚙️ Configuración", reply_markup=config_keyboard(bank))

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_bank"):
        txt = (update.message.text or "").strip()
        if txt.isdigit() or txt.replace(".","",1).isdigit():
            try:
                set_setting("bankroll", float(txt))
                await update.message.reply_text(f"✅ Bank inicial actualizado a {txt}")
            except Exception:
                await update.message.reply_text("❌ No pude guardar el bank. Intenta de nuevo.")
        else:
            await update.message.reply_text("Ingresa un número válido, ej: 750")
        context.user_data["await_bank"] = False
        # mostrar menú otra vez
        bank = get_bankroll()
        await update.message.reply_text("⚙️ Configuración", reply_markup=config_keyboard(bank))

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config_menu))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()

if __name__ == "__main__":
    main()
