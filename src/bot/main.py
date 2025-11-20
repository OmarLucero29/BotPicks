# src/bot/main.py
"""
BotPicks - Bot Telegram (config editor with message cleanup; single 'Volver' at end of picks)
- Al pulsar Configuración, abre la preview y envía un mensaje independiente por cada parámetro.
- Guarda message_ids de la preview+parámetros+acciones y los borra al Guardar/Cancelar/Reset.
- Quita el bloque "Configuración (interactiva)" de la preview.
- Cada pick ya no incluye un botón 'Volver'; ese botón aparece únicamente en el mensaje final.
"""

import os
import uuid
import random
from datetime import datetime, timezone
from fractions import Fraction
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from typing import Dict, List, Optional, Tuple

# Supabase optional
try:
    from supabase import create_client
    _HAS_SUPABASE = True
except Exception:
    _HAS_SUPABASE = False

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

sb = None
if _HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        sb = None

# -------------------------
# Defaults & cache
# -------------------------
DEFAULT_CONFIG = {
    "use_climate": "false",
    "top_picks_count": "5",
    "parlay_seg_target": "1.8",
    "parlay_so_target": "10.0",
    "recalibration_daily": "02:30",
    "max_parlay_legs": "6",
    "notify_on_new_pick": "true",
    "pick_format": "A",
    "odds_format": "decimal",
}
CONFIG_CACHE: Dict[str, str] = {}

SPORT_EMOJI = {
    "soccer": "⚽",
    "basketball": "🏀",
    "baseball": "⚾",
    "tennis": "🎾",
    "hockey": "🏒",
    "football": "🏈",
    "box": "🥊",
    "mma": "🥋",
    "f1": "🏎️",
    "esports": "🎮",
    "pingpong": "🏓",
    "efutbol": "🎮⚽",
}

# -------------------------
# DB / Config helpers
# -------------------------
def fetch_config() -> Dict[str, str]:
    global CONFIG_CACHE
    if sb:
        try:
            res = sb.table("config").select("*").execute()
            rows = res.data or []
            cfg = DEFAULT_CONFIG.copy()
            for r in rows:
                key = r.get("key") or r.get("name")
                val = r.get("value") or r.get("val")
                if key:
                    cfg[key] = str(val)
            CONFIG_CACHE = cfg.copy()
            return cfg
        except Exception:
            pass
    if not CONFIG_CACHE:
        CONFIG_CACHE = DEFAULT_CONFIG.copy()
    return CONFIG_CACHE

def set_config_key(key: str, value: str) -> bool:
    key = str(key)
    value = str(value)
    if sb:
        try:
            existing = sb.table("config").select("*").eq("key", key).limit(1).execute()
            if existing.data:
                sb.table("config").update({"value": value}).eq("key", key).execute()
            else:
                sb.table("config").insert({"id": str(uuid.uuid4()), "key": key, "value": value}).execute()
            CONFIG_CACHE[key] = value
            return True
        except Exception:
            CONFIG_CACHE[key] = value
            return False
    else:
        CONFIG_CACHE[key] = value
        return False

# -------------------------
# Picks (DB or Mock)
# -------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def gen_mock_pick(sport: str, idx: int = 0) -> Dict:
    teams = {
        "soccer": [("Real Madrid","FC Barcelona"),("Atletico","Sevilla")],
        "efutbol": [("eTeamA","eTeamB")],
        "basketball": [("LAL","BOS")],
        "tennis": [("Nadal","Djokovic")],
        "mma": [("FighterA","FighterB")],
        "f1": [("Verstappen","Leclerc")],
    }
    pair = teams.get(sport, [("A","B")])[idx % len(teams.get(sport, [("A","B")]))]
    partido = f"{pair[0]} vs {pair[1]}"
    cuota = round(random.uniform(1.5, 3.75), 2)
    stake = round(random.uniform(1.0, 5.0), 1)
    ev = round(random.uniform(-5.0, 8.0), 1)
    league = {
        "soccer": "LaLiga",
        "efutbol": "eFootball League",
        "basketball": "NBA",
        "tennis": "ATP",
        "mma": "UFC",
        "f1": "F1",
    }.get(sport, "Exhibition")
    stadium = {
        "Real Madrid vs FC Barcelona": "Santiago Bernabéu"
    }.get(partido, "—")
    climate = {"temp": f"{random.randint(10,30)}°C", "desc": random.choice(["Soleado","Nublado","Lluvia ligera"]) }
    return {
        "id": str(uuid.uuid4()),
        "fecha": now_iso(),
        "deporte": sport,
        "partido": partido,
        "mercado": "Over/Under 2.5",
        "pick": "Over 2.5",
        "cuota": cuota,
        "stake": stake,
        "ev": ev,
        "league": league,
        "stadium": stadium,
        "climate": climate,
        "explanation": "Mock: ventaja por forma y localía"
    }

