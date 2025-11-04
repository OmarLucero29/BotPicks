import os, json, time, pathlib, datetime as dt
from dotenv import load_dotenv; load_dotenv()
OUT = pathlib.Path("data")/dt.date.today().isoformat(); OUT.mkdir(parents=True, exist_ok=True)

def fetch_stub(sport):
    # TODO: reemplazar por la fuente real (APISports u otra)
    time.sleep(0.2)
    return {"sport": sport, "ts": dt.datetime.utcnow().isoformat(), "items": []}

SPORTS = ["soccer","baseball","basketball","tennis","hockey","pingpong","football","esports"]
for s in SPORTS:
    data = fetch_stub(s)
    (OUT/f"{s}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
print(f"OK -> {OUT}")
