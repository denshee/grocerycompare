import time
import random
import re
import json
from curl_cffi import requests
import sheets_helper

STORE_NAME = "Coles"
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken", "beef", "apples", "bananas"]

def find_products(obj):
    """Recursively search the massive JSON block for product data"""
    products = []
    if isinstance(obj, dict):
        # Look for Coles specific product identifiers
        if obj.get('_type') == 'PRODUCT' or 'pricing' in obj and 'brand' in obj:
            products.append(obj)
        else:
            for v in obj.values():
                products.extend(find_products(v))
    elif isinstance(obj, list):
        for item in obj:
            products.extend(find_products(item))
    return products

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    all_new_rows, all_updates = [], []
    seen_names = set()

    for term in SEARCH_TERMS:
        print(f"  [SSR EXTRACTION] Fetching: {term}")
        try:
            url = f"https://www.coles.com.au/search?q={term}"
            
            # Impersonate Chrome at the network TLS level to bypass Akamai
            r = requests.get(url, impersonate="chrome124", timeout=30)
            
            if r.status_code != 200:
                print(f"    ⚠️ Blocked by Server (Status {r.status_code})")
                continue

            # Extract the hidden Next.js JSON payload from the HTML source
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
            
            if not match:
                print(f"    ⚠️ No SSR data found. Coles served a challenge page.")
                continue

            # Load the massive JSON block and hunt for products
            raw_data = json.loads(match.group(1))
            products = find_products(raw_data)
            
            items_found = 0
            for p in products:
                brand = p.get('brand', '')
                name_part = p.get('name', '')
                full_name = f"{brand} {name_part}".strip()
                
                if not full_name or full_name in seen_names: continue
                seen_names.add(full_name)

                pricing = p.get("pricing", {})
                price = pricing.get("now")
                
                img_id = p.get("imageUris", [{}])[0].get("uri", "")
                img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""

                if full_name and price:
                    items_found += 1
                    key = (full_name, STORE_NAME)
                    if key in existing:
                        old = existing[key]
                        all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img_url, ""]))
                    else:
                        all_new_rows.append(["", full_name, "Pantry", STORE_NAME, price, "", "TRUE", img_url])
            
            print(f"    Successfully extracted {items_found} items.")
            time.sleep(random.uniform(2, 4))
            
        except Exception as e:
            print(f"    ❌ Critical extraction error: {e}")
            continue

    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()