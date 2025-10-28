import os, json, gspread

def _service_json():
    js = os.environ.get("GCP_SA_JSON") or os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not js: raise RuntimeError("GCP_SA_JSON o GCP_SERVICE_ACCOUNT_JSON no configurado")
    return json.loads(js)

def _client():
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(_service_json(), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)

def _tab_name(env_name: str, default_name: str) -> str:
    return os.environ.get(env_name, default_name)

def write_rows(sheet_id: str, tab_env_name: str, default_tab: str, rows: list[list[str]]):
    if not rows: return
    sh = _client().open_by_key(sheet_id)
    tab_name = _tab_name(tab_env_name, default_tab)
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=20)
    ws.append_rows(rows, value_input_option="RAW")
