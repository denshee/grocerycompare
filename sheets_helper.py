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

# --- Categorization Intelligence ---
CATEGORY_MAPPING = {
    "Fruit & Veg": ["apple", "banana", "potato", "onion", "carrot", "broccoli", "tomato", "berry", "fruit", "veg", "lettuce", "avocado", "cucumber", "capsicum", "mushroom"],
    "Meat & Seafood": ["chicken", "beef", "lamb", "pork", "steak", "mince", "salmon", "prawn", "sausage", "bacon", "ham", "seafood", "meat", "fish", "roast"],
    "Dairy, Eggs & Fridge": ["milk", "cheese", "yoghurt", "butter", "egg", "cream", "margarine", "dip", "dairy", "feta", "parmesan", "sour cream"],
    "Bakery": ["bread", "muffin", "crumpet", "croissant", "toast", "bakery", "wrap", "pita", "bagel", "sourdough", "roll"],
    "Pantry": ["rice", "pasta", "flour", "sugar", "sauce", "oil", "tuna", "canned", "honey", "jam", "peanut butter", "cereal", "oats", "spice", "salt", "spaghetti", "weet-bix", "mayonnaise"],
    "Frozen": ["frozen", "ice cream", "pizza", "chips", "peas", "meal", "frozen berries"],
    "Snacks & Confectionery": ["chip", "chocolate", "lolly", "biscuit", "cookie", "nut", "cracker", "popcorn", "confectionery"],
    "Drinks": ["juice", "water", "soda", "coke", "coffee", "tea", "drink", "sparkling", "soft drink"],
    "Household": ["detergent", "soap", "paper", "bag", "cleaner", "shampoo", "toothpaste", "nappy", "wipe", "pet", "sunscreen", "dishwashing", "garbage"],
}

def auto_categorize(name, current_cat):
    if current_cat and current_cat != "Uncategorized":
        return current_cat
    name_lower = name.lower()
    for cat, keywords in CATEGORY_MAPPING.items():
        if any(kw in name_lower for kw in keywords):
            return cat
    return "Uncategorized"

# --- Column Indices (1-based) ---
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

def load_existing_listings(worksheet):
    print("  Loading existing sheet data...")
    all_values = worksheet.get_all_values()
    existing = {}
    if len(all_values) < 2: return existing
        
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) >= 4:
            name = row[COL_PRODUCT_NAME - 1].strip()
            store = row[COL_STORE - 1].strip()
            
            def parse_f(val):
                if not val: return None
                try: return float(val.replace('$', '').replace(',', '').strip())
                except: return None

            existing[(name, store)] = {
                'row': i,
                'category': row[COL_CATEGORY - 1].strip() if len(row) >= COL_CATEGORY else "",
                'price': parse_f(row[COL_CURRENT_PRICE - 1]) if len(row) >= COL_CURRENT_PRICE else None,
                'reg_price': parse_f(row[COL_REGULAR_PRICE - 1]) if len(row) >= COL_REGULAR_PRICE else None,
                'image': row[COL_IMAGE_URL - 1].strip() if len(row) >= COL_IMAGE_URL else "",
                'canonical_id': row[COL_CANONICAL_ID - 1].strip() if len(row) >= COL_CANONICAL_ID else ""
            }
    return existing

def batch_upsert(worksheet, store_name, new_rows, price_updates, history_rows=None):
    created = 0
    updated = 0

    # 1. NEW ROWS: Ensure 8 columns exactly [ID, Name, Cat, Store, Price, WasPrice, Stock, Image]
    if new_rows:
        formatted_new = []
        for r in new_rows:
            r[2] = auto_categorize(r[1], r[2]) # Auto-cat by Name
            formatted_new.append(r[:8]) # Trim/Pad to 8 columns
        worksheet.append_rows(formatted_new, value_input_option='USER_ENTERED')
        created = len(formatted_new)

    # 2. UPDATES: Ensure 7 columns exactly for Range C:I
    if price_updates:
        batch_data = []
        for row_num, values in price_updates:
            # values must be: [Category, Store, Price, WasPrice, InStock, Image, CanonicalID]
            # Ensure it is exactly 7 items long to fill C through I
            if len(values) == 7:
                batch_data.append({
                    'range': f"C{row_num}:I{row_num}",
                    'values': [values]
                })

        if batch_data:
            worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')
            updated = len(price_updates)

    return created, updated