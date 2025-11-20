cat > scripts/ingest_daily.py <<'PY'
#!/usr/bin/env python3
# scripts/ingest_daily.py
import os
import json
from src.pipelines.ingest import run_ingest

# config simple: leer config.json en repo o usar default
cfg_path = "ingest_config.json"
if os.path.exists(cfg_path):
    cfg = json.load(open(cfg_path))
else:
    # default: tomar data/next_events.csv y optional google sheet env
    cfg = {"sources":[{"type":"csv","path":"data/next_events.csv","table":"next_events"}]}
    gs = os.getenv("GSHEET_ID")
    if gs:
        cfg["sources"].append({"type":"sheet","id":gs,"table":"next_events"})

print("Configuración de ingest:", cfg)
res = run_ingest(cfg["sources"])
print("Resultado final de ingest:", res)
PY
chmod +x scripts/ingest_daily.py
