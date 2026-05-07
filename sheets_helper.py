import os
import json
import time
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.getenv('GOOGLE_SHEET_ID') or '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Column indices (1-based) in the Listings sheet
COL_LISTING_ID   = 1
COL_PRODUCT_NAME = 2
COL_CATEGORY     = 3
COL_STORE        = 4
COL_CURRENT_PRICE = 5
COL_REGULAR_PRICE = 6
COL_IN_STOCK     = 7
COL_IMAGE_URL    = 8
COL_CANONICAL_ID = 9

def get_sheets_client():
    """Create an authenticated gspread client."""
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


def get_history_worksheet():
    """Return the Price_History worksheet object."""
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    try:
        return sheet.worksheet('Price_History')
    except gspread.WorksheetNotFound:
        # Phase 2 Cols: Date, Product_name, Store, Price, Regular_price
        ws = sheet.add_worksheet(title="Price_History", rows=1000, cols=5)
        ws.append_row(["Date", "Product_name", "Store", "Price", "Regular_price"], value_input_option='USER_ENTERED')
        return ws


def load_existing_listings(worksheet):
    """Load all existing rows into a dict for fast lookup.

    Returns:
        dict: {(product_name, store): {
            'row': row_number,
            'price': current_price (float or None),
            'reg_price': regular_price (float or None)
        }}
    """
    print("  Loading existing sheet data (1 API read)...")
    all_values = worksheet.get_all_values()
    existing = {}
    if len(all_values) < 2:
        return existing
        
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) >= 3:
            name  = row[COL_PRODUCT_NAME - 1].strip()
            category = row[COL_CATEGORY - 1].strip() if len(row) >= COL_CATEGORY else ""
            store = row[COL_STORE - 1].strip() if len(row) >= COL_STORE else ""
            
            price = None
            if len(row) >= COL_CURRENT_PRICE:
                p_val = row[COL_CURRENT_PRICE - 1].replace('$', '').replace(',', '').strip()
                try:
                    price = float(p_val) if p_val else None
                except ValueError:
                    price = None
            
            reg_price = None
            if len(row) >= COL_REGULAR_PRICE:
                rp_val = row[COL_REGULAR_PRICE - 1].replace('$', '').replace(',', '').strip()
                try:
                    reg_price = float(rp_val) if rp_val else None
                except ValueError:
                    reg_price = None

            image = ""
            if len(row) >= COL_IMAGE_URL:
                image = row[COL_IMAGE_URL - 1].strip()

            canonical_id = ""
            if len(row) >= COL_CANONICAL_ID:
                canonical_id = row[COL_CANONICAL_ID - 1].strip()

            if name and store:
                existing[(name, store)] = {
                    'row': i,
                    'price': price,
                    'reg_price': reg_price,
                    'image': image,
                    'canonical_id': canonical_id,
                    'category': category
                }
    print(f"  Found {len(existing)} existing listings in sheet.")
    return existing


def batch_upsert(worksheet, store_name, new_rows, price_updates, history_rows=None):
    """Write all new rows, price updates, and history logs in bulk.

    Args:
        worksheet: gspread Worksheet object (Listings)
        store_name: str
        new_rows: list of lists
        price_updates: list of (row_number, price, [optional reg_price]) tuples
        history_rows: list of lists to append to Price_History
    """
    created = 0
    updated = 0

    # 1. Append new rows to Listings
    if new_rows:
        print(f"  Appending {len(new_rows)} new {store_name} rows...")
        worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')
        created = len(new_rows)
        time.sleep(2) # Adaptive Rate Limiting

    # 2. Update existing prices in Listings (Optimized Row-Level Range Updates)
    if price_updates:
        print(f"  Updating {len(price_updates)} existing {store_name} rows (Range-based)...")
        batch_data = []
        for update in price_updates:
            # Expecting update format: (row_num, [category, store, price, reg_price, in_stock, image, canonical_id])
            if len(update) >= 2 and isinstance(update[1], list):
                row_num = update[0]
                values = update[1]
                # Range from Category (C) to Canonical ID (I)
                range_a1 = f"C{row_num}:I{row_num}"
                batch_data.append({
                    'range': range_a1,
                    'values': [values]
                })
            else:
                # Legacy fallback
                row_num = update[0]
                price = update[1]
                batch_data.append({
                    'range': gspread.utils.rowcol_to_a1(row_num, COL_CURRENT_PRICE),
                    'values': [[price]]
                })
                if len(update) > 2 and update[2] is not None:
                    batch_data.append({
                        'range': gspread.utils.rowcol_to_a1(row_num, COL_REGULAR_PRICE),
                        'values': [[update[2]]]
                    })

        if batch_data:
            worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')
            updated = len(price_updates)
            time.sleep(2)
    # 3. Append to Price_History
    if history_rows:
        print(f"  Logging {len(history_rows)} price changes to Price_History...")
        history_ws = get_history_worksheet()
        history_ws.append_rows(history_rows, value_input_option='USER_ENTERED')

    return created, updated


def update_listing_price(worksheet, listing_name, new_price):
    """Legacy single-cell update."""
    cell = worksheet.find(listing_name)
    if cell:
        worksheet.update(range_name=gspread.utils.rowcol_to_a1(cell.row, COL_CURRENT_PRICE), 
                         values=[[new_price]])
        return True
    return False
