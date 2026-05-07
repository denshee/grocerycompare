import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# Set up Google Sheets connection
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('grocery-compare credentials.json', scope)
client = gspread.authorize(creds)

# Open the sheet
SHEET_ID = '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'
sheet = client.open_by_key(SHEET_ID)
listings_worksheet = sheet.worksheet('Listings')

# Get all existing listings
existing_listings = listings_worksheet.get_all_records()
print(f"Found {len(existing_listings)} existing listings")

# Example: Update a single row
# For now, just test the connection works
print("Google Sheets connection successful!")
print(f"Sheet name: {sheet.title}")
print(f"Listings rows: {len(existing_listings)}")
