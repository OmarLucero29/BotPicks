# scripts/ingest_run.py
import os
import asyncio
import aiohttp
import asyncpg
import json
from datetime import datetime, timezone

API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # asegúrate que esté en env

API_SPORTS_BASE = "https://v3.football.api-sports.io"  # ejemplo para fútbol; API-SPORTS v3

HEADERS = {
    "x-apisports-key": API_SPORTS_KEY,
    "User-Agent": os.getenv("HTTP_USER_AGENT","BotPicks/1.0")
}

async def fetch_matches_for_sport(session, sport="football", from_ts=None, to_ts=None):
    # Example for API-SPORTS football fixtures endpoint
    params = {}
    url = f"https://v3.football.api-sports.io/fixtures"
    if from_ts and to_ts:
        params["date"] = from_ts  # adapt per API, example only
    async with session.get(url, params=params, headers=HEADERS, timeout=30) as r:
        if r.status != 200:
            text = await r.text()
            raise RuntimeError(f"Fetch failed {r.status}: {text}")
        j = await r.json()
        return j

async def upsert_match_cache(conn, match_id, sport, home, away, start_time, markets_json, extra=None):
    # Upsert into match_cache table with JSON markets
    await conn.execute("""
    INSERT INTO match_cache (match_id, sport, home, away, start_time, markets, status)
    VALUES ($1,$2,$3,$4,$5,$6,$7)
    ON CONFLICT (match_id) DO UPDATE SET markets=$6, start_time=$5, status=$7
    """, match_id, sport, home, away, start_time, json.dumps(markets_json), "not_started")

async def main():
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5)
    async with aiohttp.ClientSession() as session:
        # TODO: iterate sports & leagues; for MVP fetch football fixtures next 48h
        data = await fetch_matches_for_sport(session)
        # Parse provider-specific structure to our 'markets' normalized format:
        # markets = { "moneyline": [{"selection":"Home","odds":1.75}, ...], "over_under_2.5":[...], ... }
        # Example parsing for api-sports: j["response"] -> iterate fixtures and bookmakers -> markets
        fixtures = data.get("response", [])
        async with pool.acquire() as conn:
            for f in fixtures:
                fid = f["fixture"]["id"]
                home = f["teams"]["home"]["name"]
                away = f["teams"]["away"]["name"]
                start = f["fixture"]["timestamp"]
                # Normalize markets from bookmakers if present
                markets = {}
                for b in f.get("bookmakers", []):
                    for market in b.get("bets", []):
                        m_name = market.get("name")
                        selections = []
                        for opt in market.get("values", []):
                            selections.append({"selection": opt.get("value"), "odds": opt.get("odd"), "provider": b.get("title")})
                        if selections:
                            markets[m_name] = selections
                await upsert_match_cache(conn, str(fid), "football", home, away, datetime.fromtimestamp(start, tz=timezone.utc), markets)
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
