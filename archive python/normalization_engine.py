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
            norm_size = f"{raw_val:g}{raw_unit}"
        elif raw_unit in ['ml', 'l']:
            std_qty = raw_val / 1000.0 if raw_unit == 'ml' else raw_val
            u_type = "L"
            norm_size = f"{raw_val:g}{raw_unit.upper() if raw_unit == 'l' else raw_unit}"
        else:
            std_qty = raw_val
            u_type = "EA"
            norm_size = f"{raw_val:g}pk"

    return {
        'std_qty': std_qty,
        'u_type': u_type,
        'norm_size': norm_size,
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
    if not head_nouns:
        tokens = [t.text for t in doc if not t.is_stop]
        head_nouns = [tokens[-1]] if tokens else ["product"]
    
    clean_name = " ".join(sorted(list(set(modifiers))) + sorted(list(set(head_nouns)))).title()
    commodity_id = "-".join(["commodity"] + sorted(list(set(modifiers))) + sorted(list(set(head_nouns))))
    return clean_name, commodity_id, primary_head

class EnterpriseETL:
    def process_row(self, raw_name: str, category: str, price: float) -> dict:
        name_lower = raw_name.lower()
        cat_lower = category.lower() if category else ""
        metrics = extract_metrics(raw_name)
        
        # 1. LEXICAL NAME FENCE
        is_junk = any(junk in name_lower for junk in JUNK_KEYWORDS)

        is_non_commodity_cat = any(c in cat_lower for c in NON_COMMODITY_CATEGORIES)
        is_commodity_cat = any(c in cat_lower for c in COMMODITY_CATEGORIES)
        if not category and not is_non_commodity_cat:
            is_commodity_cat = any(kw in name_lower for kw in COMMODITY_KEYWORDS)

        if not is_junk and is_commodity_cat and not is_non_commodity_cat:
            clean_base, comm_id, head_noun = nlp_lexical_parser(raw_name, metrics['match_str'])
            
            # EGG WEIGHT TRAP
            is_egg = head_noun == "egg" or "egg" in comm_id
            is_small_egg = False
            if is_egg:
                if metrics['u_type'] == 'KG' and metrics['std_qty'] < 0.3: is_small_egg = True
                elif metrics['u_type'] == 'EA' and metrics['raw_val'] < 1: is_small_egg = True
            
            if not is_small_egg:
                u_price = ""
                if price and metrics['std_qty'] > 0:
                    u_price = f"${(price / metrics['std_qty']):.2f}/{metrics['u_type']}"

                # FIX THE "0" BUG: Only append norm_size if it exists and raw_val > 0
                final_name = clean_base
                if metrics['norm_size'] and metrics['raw_val'] > 0:
                     final_name = f"{clean_base} {metrics['norm_size']}"

                return {
                    'name': final_name.strip(),
                    'id': comm_id,
                    'unit_price': u_price,
                    'is_commodity': True
                }
            else:
                return self._bypass(raw_name, price)
        else:
            return self._bypass(raw_name, price)

    def _bypass(self, raw_name: str, price: float) -> dict:
        slug = re.sub(r'[^a-z0-9\s]', '', raw_name.lower())
        return {
            'name': raw_name.title().strip(),
            'id': re.sub(r'\s+', '-', slug.strip()),
            'unit_price': f"${price:.2f}" if price else "",
            'is_commodity': False
        }

def main():
    parser = argparse.ArgumentParser(description="NLP Normalization Reconstruction V13 (Relational Join)")
    parser.add_argument("--apply", action="store_true", help="Commit changes to Google Sheets")
    args = parser.parse_args()

    etl = EnterpriseETL()
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        if os.path.exists(CREDS_FILE):
             creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        else: return print("Error: credentials.json not found.")
        
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_ID)
        
        # 1. Relational Map {ID: Pristine_Name} from Products
        print("Indexing Products for pristine names...")
        ws_p = sh.worksheet("Products")
        p_data = ws_p.get_all_values()
        p_headers = [h.strip().strip("'").strip('"') for h in p_data[0]]
        p_name_idx = p_headers.index("Product_name")
        p_cid_idx = p_headers.index("Canonical_ID")
        
        id_to_pristine = {row[p_cid_idx]: row[p_name_idx] for row in p_data[1:] if len(row) > max(p_name_idx, p_cid_idx)}
        print(f"Index complete: {len(id_to_pristine)} pristine IDs mapped.")

        # 2. Target Listings
        print("Opening Listings for restoration...")
        ws_l = sh.worksheet("Listings")
        l_data = ws_l.get_all_values()
        l_headers = [h.strip().strip("'").strip('"') for h in l_data[0]]
        
        def get_idx(name):
            try: return l_headers.index(name)
            except ValueError: raise ValueError(f"Required column '{name}' missing from Listings.")

        l_name_idx = get_idx("Product_name")
        l_cat_idx = get_idx("Category")
        l_cid_idx = get_idx("Canonical_ID")
        l_price_idx = get_idx("Current_price")
        
        try: l_up_idx = l_headers.index("Unit_Price")
        except ValueError:
            print("Mapping missing Unit_Price column via dynamic injection...")
            l_up_idx = len(l_headers)
            ws_l.update_cell(1, l_up_idx + 1, "Unit_Price")

        print(f"--- Relational NLP Reconstruction (Apply={args.apply}) ---")
        updates = []
        dry_run_samples = []

        for i, row in enumerate(l_data[1:], start=2):
            if len(row) <= max(l_name_idx, l_cat_idx, l_cid_idx, l_price_idx): continue
            
            l_id = row[l_cid_idx].strip()
            l_cat = row[l_cat_idx].strip()
            l_price_str = row[l_price_idx].replace('$', '').replace(',', '').strip()
            l_price = float(l_price_str) if l_price_str else None
            
            # BYPASS CORRUPTION: Source name from Products map
            pristine_name = id_to_pristine.get(l_id, row[l_name_idx])
            
            res = etl.process_row(pristine_name, l_cat, l_price)

            if args.apply:
                updates.append({'range': rowcol_to_a1(i, l_name_idx + 1), 'values': [[res['name']]]})
                updates.append({'range': rowcol_to_a1(i, l_cid_idx + 1), 'values': [[res['id']]]})
                updates.append({'range': rowcol_to_a1(i, l_up_idx + 1), 'values': [[res['unit_price']]]})
            else:
                if len(dry_run_samples) < 5:
                    dry_run_samples.append((pristine_name, res['name']))

        if not args.apply:
            print("\n--- Dry Run Preview: Fix '0' Bug & Restoration ---")
            for raw, clean in dry_run_samples:
                print(f"[RECOVERED] '{raw}' -> '{clean}'")
            print(f"\nTotal potential restorations: {len(l_data)-1}. To commit, run: python normalization_engine.py --apply")
        else:
            if updates:
                print(f"Executing {len(updates)//3} row repairs via batch sync...")
                BATCH = 500
                for j in range(0, len(updates), BATCH):
                    ws_l.batch_update(updates[j:j+BATCH], value_input_option='USER_ENTERED')
                print("Relational NLP Reconstruction Successful.")

    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    main()
