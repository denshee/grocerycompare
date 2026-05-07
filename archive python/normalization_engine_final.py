import gspread
import re
import os
import argparse
import spacy
import traceback
from typing import Dict, List, Tuple, Optional
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

# --- Configuration ---
CREDS_FILE = 'credentials.json'
SHEET_ID = os.getenv('GOOGLE_SHEET_ID') or '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'

# Fencing Data
NON_COMMODITY_CATEGORIES = ['confectionery', 'chocolate', 'easter', 'pantry', 'drinks', 'snacks', 'health', 'beauty', 'household', 'toiletries']
COMMODITY_CATEGORIES = ['dairy', 'eggs', 'meat', 'poultry', 'seafood', 'fruit', 'veg', 'produce', 'bakery', 'fridge']
JUNK_KEYWORDS = ['chocolate', 'easter', 'foiled', 'raspberry', 'gift box', 'mini', 'candy', 'hollow', 'dairy fine', 'creme']
COMMODITY_KEYWORDS = ['egg', 'milk', 'beef', 'mince', 'pork', 'chicken', 'lamb', 'apple', 'banana', 'steak', 'sausage', 'breast', 'thigh', 'whole milk']
STRIP_BRANDS = ['coles', 'woolworths', 'aldi', 'macro', 'homebrand', 'essentials', 'farmdale', 'paddock', 'hill view', 'community co']

# Initialize spaCy
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Error: spaCy model 'en_core_web_sm' not found.")
    exit(1)

def extract_metrics(name: str) -> dict:
    metric_pattern = r'(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pk|pack|ea|s|tabs|capsules|pcs)\b'
    match = re.search(metric_pattern, name.lower())
    
    std_qty = 1.0
    u_type = "EA"
    norm_size = ""
    raw_val = 0
    raw_unit = ""
    match_str = ""

    if match:
        match_str = match.group(0)
        raw_val = float(match.group(1))
        raw_unit = match.group(2).lower()

        if raw_unit in ['g', 'kg']:
            std_qty = raw_val / 1000.0 if raw_unit == 'g' else raw_val
            u_type = "KG"
        elif raw_unit in ['ml', 'l']:
            std_qty = raw_val / 1000.0 if raw_unit == 'ml' else raw_val
            u_type = "L"
        else:
            std_qty = raw_val
            u_type = "EA"

    return {
        'std_qty': std_qty,
        'u_type': u_type,
        'raw_val': raw_val,
        'raw_unit': raw_unit,
        'match_str': match_str
    }

def nlp_lexical_parser(raw_name: str, match_str: str) -> Tuple[str, str, str]:
    temp_name = raw_name.lower()
    if match_str:
        temp_name = temp_name.replace(match_str.lower(), ' ')
    temp_name = re.sub(r'(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pk|pack|ea|s|tabs|capsules)\b', ' ', temp_name)
    for brand in STRIP_BRANDS:
        temp_name = re.sub(rf'\b{brand}\b', ' ', temp_name)
    temp_name = re.sub(r'[^a-z0-9\- ]', ' ', temp_name)
    temp_name = re.sub(r'\s+', ' ', temp_name).strip()

    doc = nlp(temp_name)
    head_nouns = [token.lemma_ for token in doc if token.pos_ in ['NOUN', 'PROPN']]
    modifiers = [token.text for token in doc if token.pos_ in ['ADJ']]
    
    primary_head = head_nouns[-1] if head_nouns else "product"
    
    parts = sorted(list(set(modifiers))) + sorted(list(set(head_nouns)))
    slug_base = "-".join(parts)
    return slug_base, primary_head

class AdditiveETL:
    def process_row(self, raw_name: str, category: str, store: str, price: float) -> dict:
        name_lower = raw_name.lower()
        cat_lower = category.lower() if category else ""
        store_lower = (store or "unknown").lower()
        metrics = extract_metrics(raw_name)
        
        # 1. LEXICAL NAME FENCE
        is_junk = any(junk in name_lower for junk in JUNK_KEYWORDS)

        is_non_commodity_cat = any(c in cat_lower for c in NON_COMMODITY_CATEGORIES)
        is_commodity_cat = any(c in cat_lower for c in COMMODITY_CATEGORIES)
        if not category and not is_non_commodity_cat:
            is_commodity_cat = any(kw in name_lower for kw in COMMODITY_KEYWORDS)

        if not is_junk and is_commodity_cat and not is_non_commodity_cat:
            slug_base, head_noun = nlp_lexical_parser(raw_name, metrics['match_str'])
            
            # EGG WEIGHT TRAP
            is_egg = head_noun == "egg" or "egg" in slug_base
            is_small_egg = False
            if is_egg:
                if metrics['u_type'] == 'KG' and metrics['std_qty'] < 0.3: is_small_egg = True
                elif metrics['u_type'] == 'EA' and metrics['raw_val'] < 1: is_small_egg = True
            
            if not is_small_egg:
                u_price = ""
                if price and metrics['std_qty'] > 0:
                    u_price = f"${(price / metrics['std_qty']):.2f}/{metrics['u_type']}"

                return {
                    'id': f"staple-{slug_base}",
                    'unit_price': u_price
                }
            else:
                return self._bypass(raw_name, store_lower, price)
        else:
            return self._bypass(raw_name, store_lower, price)

    def _bypass(self, raw_name: str, store: str, price: float) -> dict:
        slug = re.sub(r'[^a-z0-9\s]', '', raw_name.lower())
        branded_slug = re.sub(r'\s+', '-', slug.strip())
        return {
            'id': f"{store}-{branded_slug}",
            'unit_price': f"${price:.2f}" if price else ""
        }

