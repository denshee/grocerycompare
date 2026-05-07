import argparse
import random
import sys
import time
import json
from datetime import datetime
from curl_cffi import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import sheets_helper

STORE_NAME = "Woolworths"
BATCH_WRITE_EVERY = 200 # Smaller batches for safety

WOOLWORTHS_CATEGORIES = [
    "1-E5BEE36E", # Fruit & Veg
    "1_D5A2236",  # Meat, Seafood & Deli
    "1_6E4E4E4",  # Dairy, Eggs & Fridge
    "1_9E9293F",  # Bakery
    "1_39FD497",  # Pantry
    "1_AC21391",  # Frozen-foods
    "1_5AF3A0A",  # Drinks
    "1_8E4E4E4",  # Health & Beauty
    "1_2432B53",  # Household
]

def clean_price(val) -> float | None:
    if val is None: return None
    try:
        return float(val)
    except:
        return None

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
def fetch_woolies_page(category_id, page_number):
    """Hits the Woolworths internal API with Chrome Impersonation."""
    url = "https://www.woolworths.com.au/apis/ui/browse/category"
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "origin": "https://www.woolworths.com.au",
        "referer": "https://www.woolworths.com.au/shop/browse/",
    }
    params = {
        "categoryId": category_id,
        "pageNumber": page_number,
        "pageSize": 36,
        "sortType": "Name",
        "url": "/shop/browse/"
    }
    
    # Impersonate Chrome 124
    r = requests.get(url, params=params, headers=headers, impersonate="chrome124", timeout=30)
    
    if r.status_code == 403:
        print("      [403] Akamai Block! Cooling down...")
        raise Exception("Blocked by Akamai")
        
    return r.json()

def batch_write(worksheet, products_buffer, existing, written_names):
    new_rows = []
    price_updates = []
    history_rows = []
    now_str = datetime.now().strftime("%Y-%m-%d")

    for p in products_buffer:
        name = p["name"]
        if name in written_names: continue
        key = (name, STORE_NAME)
        
        if key in existing:
            old = existing[key]
            # Update if price changed, or if category/image is missing
            cat_needed = (not old.get('category') or old.get('category') == "Uncategorized")
            img_needed = (not old.get('image') or "placeholder" in old.get('image', '').lower())
            
            if p["price"] != old['price'] or cat_needed or img_needed:
                price_updates.append((
                    old['row'], 
                    p["price"], 
                    p["was_price"], 
                    p["image"] if img_needed else None,
                    p["category"] if cat_needed else None
                ))
                if p["price"] != old['price']:
                    history_rows.append([now_str, name, STORE_NAME, p["price"], p["was_price"] or ""])
        else:
            new_rows.append(["", name, p["category"], STORE_NAME, p["price"], p["was_price"] or "", "TRUE", p["image"]])
            existing[key] = {'row': -1, 'price': p['price'], 'category': p['category']}
        
        written_names.add(name)

    return sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, price_updates, history_rows)

def main():
    print("\n[Phase 1] Connecting to Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    
    total_created, total_updated = 0, 0
    written_names = set()

    for cat_id in WOOLWORTHS_CATEGORIES:
        print(f"\n  Scraping Category ID: {cat_id}")
        page = 1
        buffer = []
        
        while True:
            try:
                print(f"      Page {page}...")
                data = fetch_woolies_page(cat_id, page)
                bundles = data.get('Bundles', [])
                if not bundles: break
                
                for b in bundles:
                    prod = b.get('Products', [{}])[0]
                    if not prod: continue
                    
                    name = prod.get('Name')
                    price = clean_price(prod.get('Price'))
                    was_price = clean_price(prod.get('WasPrice'))
                    img = prod.get('MediumImageFile')
                    
                    if name and price:
                        buffer.append({
                            "name": name,
                            "price": price,
                            "was_price": was_price,
                            "category": "Uncategorized", # To be mapped by Aisle logic later
                            "image": img
                        })

                if len(buffer) >= BATCH_WRITE_EVERY:
                    c, u = batch_write(worksheet, buffer, existing, written_names)
                    total_created += c
                    total_updated += u
                    buffer = []
                
                time.sleep(random.uniform(2, 5)) # Safety Jitter
                page += 1
                if page > 50: break # Safety cap
                
            except Exception as e:
                print(f"      Error: {e}")
                break
        
        if buffer:
            c, u = batch_write(worksheet, buffer, existing, written_names)
            total_created += c
            total_updated += u

    print(f"\nFinished. Total Created: {total_created}, Updated: {total_updated}")

if __name__ == "__main__":
    main()