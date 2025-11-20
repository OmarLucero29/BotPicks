# scripts/cron_notify.py
"""
Cron / Worker para:
- Ingesta de datos desde APISPORTS, ODDSAPI y PANDASCORE
- Upsert normalizado en la tabla `match_cache`
- Revisión de `notifications`: notifica cambios de cuota (threshold_pct)
- Notifica cuando una leg se gane (usa src/parlay/evaluator.evaluate_leg)
- Modo de persistencia:
    * Uso preferente: DATABASE_URL (asyncpg)
    * Fallback: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (REST)
Requisitos: aiohttp, asyncpg (si usas Postgres), python >=3.9

Variables de entorno (mantener nombres EXACTOS como en Tokens.txt):
- TELEGRAM_BOT_TOKEN
- API_SPORTS_KEY
- ODDSAPI_KEY
- PANDASCORE_KEY
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- DATABASE_URL or SUPABASE_DB_URL or POSTGRES_URL (opcional)
- NOTIFY_CHECK_INTERVAL (default 30s)
- HTTP_USER_AGENT (opcional)
"""

import os
import asyncio
import aiohttp
import asyncpg
import json
import time
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime, timezone

# Evaluator import
from src.parlay.evaluator import evaluate_leg  # se espera que exista

# Env / Tokens (mantener exactamente los nombres)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")
ODDSAPI_KEY = os.getenv("ODDSAPI_KEY")
PANDASCORE_KEY = os.getenv("PANDASCORE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# DB connection variables (try several names)
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or os.getenv("POSTGRES_URL")

CHECK_INTERVAL_SECONDS = int(os.getenv("NOTIFY_CHECK_INTERVAL", "30"))
HTTP_USER_AGENT = os.getenv("HTTP_USER_AGENT", "BotPicks/1.0 (+https://example.com)")

# Safety defaults
DEFAULT_ODDS_CHANGE_THRESHOLD = 5.0  # percent
DEFAULT_NOTIFY_ON_LEG_WON = True

# Timeouts
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)

# Simple Telegram send via Bot API (no aiogram dependency here)
async def telegram_send_message(session: aiohttp.ClientSession, chat_id: int, text: str):
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set; skipping telegram send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with session.post(url, json=payload, timeout=HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                txt = await resp.text()
                print(f"Telegram send failed {resp.status}: {txt}")
    except Exception as e:
        print("Telegram send exception:", e)

# Normalizer / Parser helpers for provider responses into our internal 'markets' format:
# markets = { market_name: [ { "selection": "...", "odds": 1.23, "provider":"api-sports", "metadata": {...} }, ... ] }

async def fetch_apisports_fixtures(session: aiohttp.ClientSession, sport: str = "football") -> List[Dict[str, Any]]:
    """
    Fetch fixtures + bookmaker markets from API-SPORTS (v3). Returns normalized list of matches.
    Requires API_SPORTS_KEY.
    """
    if not API_SPORTS_KEY:
        return []
    results = []
    headers = {"x-apisports-key": API_SPORTS_KEY, "User-Agent": HTTP_USER_AGENT}
    # Example: fetch upcoming fixtures for next 48h - adapt params if needed
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"next": 48}  # next 48 hours
    try:
        async with session.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT) as r:
            if r.status != 200:
                txt = await r.text()
                print("APISPORTS fetch error:", r.status, txt)
                return []
            j = await r.json()
    except Exception as e:
        print("APISPORTS request exception:", e)
        return []

    for f in j.get("response", []):
        fixture = f.get("fixture", {})
        teams = f.get("teams", {})
        if not fixture:
            continue
        match_id = str(fixture.get("id"))
        start_ts = fixture.get("timestamp")
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc) if start_ts else None
        home = teams.get("home", {}).get("name")
        away = teams.get("away", {}).get("name")
        # Build markets from bookmakers if present
        markets = {}
        for bookmaker in f.get("bookmakers", []):
            provider = bookmaker.get("title")
            for bet in bookmaker.get("bets", []):
                mname = bet.get("name") or "unknown"
                selections = []
                for val in bet.get("values", []):
                    odd = val.get("odd")
                    sel = val.get("value")
                    if odd is None or sel is None:
                        continue
                    try:
                        oddf = float(odd)
                    except Exception:
                        continue
                    selections.append({"selection": sel, "odds": oddf, "provider": provider, "metadata": val})
                if selections:
                    markets.setdefault(mname, []).extend(selections)
        results.append({
            "match_id": match_id,
            "sport": "football",
            "home": home,
            "away": away,
            "start_time": start_dt.isoformat() if start_dt else None,
            "markets": markets,
            "source": "api-sports"
        })
    return results

