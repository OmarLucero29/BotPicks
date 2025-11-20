# scripts/test_connections.py
import os
from dotenv import load_dotenv
load_dotenv()
print("Checking environment and integrations...")
missing = []
for var in ["SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","GOOGLE_SHEETS_CREDENTIALS_JSON_B64","GSHEET_ID"]:
    print(f"{var}:", "SET" if os.getenv(var) else "MISSING")
