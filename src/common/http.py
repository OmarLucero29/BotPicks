import time, json, requests
from typing import Optional, Dict, Any

class HttpClient:
    def __init__(self, base: Optional[str]=None, timeout: int=30, max_retries: int=5, backoff: float=0.9):
        self.base = base.rstrip("/") if base else None
        self.t = timeout; self.r = max_retries; self.b = backoff

    def _url(self, path_or_url: str) -> str:
        return path_or_url if (self.base is None or path_or_url.startswith("http")) else f"{self.base}/{path_or_url.lstrip('/')}"

    def get(self, path_or_url: str, params: Optional[Dict[str,Any]]=None, headers: Optional[Dict[str,str]]=None):
        url = self._url(path_or_url)
        tries = 0
        while True:
            try:
                res = requests.get(url, params=params, headers=headers, timeout=self.t)
                if res.status_code in (429, 502, 503, 504):
                    raise RuntimeError(f"HTTP {res.status_code}")
                return res
            except Exception:
                tries += 1
                if tries > self.r: raise
                time.sleep(self.b * tries)

    def get_json(self, path_or_url: str, params: Optional[Dict[str,Any]]=None, headers: Optional[Dict[str,str]]=None):
        res = self.get(path_or_url, params=params, headers=headers)
        ctype = res.headers.get("content-type","").lower()
        if "application/json" not in ctype:
            return None
        try:
            return res.json()
        except json.JSONDecodeError:
            return None

def save_jsonl(path: str, rows: list[dict]):
    import pathlib
    p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
