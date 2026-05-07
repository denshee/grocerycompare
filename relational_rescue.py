import os
import gspread
import argparse
import traceback
import re
import spacy
from typing import Dict, List, Tuple, Optional
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

# --- Configuration ---
CREDS_FILE = 'credentials.json'
SHEET_ID = os.getenv('GOOGLE_SHEET_ID') or '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k'

# Load spaCy for on-the-fly ID alignment
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Error: spaCy model 'en_core_web_sm' not found.")
    exit(1)

# --- Normalization Re-implementation (from normalization_engine.py V11) ---
JUNK_KEYWORDS = ['chocolate', 'easter', 'foiled', 'raspberry', 'gift box', 'mini', 'candy', 'hollow', 'dairy fine']
COMMODITY_CATEGORIES = ['dairy', 'eggs', 'meat', 'poultry', 'seafood', 'fruit', 'veg', 'produce', 'bakery', 'fridge']
COMMODITY_KEYWORDS = ['egg', 'milk', 'beef', 'mince', 'pork', 'chicken', 'lamb', 'apple', 'banana', 'steak', 'sausage', 'breast', 'thigh', 'whole milk']
STRIP_BRANDS = ['coles', 'woolworths', 'aldi', 'macro', 'homebrand', 'essentials', 'farmdale', 'paddock', 'hill view', 'community co']

def extract_metrics(name: str) -> dict:
    match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pk|pack|ea|s|tabs|capsules|pcs)\b', name.lower())
    u_type = "EA"
    std_qty = 1.0
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
    return {'u_type': u_type, 'std_qty': std_qty, 'raw_val': raw_val, 'raw_unit': raw_unit, 'match_str': match_str}

def get_normalized_id(raw_name: str, category: str) -> str:
    name_lower = raw_name.lower()
    cat_lower = category.lower() if category else ""
    metrics = extract_metrics(raw_name)
    
    is_junk = any(junk in name_lower for junk in JUNK_KEYWORDS)
    is_egg_suspect = "egg" in name_lower
    is_small_egg = False
    if is_egg_suspect:
        if metrics['u_type'] == 'KG' and metrics['std_qty'] < 0.3: is_small_egg = True
        elif metrics['u_type'] == 'EA' and metrics['raw_val'] < 1: is_small_egg = True

    is_commodity_cat = any(c in cat_lower for c in COMMODITY_CATEGORIES)
    if not category: is_commodity_cat = any(kw in name_lower for kw in COMMODITY_KEYWORDS)
    
    should_bypass = is_junk or is_small_egg or not is_commodity_cat

    if not should_bypass:
        temp_name = name_lower
        if metrics['match_str']: temp_name = temp_name.replace(metrics['match_str'].lower(), ' ')
        temp_name = re.sub(r'(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pk|pack|ea|s|tabs|capsules)\b', ' ', temp_name)
        for brand in STRIP_BRANDS: temp_name = re.sub(rf'\b{brand}\b', ' ', temp_name)
        temp_name = re.sub(r'[^a-z0-9\- ]', ' ', temp_name)
        temp_name = re.sub(r'\s+', ' ', temp_name).strip()
        doc = nlp(temp_name)
        head_nouns = [token.lemma_ for token in doc if token.pos_ in ['NOUN', 'PROPN']]
        modifiers = [token.text for token in doc if token.pos_ in ['ADJ']]
        if not head_nouns: 
            tokens = [t.text for t in doc if not t.is_stop]
            head_nouns = [tokens[-1]] if tokens else ["product"]
        unique_mods = sorted(list(set(modifiers)))
        unique_nouns = sorted(list(set(head_nouns)))
        return "-".join(["commodity"] + unique_mods + unique_nouns)
    else:
        clean = re.sub(r'[^a-z0-9\s]', '', name_lower)
        return re.sub(r'\s+', '-', clean.strip())

class RelationalRescue:
    def __init__(self):
        self.scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        self.client = self._authorize()
        self.sh = self.client.open_by_key(SHEET_ID)

    def _authorize(self):
        if os.path.exists(CREDS_FILE):
            creds = Credentials.from_service_account_file(CREDS_FILE, scopes=self.scopes)
        else:
            raise FileNotFoundError(f"Credential file '{CREDS_FILE}' not found.")
        return gspread.authorize(creds)

    def map_headers(self, ws) -> Dict[str, int]:
        headers = ws.row_values(1)
        return {header.strip().strip("'").strip('"'): i for i, header in enumerate(headers)}

    def run_rescue(self, apply: bool = False):
        try:
            print(f"--- Relational Rescue Initiative (Apply={apply}) ---")
            ws_products = self.sh.worksheet("Products")
            ws_listings = self.sh.worksheet("Listings")
            p_map = self.map_headers(ws_products)
            l_map = self.map_headers(ws_listings)

            required_p = ["Product_name", "Category", "Primary_Image"]
            required_l = ["Canonical_ID", "Image_URL"]
            for col in required_p:
                 if col not in p_map: raise ValueError(f"Missing column '{col}' in Products!")
            for col in required_l:
                 if col not in l_map: raise ValueError(f"Missing column '{col}' in Listings!")

            # 1. Index Products by Normalized IDs
            print("Mapping Products by on-the-fly NLP normalization...")
            p_data = ws_products.get_all_values()
            id_to_image = {}
            for row in p_data[1:]:
                name = row[p_map["Product_name"]].strip()
                cat = row[p_map["Category"]].strip()
                img = row[p_map["Primary_Image"]].strip()
                if name and img:
                    norm_id = get_normalized_id(name, cat)
                    id_to_image[norm_id] = img
            print(f"Index complete: {len(id_to_image)} products mapped.")

            # 2. Iterate and Repair Listings
            print("Analyzing Listings for recovery...")
            l_data = ws_listings.get_all_values()
            updates = []
            dry_run_samples = []

            for i, row in enumerate(l_data[1:], start=2):
                l_cid = row[l_map["Canonical_ID"]].strip()
                current_img = row[l_map["Image_URL"]].strip() if len(row) > l_map["Image_URL"] else ""
                
                if l_cid in id_to_image:
                    target_img = id_to_image[l_cid]
                    # We repair if current is empty, corrupted, or different
                    # (Corruption usually means missing https or localhost placeholder)
                    is_corrupted = not current_img.startswith("http") or "localhost" in current_img
                    
                    if is_corrupted or target_img != current_img:
                        if apply:
                            updates.append({
                                'range': rowcol_to_a1(i, l_map["Image_URL"] + 1),
                                'values': [[target_img]]
                            })
                        else:
                            if len(dry_run_samples) < 5:
                                dry_run_samples.append((l_cid, target_img))

            if not apply:
                print("\n--- Dry Run Preview ---")
                for cid, img in dry_run_samples:
                    print(f"[RECOVERED] {cid} -> {img}")
                print(f"Total potential repairs: {len(updates) if apply else len([u for u in l_data[1:] if u[l_map['Canonical_ID']] in id_to_image])}")
                print("\nTo execute, run: python relational_rescue.py --apply")
            else:
                if updates:
                    print(f"Executing {len(updates)} repairs...")
                    WS_BATCH_SIZE = 500
                    for j in range(0, len(updates), WS_BATCH_SIZE):
                        ws_listings.batch_update(updates[j:j+WS_BATCH_SIZE], value_input_option='USER_ENTERED')
                    print("Relational repair successful.")
                else:
                    print("No repairs needed.")

        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    RelationalRescue().run_rescue(apply=args.apply)
