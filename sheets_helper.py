import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.getenv('GOOGLE_SHEET_ID') or '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

def get_sheets_client():
    gcp_creds_json = os.getenv('GCP_CREDENTIALS')
    if gcp_creds_json:
        creds_dict = json.loads(gcp_creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    return gspread.authorize(creds)

def batch_upsert(worksheet, store_name, new_rows, price_updates, history_rows=None):
    # CRITICAL DIAGNOSTIC
    print(f"\n[DIAGNOSTIC] --- {store_name} Pre-Flight Check ---")
    print(f"  Incoming New Rows: {len(new_rows)}")
    print(f"  Incoming Updates:  {len(price_updates)}")

    if not new_rows and not price_updates:
        print(f"❌ ERROR: {store_name} tried to send EMPTY lists to the sheet.")
        print(f"💡 REASON: The scraper found the website but failed to extract names/prices.")
        # This will show up in red in your GitHub Actions logs
        raise ValueError(f"SCRAPER FAILURE: {store_name} returned zero products. Check selectors.")

    # Only runs if data exists
    created = 0
    if new_rows:
        print(f"✅ ACTION: Writing {len(new_rows)} new rows...")
        worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')
        created = len(new_rows)
        time.sleep(1)

    return created, len(price_updates)