import os
import json
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

def get_sheets_client():
    """Create an authenticated gspread client.
    
    Loads credentials from the GCP_CREDENTIALS environment variable (JSON string)
    when running in GitHub Actions, or falls back to credentials.json locally.
    """
    gcp_creds_json = os.getenv('GCP_CREDENTIALS')
    if gcp_creds_json:
        creds_dict = json.loads(gcp_creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    
    return gspread.authorize(creds)

def get_listings_worksheet():
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet('Listings')

def update_listing_price(worksheet, listing_name, new_price):
    """Update price for a specific listing by name"""
    cell = worksheet.find(listing_name)
    if cell:
        # Current_price is column D (index 4)
        worksheet.update_cell(cell.row, 4, new_price)
        return True
    return False
