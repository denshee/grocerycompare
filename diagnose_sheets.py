import os
import gspread
import traceback
from google.oauth2.service_account import Credentials

# --- Configuration ---
CREDS_FILE = 'credentials.json'
# Using the ID found in normalization_engine.py
SHEET_ID = os.getenv('GOOGLE_SHEET_ID') or '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'
TARGET_WORKSHEET = "Products" # User specifically requested "Products" for the test

def test_google_sheets_connection():
    print(f"--- AGGRESSIVE DIAGNOSTIC START ---")
    print(f"Targeting Spreadsheet ID: {SHEET_ID}")
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # 1. Credential Check
        if not os.path.exists(CREDS_FILE):
            print(f"ERROR: Credential file '{CREDS_FILE}' NOT FOUND in current directory.")
            print(f"Current Directory: {os.getcwd()}")
            return

        print(f"Attempting to authorize with {CREDS_FILE}...")
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        print("Authorization: SUCCESS")

        # 2. Open Spreadsheet
        print(f"Attempting to open spreadsheet...")
        sh = client.open_by_key(SHEET_ID)
        print(f"Spreadsheet Title: {sh.title}")

        # 3. Access Worksheet
        try:
            ws = sh.worksheet(TARGET_WORKSHEET)
            print(f"Worksheet '{TARGET_WORKSHEET}': FOUND")
        except gspread.exceptions.WorksheetNotFound:
            print(f"ERROR: Worksheet '{TARGET_WORKSHEET}' NOT FOUND.")
            print(f"Available Worksheets: {[w.title for w in sh.worksheets()]}")
            return

        # 4. Write Test
        print(f"Attempting write to {TARGET_WORKSHEET}!Z1...")
        ws.update_acell('Z1', 'API_CONNECTED_SUCCESSFULLY')
        print("!!! WRITE SUCCESSFUL !!!")
        print("Check cell Z1 in the Google Sheet for the message 'API_CONNECTED_SUCCESSFULLY'.")

    except Exception:
        print("--- CRITICAL API FAILURE ---")
        traceback.print_exc()

if __name__ == "__main__":
    test_google_sheets_connection()