async def fetch_oddsapi_odds(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Fetch odds from TheOddsAPI (oddsapi). Example endpoint: GET /v4/sports/{sport}/odds
    We'll fetch several sports supported. Requires ODDSAPI_KEY.
    """
    if not ODDSAPI_KEY:
        return []
    results = []
    base = "https://api.the-odds-api.com/v4/sports"
    # List of some sports slugs used by the-odds-api
    sport_slugs = ["soccer_epl", "soccer_spain_laliga", "basketball_nba", "americanfootball_nfl", "tennis_atp"]
    for slug in sport_slugs:
        url = f"{base}/{slug}/odds"
        params = {"apiKey": ODDSAPI_KEY, "regions": "us,eu", "markets": "h2h,spreads,totals", "oddsFormat": "decimal"}
        try:
            async with session.get(url, params=params, timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT}) as r:
                if r.status != 200:
                    # skip quietly
                    continue
                j = await r.json()
        except Exception:
            continue
        for match in j:
            # match has: id, sport_key, commence_time, home_team, away_team, bookmakers -> markets
            match_id = str(match.get("id") or f"{match.get('sport_key')}_{match.get('commence_time')}_{match.get('home_team')}")
            start_time = match.get("commence_time")
            home = match.get("home_team")
            away = match.get("away_team")
            markets = {}
            for book in match.get("bookmakers", []):
                prov = book.get("title")
                for market in book.get("markets", []):
                    mkey = market.get("key")
                    for outcome in market.get("outcomes", []):
                        sel = outcome.get("name")
                        odd = outcome.get("price")
                        if odd is None:
                            continue
                        try:
                            oddf = float(odd)
                        except Exception:
                            continue
                        markets.setdefault(mkey, []).append({"selection": sel, "odds": oddf, "provider": prov, "metadata": outcome})
            results.append({
                "match_id": match_id,
                "sport": match.get("sport_key"),
                "home": home,
                "away": away,
                "start_time": start_time,
                "markets": markets,
                "source": "oddsapi"
            })
    return results

async def fetch_pandascore_matches(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Fetch matches from PandaScore (esports). Requires PANDASCORE_KEY.
    Endpoint example: https://api.pandascore.co/matches/upcoming
    """
    if not PANDASCORE_KEY:
        return []
    results = []
    base = "https://api.pandascore.co"
    url = f"{base}/matches/upcoming"
    headers = {"Authorization": f"Bearer {PANDASCORE_KEY}", "User-Agent": HTTP_USER_AGENT}
    try:
        async with session.get(url, headers=headers, timeout=HTTP_TIMEOUT) as r:
            if r.status != 200:
                return []
            j = await r.json()
    except Exception:
        return []
    for m in j:
        league = m.get("league", {}).get("name")
        match_id = str(m.get("id"))
        home = (m.get("opponents") or [{}])[0].get("opponent", {}).get("name") if m.get("opponents") else None
        away = (m.get("opponents") or [{}])[1].get("opponent", {}).get("name") if m.get("opponents") else None
        # PandaScore may not provide odds; markets may be empty -> still store metadata
        markets = {}
        results.append({
            "match_id": match_id,
            "sport": "esports",
            "home": home,
            "away": away,
            "start_time": m.get("begin_at"),
            "markets": markets,
            "source": "pandascore"
        })
    return results

# DB wrapper: try asyncpg (Postgres). If not available, use Supabase REST API
class DBClient:
    def __init__(self, database_url: Optional[str], supabase_url: Optional[str], supabase_key: Optional[str]):
        self.database_url = database_url
        self.supabase_url = supabase_url.rstrip("/") if supabase_url else None
        self.supabase_key = supabase_key
        self.pool = None
        self.session = None

    async def init(self):
        self.session = aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT})
        if self.database_url:
            try:
                self.pool = await asyncpg.create_pool(dsn=self.database_url, min_size=1, max_size=5)
                print("Connected via asyncpg to DATABASE_URL")
            except Exception as e:
                print("asyncpg connection failed:", e)
                self.pool = None

    async def close(self):
        if self.pool:
            await self.pool.close()
        if self.session:
            await self.session.close()

    # Upsert match_cache row
    async def upsert_match_cache(self, match: Dict[str, Any]):
        """
        match: { match_id, sport, home, away, start_time (iso), markets (dict), source }
        """
        if self.pool:
            async with self.pool.acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO match_cache (match_id, sport, home, away, start_time, markets, status)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)
                        ON CONFLICT (match_id) DO UPDATE
                          SET markets = EXCLUDED.markets, start_time = EXCLUDED.start_time, sport = EXCLUDED.sport
                        """,
                        str(match.get("match_id")),
                        match.get("sport"),
                        match.get("home"),
                        match.get("away"),
                        match.get("start_time"),
                        json.dumps(match.get("markets") or {}),
                        "not_started"
                    )
                except Exception as e:
                    print("DB upsert error (asyncpg):", e)
        elif self.supabase_url and self.supabase_key:
            # Use Supabase REST upsert (merge-duplicates) - requires primary key match_id
            table = "match_cache"
            url = f"{self.supabase_url}/rest/v1/{table}"
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",  # upsert
                "Accept": "application/json"
            }
            payload = {
                "match_id": str(match.get("match_id")),
                "sport": match.get("sport"),
                "home": match.get("home"),
                "away": match.get("away"),
                "start_time": match.get("start_time"),
                "markets": match.get("markets") or {},
                "status": "not_started"
            }
            try:
                async with self.session.post(url, headers=headers, json=[payload]) as resp:
                    if resp.status not in (200, 201, 204):
                        txt = await resp.text()
                        print("Supabase upsert match_cache failed:", resp.status, txt)
            except Exception as e:
                print("Supabase upsert exception:", e)
        else:
            print("No DB client available to upsert match_cache.")

    async def fetch_notifications(self):
        """
        Return list of notifications rows: id, user_id, parlay_id, trigger_config, active
        Implemented for both Postgres and Supabase REST.
        """
        if self.pool:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT id, user_id, parlay_id, trigger_config, active, last_notified_at FROM notifications WHERE active = true")
                return [dict(r) for r in rows]
        elif self.supabase_url and self.supabase_key:
            url = f"{self.supabase_url}/rest/v1/notifications?active=eq.true"
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}", "Accept": "application/json"}
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    j = await resp.json()
                    return j
                else:
                    txt = await resp.text()
                    print("Supabase fetch notifications failed:", resp.status, txt)
                    return []
        else:
            return []

    async def fetch_parlay(self, parlay_id: int) -> Optional[Dict[str, Any]]:
        if self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT id, user_id, total_odds, settings_snapshot FROM parlays WHERE id=$1", parlay_id)
                return dict(row) if row else None
        elif self.supabase_url and self.supabase_key:
            url = f"{self.supabase_url}/rest/v1/parlays?id=eq.{parlay_id}&select=*"
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}", "Accept": "application/json"}
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    j = await resp.json()
                    return j[0] if j else None
                else:
                    return None
        else:
            return None

    async def fetch_parlay_legs(self, parlay_id: int) -> List[Dict[str, Any]]:
        if self.pool:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT id, match_id, market, selection, odds FROM parlay_legs WHERE parlay_id=$1", parlay_id)
                return [dict(r) for r in rows]
        elif self.supabase_url and self.supabase_key:
            url = f"{self.supabase_url}/rest/v1/parlay_legs?parlay_id=eq.{parlay_id}"
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}", "Accept": "application/json"}
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return []
        else:
            return []

    async def fetch_matchcache_by_id(self, match_id: str) -> Optional[Dict[str, Any]]:
        if self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT match_id, sport, home, away, start_time, markets, status, home_score, away_score FROM match_cache WHERE match_id=$1", match_id)
                return dict(row) if row else None
        elif self.supabase_url and self.supabase_key:
            url = f"{self.supabase_url}/rest/v1/match_cache?match_id=eq.{match_id}&select=*"
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}", "Accept": "application/json"}
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    j = await resp.json()
                    return j[0] if j else None
                else:
                    return None
        else:
            return None

    async def update_notification_last_notified(self, notif_id: int):
        if self.pool:
            async with self.pool.acquire() as conn:
                await conn.execute("UPDATE notifications SET last_notified_at = now() WHERE id=$1", notif_id)
        elif self.supabase_url and self.supabase_key:
            url = f"{self.supabase_url}/rest/v1/notifications?id=eq.{notif_id}"
            headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}", "Content-Type": "application/json", "Prefer": "return=representation"}
            payload = {"last_notified_at": datetime.now(timezone.utc).isoformat()}
            async with self.session.patch(url, headers=headers, json=payload) as resp:
                if resp.status not in (200,204):
                    txt = await resp.text()
                    print("Supabase update notification failed:", resp.status, txt)

# Helper to compute current total odds for a parlay by reading match_cache markets
async def compute_current_parlay_odds(db: DBClient, legs: List[Dict[str, Any]]) -> float:
    total = 1.0
    for leg in legs:
        match_id = str(leg.get("match_id"))
        mc = await db.fetch_matchcache_by_id(match_id)
        chosen_odds = None
        if mc and mc.get("markets"):
            markets = mc.get("markets") or {}
            # try find market matching leg.market and selection
            for mname, selections in markets.items():
                # Compare normalized market name and selection heuristically
                if normalize_str(mname) == normalize_str(leg.get("market")) or normalize_str(leg.get("market")) in normalize_str(mname):
                    for s in selections:
                        if normalize_str(s.get("selection","")) == normalize_str(leg.get("selection","")):
                            chosen_odds = float(s.get("odds"))
                            break
                    if chosen_odds:
                        break
            # if not found, try to take first odds available
            if not chosen_odds:
                for mname, selections in markets.items():
                    if selections:
                        chosen_odds = float(selections[0].get("odds"))
                        break
        if not chosen_odds:
            # fallback to stored leg odds
            chosen_odds = float(leg.get("odds", 1.0) or 1.0)
        total *= float(chosen_odds)
    return float(total)

def normalize_str(s: Optional[str]) -> str:
    if not s:
        return ""
    return str(s).strip().lower()

# Main loop: ingest -> upsert -> check notifications -> send messages for odds change & leg won
async def main_loop():
    db = DBClient(DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    await db.init()
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT}) as session:
        try:
            while True:
                start = time.time()
                # 1) Ingest from providers (APISPORTS, ODDSAPI, PANDASCORE)
                tasks = [
                    fetch_apisports_fixtures(session),
                    fetch_oddsapi_odds(session),
                    fetch_pandascore_matches(session)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                ingested = 0
                for res in results:
                    if isinstance(res, Exception):
                        print("Ingest task exception:", res)
                        continue
                    for m in res:
                        await db.upsert_match_cache(m)
                        ingested += 1
                if ingested:
                    print(f"Ingested/updated {ingested} matches into match_cache")

                # 2) Process notifications
                notifs = await db.fetch_notifications()
                for n in notifs:
                    notif_id = n.get("id")
                    user_id = int(n.get("user_id"))
                    parlay_id = int(n.get("parlay_id"))
                    trigger_config = n.get("trigger_config") or {}
                    threshold = float(trigger_config.get("threshold_pct", DEFAULT_ODDS_CHANGE_THRESHOLD))
                    notify_on_leg_won = bool(trigger_config.get("notify_on_leg_won", DEFAULT_NOTIFY_ON_LEG_WON))

                    parlay = await db.fetch_parlay(parlay_id)
                    if not parlay:
                        continue
                    saved_total_odds = float(parlay.get("total_odds") or 0.0)
                    legs = await db.fetch_parlay_legs(parlay_id)
                    # Compute current total odds
                    current_total_odds = await compute_current_parlay_odds(db, legs)
                    pct_change = abs((current_total_odds - saved_total_odds) / saved_total_odds * 100) if saved_total_odds > 0 else 0.0
                    if pct_change >= threshold:
                        # notify user
                        msg = f"🔔 Cambio de cuota detectado para tu Parlay #{parlay_id}\nCuota anterior: {saved_total_odds:.2f}\nCuota actual: {current_total_odds:.2f}\nCambio: {pct_change:.2f}%"
                        await telegram_send_message(session, user_id, msg)
                        await db.update_notification_last_notified(notif_id)

                    # Now check legs results (notify when a leg is won)
                    if notify_on_leg_won:
                        for leg in legs:
                            match_id = str(leg.get("match_id"))
                            mc = await db.fetch_matchcache_by_id(match_id)
                            if not mc:
                                continue
                            status = (mc.get("status") or "").lower()
                            # status should be 'finished' for evaluation
                            if status != "finished":
                                continue
                            # build match_final structure expected by evaluator
                            match_final = {
                                "status": mc.get("status"),
                                "home": mc.get("home"),
                                "away": mc.get("away"),
                                "home_score": mc.get("home_score"),
                                "away_score": mc.get("away_score"),
                                "winner": mc.get("winner"),
                                "final_result": mc.get("final_result")
                            }
                            leg_obj = {"market": leg.get("market"), "selection": leg.get("selection"), "metadata": leg.get("metadata")}
                            try:
                                res = evaluate_leg(leg_obj, match_final)
                            except Exception as e:
                                print("Evaluator exception:", e)
                                res = None
                            if res is True:
                                # Send notification for leg won
                                text = f"✅ ¡Una leg de tu Parlay #{parlay_id} se ganó!\nMatch: {match_final.get('home')} vs {match_final.get('away')}\nPick: {leg.get('selection')} — Cuota: {float(leg.get('odds') or 0):.2f}"
                                await telegram_send_message(session, user_id, text)
                                # update notification last_notified
                                await db.update_notification_last_notified(notif_id)
                elapsed = time.time() - start
                sleep_for = max(1, CHECK_INTERVAL_SECONDS - elapsed)
                await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            print("main loop cancelled")
        except Exception as e:
            print("Fatal exception in main_loop:", e)
        finally:
            await db.close()

# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Stopped by user")
