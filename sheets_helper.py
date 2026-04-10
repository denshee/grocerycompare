import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k')

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Column indices (1-based) in the Listings sheet
COL_LISTING_ID   = 1
COL_PRODUCT_NAME = 2
COL_STORE        = 3
COL_CURRENT_PRICE = 4
COL_REGULAR_PRICE = 5
COL_IN_STOCK     = 6
COL_IMAGE_URL    = 7

def get_sheets_client():
    """Create an authenticated gspread client.

    In GitHub Actions, reads credentials from GCP_CREDENTIALS env var (JSON string).
    Locally, falls back to credentials.json file.
    """
    gcp_creds_json = os.getenv('GCP_CREDENTIALS')
    if gcp_creds_json:
        creds_dict = json.loads(gcp_creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    return gspread.authorize(creds)


def get_listings_worksheet():
    """Return the Listings worksheet object."""
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet('Listings')


def load_existing_listings(worksheet):
    """Load all existing rows into a dict for fast lookup.

    Returns:
        dict: {(product_name, store): row_number (1-based, header = row 1)}
    """
    print("  Loading existing sheet data (1 API read)...")
    all_values = worksheet.get_all_values()  # Returns list of lists (no parsing)
    existing = {}
    if len(all_values) < 2:
        return existing  # empty or header-only
    # Row 1 is header, data starts at row 2
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) >= 3:
            name  = row[COL_PRODUCT_NAME - 1].strip()
            store = row[COL_STORE - 1].strip()
            if name and store:
                existing[(name, store)] = i
    print(f"  Found {len(existing)} existing listings in sheet.")
    return existing


def batch_upsert(worksheet, store_name, new_rows, price_updates):
    """Write all new rows and price updates in bulk.

    Args:
        worksheet: gspread Worksheet object
        store_name: str, for logging
        new_rows: list of lists — full rows to append (new products)
        price_updates: list of (row_number, price) tuples — existing products to update
    """
    created = 0
    updated = 0

    # --- Append all new rows in one call ---
    if new_rows:
        print(f"  Appending {len(new_rows)} new {store_name} rows (1 API call)...")
        worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')
        created = len(new_rows)
        # Small pause between the two write calls to stay within quota
        if price_updates:
            time.sleep(2)

    # --- Batch update all prices in one call ---
    if price_updates:
        print(f"  Updating {len(price_updates)} existing {store_name} prices (1 API call)...")
        batch_data = []
        for row_num, price in price_updates:
            cell = gspread.utils.rowcol_to_a1(row_num, COL_CURRENT_PRICE)
            batch_data.append({
                'range': cell,
                'values': [[price]]
            })
        worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')
        updated = len(price_updates)

    return created, updated


# --- Legacy helper kept for backwards compatibility ---
def update_listing_price(worksheet, listing_name, new_price):
    """Single-cell price update. Prefer batch_upsert for bulk operations."""
    cell = worksheet.find(listing_name)
    if cell:
        worksheet.update_cell(cell.row, COL_CURRENT_PRICE, new_price)
        return True
    return False