def gen_mock_picks_for_sport(sport: str, n: int = 5) -> List[Dict]:
    return [gen_mock_pick(sport, i) for i in range(n)]

def fetch_top_picks(limit: int = 5) -> List[Dict]:
    cfg = fetch_config()
    limit = int(limit)
    if sb:
        try:
            res = sb.table("picks").select("*").order("fecha", desc=True).limit(limit).execute()
            rows = res.data or []
            if rows:
                return rows
        except Exception:
            pass
    picks = []
    for s in ["soccer","efutbol","basketball","tennis","mma","f1"]:
        picks.extend(gen_mock_picks_for_sport(s, 2))
    picks = sorted(picks, key=lambda r: float(r.get("ev",0)), reverse=True)
    return picks[:limit]

def fetch_pick_by_id(pid: str) -> Optional[Dict]:
    if sb:
        try:
            res = sb.table("picks").select("*").eq("id", pid).limit(1).execute()
            return (res.data or [None])[0]
        except Exception:
            return None
    return None

def insert_guardado(user_id: str, pick_rec: Dict) -> bool:
    if not sb:
        return False
    try:
        rec = {
            "id": str(uuid.uuid4()),
            "fecha": now_iso(),
            "deporte": pick_rec.get("deporte"),
            "partido": pick_rec.get("partido"),
            "mercado": pick_rec.get("mercado"),
            "pick": pick_rec.get("pick"),
            "cuota": pick_rec.get("cuota"),
            "stake": pick_rec.get("stake"),
            "user_id": str(user_id)
        }
        sb.table("guardados").insert(rec).execute()
        return True
    except Exception:
        return False

# -------------------------
# Formatting & odds conversion
# -------------------------
def ev_emoji_and_text(ev_value) -> Tuple[str, str]:
    try:
        ev = float(ev_value)
    except Exception:
        return "⚪", f"{ev_value}"
    if ev > 2.0:
        return "🟢", f"+{ev}%"
    if ev > 0.0:
        return "🟡", f"+{ev}%"
    if ev == 0:
        return "🟡", f"{ev}%"
    return "🔴", f"{ev}%"

