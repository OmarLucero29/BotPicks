import time, json, requests
from typing import Optional, Dict, Any

class HttpClient:
    def __init__(self, base: Optional[str]=None, timeout: int=30, max_retries: int=5, backoff: float=0.9):
        self.base = base.rstrip('/') if base else None
        self.t=timeout; self.r=max_retries; self.b=backoff
    def _url(self, p): return p if (self.base is None or p.startswith('http')) else f"{self.base}/{p.lstrip('/')}"
    def get(self, p, params: Optional[Dict[str,Any]]=None, headers: Optional[Dict[str,str]]=None):
        url=self._url(p); tries=0
        while True:
            try:
                r=requests.get(url, params=params, headers=headers, timeout=self.t)
                if r.status_code in (429,502,503,504): raise RuntimeError(f"HTTP {r.status_code}")
                return r
            except Exception:
                tries+=1
                if tries>self.r: raise
                time.sleep(self.b*tries)
    def get_json(self, p, params=None, headers=None):
        r=self.get(p, params=params, headers=headers)
        if 'application/json' not in r.headers.get('content-type','').lower(): return None
        try: return r.json()
        except json.JSONDecodeError: return None

def save_jsonl(path: str, rows: list[dict]):
    import pathlib, json as _j
    p=pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p,'w',encoding='utf-8') as f:
        for r in rows: f.write(_j.dumps(r, ensure_ascii=False)+'\n')
