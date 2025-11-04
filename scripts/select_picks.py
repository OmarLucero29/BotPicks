import json, pathlib, datetime as dt
today = dt.date.today().isoformat()
src = pathlib.Path("data")/today
dst = pathlib.Path("data")/f"picks_{today}.json"
picks = []
for f in src.glob("*.json"):
    obj = json.loads(f.read_text())
    # TODO: lógica real de modelos; por ahora, deja registro vacío
    picks.append({"sport": obj["sport"], "n_items": len(obj["items"]), "status":"draft"})
dst.write_text(json.dumps(picks, indent=2, ensure_ascii=False))
print(f"Picks -> {dst}")