def friendly_date(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%d-%b-%Y %H:%M UTC")
    except Exception:
        return iso_str[:19].replace("T"," ")

def format_odds(odds_value, odds_format: str) -> str:
    try:
        dec = float(odds_value)
    except Exception:
        return str(odds_value)
    if dec <= 1.0:
        return f"{dec:.2f}"
    if odds_format == "decimal":
        return f"{dec:.2f}"
    if odds_format == "fractional":
        try:
            frac = Fraction(dec - 1).limit_denominator(1000)
            if frac.numerator == 0:
                return f"{dec:.2f}"
            return f"{frac.numerator}/{frac.denominator}"
        except Exception:
            return f"{dec:.2f}"
    if odds_format == "american":
        try:
            if dec >= 2.0:
                val = (dec - 1) * 100.0
                am = int(round(val))
                return f"+{am}"
            else:
                denom = (dec - 1)
                if denom == 0:
                    return "—"
                val = 100.0 / denom
                am = int(round(val))
                return f"-{am}"
        except Exception:
            return f"{dec:.2f}"
    return f"{dec:.2f}"

# Format A, B, C (renderers)
def format_pick_A(rec: Dict, cfg: Dict) -> str:
    sport_emoji = SPORT_EMOJI.get(rec.get("deporte"), "🔹")
    partido = rec.get("partido", "—")
    league = rec.get("league") or ""
    header = f"{sport_emoji} <b>{partido}</b>"
    if league:
        header += f"  <i>({league})</i>"
    fecha = friendly_date(rec.get("fecha"))
    stadium = rec.get("stadium") or "—"
    climate_text = "—"
    if str(cfg.get("use_climate","false")).lower() in ("true","1","yes"):
        c = rec.get("climate")
        if isinstance(c, dict):
            climate_text = f"{c.get('desc','')} {c.get('temp','')}"
        else:
            climate_text = c or "—"
    mercado = rec.get("mercado","—")
    pick = rec.get("pick","—")
    odds_fmt = cfg.get("odds_format","decimal")
    cuota = format_odds(rec.get("cuota","—"), odds_fmt)
    stake = rec.get("stake","—")
    ev_val = rec.get("ev","—")
    ev_icon, ev_text = ev_emoji_and_text(ev_val)
    explanation = rec.get("explanation","").strip()
    text = (
        f"{header}\n\n"
        f"📅 {fecha}   🏟️ {stadium}   ☁️ {climate_text}\n\n"
        f"📊 <b>Mercado:</b> {mercado}\n\n"
        f"✅ <b>Pick:</b> {pick}\n\n"
        f"💰 <b>Cuota:</b> {cuota}   🎯 <b>Stake:</b> {stake}%   📈 <b>EV:</b> {ev_text} {ev_icon}\n\n"
    )
    if explanation:
        text += f"<i>{explanation}</i>\n\n"
    return text

def format_pick_B(rec: Dict, cfg: Dict) -> str:
    sport_emoji = SPORT_EMOJI.get(rec.get("deporte"), "🔹")
    partido = rec.get("partido", "—")
    league = rec.get("league") or ""
    header = f"🏆 {sport_emoji} <b>{partido}</b>"
    if league:
        header += f"  <i>({league})</i>"
    fecha = friendly_date(rec.get("fecha"))
    stadium = rec.get("stadium") or "—"
    climate_text = "—"
    if str(cfg.get("use_climate","false")).lower() in ("true","1","yes"):
        c = rec.get("climate")
        if isinstance(c, dict):
            climate_text = f"{c.get('desc','')} {c.get('temp','')}"
        else:
            climate_text = c or "—"
    cuota = format_odds(rec.get("cuota","—"), cfg.get("odds_format","decimal"))
    pick = rec.get("pick","—")
    stake = rec.get("stake","—")
    ev_val = rec.get("ev","—")
    ev_icon, ev_text = ev_emoji_and_text(ev_val)
    explanation = rec.get("explanation","").strip()
    text = (
        f"{header}\n\n"
        f"🗓️ {fecha}\n"
        f"🏟️ {stadium}   ☁️ {climate_text}\n\n"
        f"📈 <b>Mercado:</b> {rec.get('mercado','—')}\n"
        f"✅ <b>Pick:</b> {pick}\n\n"
        f"💵 <b>Cuota:</b> {cuota}   🎯 <b>Stake:</b> {stake}%\n"
        f"📊 <b>EV:</b> {ev_text} {ev_icon}\n\n"
    )
    if explanation:
        text += f"📝 {explanation}\n\n"
    return text

def format_pick_C(rec: Dict, cfg: Dict) -> str:
    partido = rec.get("partido", "—")
    league = rec.get("league") or ""
    header = f"⚽ {partido}"
    if league:
        header += f"  ({league})"
    fecha = friendly_date(rec.get("fecha"))
    stadium = rec.get("stadium") or "—"
    climate_text = "—"
    if str(cfg.get("use_climate","false")).lower() in ("true","1","yes"):
        c = rec.get("climate")
        if isinstance(c, dict):
            climate_text = f"{c.get('desc','')} {c.get('temp','')}"
        else:
            climate_text = c or "—"
    cuota = format_odds(rec.get("cuota","—"), cfg.get("odds_format","decimal"))
    pick = rec.get("pick","—")
    stake = rec.get("stake","—")
    ev_val = rec.get("ev","—")
    ev_icon, ev_text = ev_emoji_and_text(ev_val)
    kpis = rec.get("kpis","xG:—")
    text = (
        f"{header}  —  {fecha}\n\n"
        f"[Estadio: {stadium}] [Clima: {climate_text}]\n\n"
        f"Pick: <b>{pick}</b>  |  Cuota: <b>{cuota}</b>  |  Stake: <b>{stake}%</b>  |  EV: <b>{ev_text} {ev_icon}</b>\n\n"
        f"KPIs: {kpis}\n\n"
    )
    return text

def render_pick_by_format(rec: Dict, cfg: Dict) -> str:
    fmt = str(cfg.get("pick_format","A")).upper()
    if fmt == "A":
        return format_pick_A(rec, cfg)
    if fmt == "B":
        return format_pick_B(rec, cfg)
    if fmt == "C":
        return format_pick_C(rec, cfg)
    return format_pick_A(rec, cfg)

# -------------------------
# Config UI helpers
# -------------------------
def friendly_label(key: str) -> str:
    mapping = {
        "use_climate": "Clima",
        "top_picks_count": "Top picks",
        "parlay_seg_target": "Objetivo Parlay Segurito",
        "parlay_so_target": "Objetivo Parlay Soñador",
        "recalibration_daily": "Hora recalibración diaria",
        "max_parlay_legs": "Máx legs parlay",
        "notify_on_new_pick": "Notificar picks nuevos",
        "pick_format": "Formato Pick",
        "odds_format": "Formato Momio",
    }
    return mapping.get(key, key)

def _is_bool_like(v: str) -> bool:
    return str(v).lower() in ("true","false","1","0","yes","no")

def _is_numeric_like(v: str) -> bool:
    try:
        float(v)
        return True
    except Exception:
        return False

def build_param_text_and_kb(key: str, value: str) -> Tuple[str, InlineKeyboardMarkup]:
    lbl = friendly_label(key)
    text = f"<b>{lbl}</b>\nClave: <code>{key}</code>\nValor actual: <b>{value}</b>\n\n"
    kb = []

    if key == "pick_format":
        row = []
        for opt in ("A","B","C"):
            mark = "✅" if str(value).upper() == opt else ""
            row.append(InlineKeyboardButton(f"{opt} {mark}", callback_data=f"cfg_set::{key}::{opt}"))
        kb.append(row)
        kb.append([InlineKeyboardButton("✏️ Editar texto", callback_data=f"cfg_edit_text::{key}")])

    elif key == "odds_format":
        row = []
        for opt, label in (("decimal","Decimal"), ("fractional","Frac"), ("american","Amér")):
            mark = "✅" if str(value).lower() == opt else ""
            row.append(InlineKeyboardButton(f"{label} {mark}", callback_data=f"cfg_set::{key}::{opt}"))
        kb.append(row)
        kb.append([InlineKeyboardButton("✏️ Editar texto", callback_data=f"cfg_edit_text::{key}")])

    elif _is_bool_like(value):
        kb.append([
            InlineKeyboardButton("✅ Activar", callback_data=f"cfg_set::{key}::true"),
            InlineKeyboardButton("❌ Desactivar", callback_data=f"cfg_set::{key}::false"),
        ])
        kb.append([InlineKeyboardButton("✏️ Editar texto", callback_data=f"cfg_edit_text::{key}")])

    elif _is_numeric_like(value):
        try:
            step = 1 if float(value).is_integer() else 0.1
        except Exception:
            step = 1
        kb.append([
            InlineKeyboardButton("➖", callback_data=f"cfg_inc::{key}::{-step}"),
            InlineKeyboardButton(f"{value}", callback_data=f"cfg_none::{key}"),
            InlineKeyboardButton("➕", callback_data=f"cfg_inc::{key}::{step}"),
        ])
        kb.append([InlineKeyboardButton("✏️ Editar texto", callback_data=f"cfg_edit_text::{key}")])

    else:
        kb.append([InlineKeyboardButton("✏️ Editar", callback_data=f"cfg_edit_text::{key}")])

    return text, InlineKeyboardMarkup(kb)

def build_final_config_actions_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("💾 Guardar", callback_data="cfg_save::0"),
         InlineKeyboardButton("❌ Cancelar", callback_data="cfg_cancel::0")],
        [InlineKeyboardButton("🔁 Reset defaults", callback_data="cfg_reset::0"),
         InlineKeyboardButton("🔙 Menú", callback_data="main")],
    ]
    return InlineKeyboardMarkup(kb)

