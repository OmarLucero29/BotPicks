# src/bot/handlers.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict

def main_menu_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("Top Picks", callback_data="top_picks")],
        [InlineKeyboardButton("Parlay Segurito", callback_data="parlay_segurito"),
         InlineKeyboardButton("Parlay Soñador", callback_data="parlay_sonador")],
        [InlineKeyboardButton("Fantasy", callback_data="fantasy"),
         InlineKeyboardButton("Deportes", callback_data="deportes")],
        [InlineKeyboardButton("Autoevaluación", callback_data="autoevaluacion"),
         InlineKeyboardButton("Configuración", callback_data="configuracion")]
    ]
    return InlineKeyboardMarkup(kb)

def pick_card_text(pick: Dict) -> str:
    partido = pick.get('partido') or f"{pick.get('home','')} vs {pick.get('away','')}"
    mercado = pick.get('mercado', '1X2')
    cuota = pick.get('cuota', '')
    stake = pick.get('stake', '')
    ev = pick.get('ev', '')
    explain = pick.get('explain', '')
    lines = [
        f"⚽ {partido}",
        f"Mercado: {mercado}  •  Cuota: {cuota}  •  Stake: {stake}  •  EV: {ev}",
        "",
        explain[:900]
    ]
    return "\n".join([l for l in lines if l])

def pick_buttons(pick_id: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("Avisame", callback_data=f"avisame|{pick_id}"),
         InlineKeyboardButton("Guardar", callback_data=f"guardar|{pick_id}")],
        [InlineKeyboardButton("Principal", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(kb)
