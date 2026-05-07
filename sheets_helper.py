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

def get_listings_worksheet():
    """Restored name for script compatibility"""
    client = get_sheets_client()
    return client.open_by_key(SHEET_ID).worksheet('Listings')

def load_existing_listings(worksheet):
    print("  [DEBUG] Loading existing data from Google Sheet...")
    all_values = worksheet.get_all_values()
    existing = {}
    if len(all_values) < 2: return existing
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) >= 4:
            name, store = row[1].strip(), row[3].strip()
            existing[(name, store)] = {'row': i, 'category': row[2], 'price': row[4]}
    return existing

def batch_upsert(worksheet, store_name, new_rows, price_updates, history_rows=None):
    # CRITICAL DIAGNOSTIC - This is what we need to see in the logs
    print(f"\n[DIAGNOSTIC] --- {store_name} DATA CHECK ---")
    print(f"  New Rows found by scraper: {len(new_rows)}")
    print(f"  Updates found by scraper:  {len(price_updates)}")

    if not new_rows and not price_updates:
        print(f"❌ ERROR: {store_name} scraper found NOTHING on the website.")
        # We crash on purpose here so the log stays visible in GitHub
        raise ValueError(f"CRITICAL: {store_name} scraper returned 0 items. Selectors are likely broken.")

    if new_rows:
        print(f"✅ ACTION: Writing {len(new_rows)} new rows...")
        worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')
        time.sleep(1)

    return len(new_rows), len(price_updates)