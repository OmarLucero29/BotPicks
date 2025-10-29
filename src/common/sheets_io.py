import os, json, gspread
from google.oauth2.service_account import Credentials
SCOPES=['https://www.googleapis.com/auth/spreadsheets']
def get_client():
    raw=os.environ.get('GCP_SA_JSON'); info=json.loads(raw)
    creds=Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)
def write_rows(sheet_id: str, tab: str, rows: list[list]):
    gc=get_client(); sh=gc.open_by_key(sheet_id)
    try: ws=sh.worksheet(tab)
    except Exception: ws=sh.add_worksheet(title=tab, rows='1000', cols='32')
    ws.append_rows(rows, value_input_option='USER_ENTERED')