def main():
    parser = argparse.ArgumentParser(description="Normalization Engine Final (Strictly Additive)")
    parser.add_argument("--apply", action="store_true", help="Commit changes to Google Sheets")
    args = parser.parse_args()

    etl = AdditiveETL()
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        if os.path.exists(CREDS_FILE):
             creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        else: return print("Error: credentials.json not found.")
        
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_ID)
        
        print("Opening Listings for additive enrichment...")
        ws = sh.worksheet("Listings")
        raw_data = ws.get_all_values()
        headers = [h.strip() for h in raw_data[0]]
        
        # REQUIRED INPUTS
        def find_col(possible_names):
            for name in possible_names:
                if name in headers: return headers.index(name)
            return None

        name_idx = find_col(["Product_name", "Product name", "Name"])
        cat_idx = find_col(["Category", "Dept"])
        store_idx = find_col(["Store", "Retailer"])
        price_idx = find_col(["Current_price", "Price", "Now_Price"])

        if name_idx is None: raise ValueError("Critical column 'Product_name' not found.")

        # TARGET OUTPUTS (Column I and J)
        # Column I = Index 8, Column J = Index 9
        target_cid_idx = 8
        target_up_idx = 9

        if args.apply:
            # Initialize headers if empty or different
            if len(headers) <= target_up_idx:
                print(f"Enlarging header row to accommodate Column I/J...")
                # Pad headers if needed
                while len(headers) <= target_up_idx: headers.append("")
                headers[target_cid_idx] = "Canonical_ID"
                headers[target_up_idx] = "Unit_Price"
                ws.update("A1:Z1", [headers])

        print(f"--- Additive Normalization V14 (Apply={args.apply}) ---")
        print(f"Mapping: Name={name_idx}, Cat={cat_idx}, Price={price_idx}")
        
        updates = []
        dry_samples = []

        for i, row in enumerate(raw_data[1:], start=2):
            raw_name = row[name_idx].strip() if len(row) > name_idx else ""
            if not raw_name: continue

            cat = row[cat_idx].strip() if (cat_idx is not None and len(row) > cat_idx) else ""
            store = row[store_idx].strip() if (store_idx is not None and len(row) > store_idx) else "unknown"
            
            price = None
            if price_idx is not None and len(row) > price_idx:
                price_str = row[price_idx].replace('$', '').replace(',', '').strip()
                try: price = float(price_str) if price_str else None
                except: price = None

            res = etl.process_row(raw_name, cat, store, price)

            if args.apply:
                updates.append({'range': rowcol_to_a1(i, target_cid_idx + 1), 'values': [[res['id']]]})
                updates.append({'range': rowcol_to_a1(i, target_up_idx + 1), 'values': [[res['unit_price']]]})
            else:
                if len(dry_samples) < 10:
                    dry_samples.append((raw_name, res['id'], res['unit_price']))

        if not args.apply:
            print("\n--- Dry Run Preview (Additive Slot I/J) ---")
            for raw, sid, up in dry_samples:
                print(f"[PREVIEW] '{raw}' -> ID: {sid} | UP: {up}")
            print(f"\nPotential enrichment for {len(raw_data)-1} rows. Run with --apply to commit to Columns I/J.")
        else:
            if updates:
                print(f"Executing {len(updates)//2} additive enrichments via batch sync...")
                BATCH = 1000
                for j in range(0, len(updates), BATCH):
                    ws.batch_update(updates[j:j+BATCH], value_input_option='USER_ENTERED')
                print("Additive Enrichment Successful. Metadata columns I (ID) and J (Unit_Price) populated.")

    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    main()