# -------------------------
# Handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("BotPicks — Menú principal", reply_markup=main_keyboard())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    await query.answer()
    cfg = fetch_config()

    if data in ("main", "back"):
        await query.edit_message_text("Menú principal", reply_markup=main_keyboard())
        return

    # SEND TOP PICKS: each pick as independent message; no Volver per pick
    if data == "top":
        cfg = fetch_config()
        try:
            count = int(cfg.get("top_picks_count", DEFAULT_CONFIG["top_picks_count"]))
        except Exception:
            count = 5
        picks = fetch_top_picks(limit=count)
        if not picks:
            await query.edit_message_text("No hay picks disponibles.", reply_markup=main_keyboard())
            return
        try:
            await query.edit_message_text(f"Enviando {len(picks)} picks...", reply_markup=main_keyboard())
        except Exception:
            pass
        for p in picks:
            text = render_pick_by_format(p, cfg)
            kb = pick_action_keyboard_for_index(p.get("id"))
            try:
                await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                try:
                    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
                except Exception:
                    pass
        # final message with Volver
        try:
            await query.message.reply_text("Fin de la lista de picks.", reply_markup=back_main_keyboard())
        except Exception:
            try:
                await query.edit_message_text("Fin de la lista de picks.", reply_markup=back_main_keyboard())
            except Exception:
                pass
        return

    # Parlay flows (kept as before)
    if data == "parlay_seg":
        await query.edit_message_text("Parlay Segurito (demo) — elige objetivo:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1.5", callback_data="parseg::1.5"),
             InlineKeyboardButton("1.8", callback_data="parseg::1.8"),
             InlineKeyboardButton("2.0", callback_data="parseg::2.0")],
            [InlineKeyboardButton("🔙 Volver", callback_data="main")]
        ]))
        return
    if data and data.startswith("parseg::"):
        target = float(data.split("::",1)[1])
        picks = fetch_top_picks(limit=40)
        chosen, prod = [], 1.0
        for p in sorted(picks, key=lambda r: float(r.get("cuota",1.0))):
            if len(chosen) >= int(fetch_config().get("max_parlay_legs", "6")): break
            chosen.append(p)
            prod *= float(p.get("cuota",1.0))
            if prod >= target: break
        text = "<b>Parlay Segurito (demo)</b>\n"
        for c in chosen:
            text += f"- {c.get('partido')} | {c.get('pick')} | cuota: {c.get('cuota')}\n"
        text += f"\nMomio estimado: {round(prod,3)}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_main_keyboard())
        return
    if data == "parlay_so":
        picks = fetch_top_picks(limit=120)
        high = sorted([p for p in picks if float(p.get("cuota",1))>=1.8], key=lambda r: float(r.get("cuota",1)), reverse=True)
        chosen = high[:6] or picks[:6]
        prod = 1.0
        for c in chosen: prod *= float(c.get("cuota",1.0))
        text = "<b>Parlay Soñador (demo)</b>\n"
        for c in chosen:
            text += f"- {c.get('partido')} | {c.get('pick')} | cuota: {c.get('cuota')}\n"
        text += f"\nMomio estimado: {round(prod,3)}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_main_keyboard())
        return

    if data == "reto":
        await query.edit_message_text("Reto Escalera — envía tu bank inicial (ej: 100).", reply_markup=back_main_keyboard())
        context.user_data["expecting_reto_init"] = True
        return

    if data == "fantasy":
        await query.edit_message_text("Fantasy (demo) — en construcción.", reply_markup=back_main_keyboard())
        return

    if data == "deportes":
        enabled = list(SPORT_EMOJI.keys())
        kb = []
        for s in enabled:
            kb.append([InlineKeyboardButton(f"{SPORT_EMOJI.get(s,'🔹')} {s.capitalize()}", callback_data=f"deporte::{s}")])
        kb.append([InlineKeyboardButton("🔙 Volver", callback_data="main")])
        await query.edit_message_text("Selecciona deporte:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data and data.startswith("deporte::"):
        sport = data.split("::",1)[1]
        picks = []
        if sb:
            try:
                picks = sb.table("picks").select("*").eq("deporte", sport).order("fecha", desc=True).limit(40).execute().data or []
            except Exception:
                picks = []
        if not picks:
            picks = gen_mock_picks_for_sport(sport, 6)
        cfg = fetch_config()
        try:
            await query.edit_message_text(f"Enviando {len(picks)} picks de {sport}...", reply_markup=back_main_keyboard())
        except Exception:
            pass
        for p in picks:
            text = render_pick_by_format(p, cfg)
            kb = pick_action_keyboard_for_index(p.get("id"))
            try:
                await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                try:
                    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
                except Exception:
                    pass
        try:
            await query.message.reply_text("Fin de la lista de picks.", reply_markup=back_main_keyboard())
        except Exception:
            try:
                await query.edit_message_text("Fin de la lista de picks.", reply_markup=back_main_keyboard())
            except Exception:
                pass
        return

    if data == "auto":
        text = "<b>Autoevaluación (demo)</b>\nPicks registrados: (ver Supabase para métricas reales)\nWinrate: 52%\nROI: +4.2%\nEV promedio: +1.8%\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_main_keyboard())
        return

    # -------------------------
    # CONFIGURATION: send preview + one message per parameter (no interactive block in preview)
    # -------------------------
    if data == "config":
        pending = fetch_config().copy()
        context.user_data["cfg_pending"] = pending
        context.user_data["cfg_messages"] = []  # will hold (chat_id, message_id) to cleanup later
        # send preview only (no interactive config block inside)
        preview = get_config_preview_text(pending)
        try:
            m: Message = await query.message.reply_text(preview, parse_mode="HTML")
            context.user_data["cfg_messages"].append((m.chat_id, m.message_id))
            context.user_data["cfg_preview_msg"] = (m.chat_id, m.message_id)
        except Exception:
            pass
        # send each parameter as separate message and record its id
        for k, v in pending.items():
            text, kb = build_param_text_and_kb(k, str(v))
            try:
                m: Message = await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
                context.user_data["cfg_messages"].append((m.chat_id, m.message_id))
            except Exception:
                try:
                    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
                except Exception:
                    pass
        # final actions message
        try:
            m: Message = await query.message.reply_text("Acciones de configuración:", reply_markup=build_final_config_actions_kb())
            context.user_data["cfg_messages"].append((m.chat_id, m.message_id))
        except Exception:
            try:
                await query.edit_message_text("Acciones de configuración:", reply_markup=build_final_config_actions_kb())
            except Exception:
                pass
        try:
            await query.edit_message_text("Se han enviado los parámetros (ver mensajes).", reply_markup=main_keyboard())
        except Exception:
            pass
        return

    # CONFIG: set / inc / toggle / edit_text — update only the message where user clicked
    if data and data.startswith("cfg_set::"):
        _, key, val = data.split("::", 2)
        pending = context.user_data.get("cfg_pending") or fetch_config().copy()
        pending[key] = val
        context.user_data["cfg_pending"] = pending
        text, kb = build_param_text_and_kb(key, str(pending[key]))
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    if data and data.startswith("cfg_inc::"):
        _, key, delta = data.split("::", 2)
        try:
            d = float(delta)
        except Exception:
            d = 0.0
        pending = context.user_data.get("cfg_pending") or fetch_config().copy()
        cur = pending.get(key, DEFAULT_CONFIG.get(key, "0"))
        try:
            newv = float(cur) + d
            if float(newv).is_integer():
                newv = int(newv)
            pending[key] = str(newv)
        except Exception:
            pending[key] = cur
        context.user_data["cfg_pending"] = pending
        text, kb = build_param_text_and_kb(key, str(pending[key]))
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    if data and data.startswith("cfg_toggle::"):
        _, key = data.split("::", 1)
        pending = context.user_data.get("cfg_pending") or fetch_config().copy()
        cur = str(pending.get(key, DEFAULT_CONFIG.get(key, "false"))).lower()
        new = "true" if cur in ("false","0","no") else "false"
        pending[key] = new
        context.user_data["cfg_pending"] = pending
        text, kb = build_param_text_and_kb(key, str(pending[key]))
        try:
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    if data and data.startswith("cfg_edit_text::"):
        _, key = data.split("::",1)
        context.user_data["cfg_edit_key"] = key
        context.user_data["cfg_waiting_text"] = True
        try:
            await query.message.edit_text(f"Envía el nuevo valor para <b>{friendly_label(key)}</b> como texto (ej: 02:30).", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main")]]))
        except Exception:
            pass
        return

    # GLOBAL CONFIG ACTIONS: save / cancel / reset (these also cleanup the sent messages)
    if data and data.startswith("cfg_save::"):
        pending = context.user_data.get("cfg_pending") or fetch_config().copy()
        for k, v in pending.items():
            set_config_key(k, v)
        # cleanup messages
        chat = update.effective_chat
        msgs = context.user_data.get("cfg_messages", [])
        for (chat_id, msg_id) in msgs:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        # remove preview reference
        context.user_data.pop("cfg_messages", None)
        context.user_data.pop("cfg_pending", None)
        context.user_data.pop("cfg_waiting_text", None)
        context.user_data.pop("cfg_edit_key", None)
        context.user_data.pop("cfg_preview_msg", None)
        await query.edit_message_text("Configuración guardada.", reply_markup=main_keyboard())
        return

    if data and data.startswith("cfg_cancel::"):
        msgs = context.user_data.get("cfg_messages", [])
        for (chat_id, msg_id) in msgs:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        context.user_data.pop("cfg_messages", None)
        context.user_data.pop("cfg_pending", None)
        context.user_data.pop("cfg_waiting_text", None)
        context.user_data.pop("cfg_edit_key", None)
        context.user_data.pop("cfg_preview_msg", None)
        await query.edit_message_text("Cambios cancelados.", reply_markup=main_keyboard())
        return

    if data and data.startswith("cfg_reset::"):
        for k,v in DEFAULT_CONFIG.items():
            set_config_key(k, v)
        msgs = context.user_data.get("cfg_messages", [])
        for (chat_id, msg_id) in msgs:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        context.user_data.pop("cfg_messages", None)
        context.user_data.pop("cfg_pending", None)
        context.user_data.pop("cfg_waiting_text", None)
        context.user_data.pop("cfg_edit_key", None)
        context.user_data.pop("cfg_preview_msg", None)
        await query.edit_message_text("Defaults restaurados.", reply_markup=main_keyboard())
        return

    if data and data.startswith("cfg_none::"):
        await query.answer("Pulsa los botones para cambiar el valor.", show_alert=False)
        return

    # Avisame / addpar (unchanged)
    if data and data.startswith("avisame::"):
        pid = data.split("::",1)[1]
        pick = fetch_pick_by_id(pid) or {}
        ok = insert_guardado(update.effective_user.id, pick) if sb else False
        if ok:
            await query.edit_message_text("✔️ Registrado. Te avisaremos sobre ese pick.", reply_markup=back_main_keyboard())
        else:
            await query.edit_message_text("🔔 Guardado en modo demo (sin DB).", reply_markup=back_main_keyboard())
        return

    if data and data.startswith("addpar::"):
        await query.edit_message_text("Añadido a tu parlay (modo demo).", reply_markup=back_main_keyboard())
        return

    # fallback
    await query.edit_message_text("Acción no reconocida. Volviendo al menú.", reply_markup=main_keyboard())

# -------------------------
# Message handler: text inputs & reto flow & config text editing
# -------------------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # Config edit text flow
    if context.user_data.get("cfg_waiting_text"):
        key = context.user_data.get("cfg_edit_key")
        if not key:
            context.user_data["cfg_waiting_text"] = False
            await update.message.reply_text("Error interno (no key).", reply_markup=main_keyboard())
            return
        pending = context.user_data.get("cfg_pending") or fetch_config().copy()
        pending[key] = text
        context.user_data["cfg_pending"] = pending
        context.user_data["cfg_waiting_text"] = False
        context.user_data.pop("cfg_edit_key", None)
        txt, kb = build_param_text_and_kb(key, str(pending[key]))
        # send confirmation and the updated param message
        await update.message.reply_text(f"Valor temporal guardado para <b>{friendly_label(key)}</b>: {text}\n\n", parse_mode="HTML")
        m: Message = await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)
        # keep track of this new message in cfg_messages so it will be cleaned up with others
        cfg_msgs = context.user_data.get("cfg_messages", [])
        cfg_msgs.append((m.chat_id, m.message_id))
        context.user_data["cfg_messages"] = cfg_msgs
        return

    # Reto Escalera
    if context.user_data.get("expecting_reto_init"):
        try:
            bank_init = float(text)
            context.user_data["bank_init"] = bank_init
            context.user_data["expecting_reto_init"] = False
            context.user_data["expecting_reto_final"] = True
            await update.message.reply_text("Bank inicial registrado. Ahora envía bank objetivo (ej: 750).")
        except Exception:
            await update.message.reply_text("No entendí. Envía un número (ej: 100).")
        return

    if context.user_data.get("expecting_reto_final"):
        try:
            bank_final = float(text)
            bank_init = float(context.user_data.get("bank_init", 0))
            if bank_final <= bank_init:
                await update.message.reply_text("El bank objetivo debe ser mayor que el inicial.")
                return
            n = 6
            r = (bank_final / bank_init) ** (1.0 / n)
            steps = []
            current = bank_init
            for i in range(1, n+1):
                current = round(current * r, 2)
                steps.append((i, current))
            msg = f"<b>Reto Escalera</b>\nBank inicial: {bank_init}\nBank objetivo: {bank_final}\n\n"
            for step, val in steps:
                msg += f"Step {step}: objetivo {val}\n"
            context.user_data["expecting_reto_final"] = False
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard())
        except Exception:
            await update.message.reply_text("No entendí. Envía un número para el bank objetivo.")
        return

    await update.message.reply_text("Usa /start para abrir el menú.", reply_markup=main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comandos: /start")

# -------------------------
# UI helpers
# -------------------------
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚽ Top Picks", callback_data="top")],
        [InlineKeyboardButton("🎯 Parlay Segurito", callback_data="parlay_seg"),
         InlineKeyboardButton("💥 Parlay Soñador", callback_data="parlay_so")],
        [InlineKeyboardButton("📈 Reto Escalera", callback_data="reto")],
        [InlineKeyboardButton("🎮 Fantasy", callback_data="fantasy"),
         InlineKeyboardButton("🌍 Deportes", callback_data="deportes")],
        [InlineKeyboardButton("📊 Autoevaluación", callback_data="auto"),
         InlineKeyboardButton("⚙️ Configuración", callback_data="config")]
    ])

def back_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="main")]])

def pick_action_keyboard_for_index(pick_id: str) -> InlineKeyboardMarkup:
    # removed per-pick 'Volver' button — final message will include Volver
    rows = []
    rows.append([
        InlineKeyboardButton("🔔 Avisame", callback_data=f"avisame::{pick_id}"),
        InlineKeyboardButton("➕ Añadir a parlay", callback_data=f"addpar::{pick_id}")
    ])
    return InlineKeyboardMarkup(rows)

# -------------------------
# Run
# -------------------------
def run():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no definido en .env")
    fetch_config()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
    app.add_handler(CommandHandler("help", help_command))
    print("🤖 BotPicks activo. Usa /start")
    app.run_polling()

if __name__ == "__main__":
    run()
