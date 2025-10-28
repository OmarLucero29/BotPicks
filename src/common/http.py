import time, json, requests
from typing import Optional, Dict, Any

class HttpClient:
    def __init__(self, base: Optional[str]=None, timeout: int=30, max_retries: int=4, backoff: float=0.75):
        self.base = base.rstrip("/") if base else None
        self.t = timeout; self.r = max_retries; self.b = backoff

    def get(self, path_or_url: str, params: Optional[Dict[str,Any]]=None, headers: Optional[Dict[str,str]]=None):
        url = path_or_url if (self.base is None or path_or_url.startswith("http")) else f"{self.base}/{path_or_url.lstrip('/')}"
        tries = 0
        while True:
            try:
                res = requests.get(url, params=params, headers=headers, timeout=self.t)
                if res.status_code == 429 or res.status_code >= 500:
                    raise RuntimeError(f"HTTP {res.status_code}")
                return res
            except Exception:
                tries += 1
                if tries > self.r: raise
                time.sleep(self.b * tries)

def save_jsonl(path: str, rows: list[dict]):
    import pathlib, json as _json
    p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(_json.dumps(r, ensure_ascii=False) + "\n")
