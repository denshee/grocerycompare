import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'

def get_sheets_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
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
