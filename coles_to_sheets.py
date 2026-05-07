import time
import random
from curl_cffi import requests
from datetime import datetime
import sheets_helper

STORE_NAME = "Coles"
# We hit the 'Best Sellers' / 'Top Rated' logic directly through the API
CATEGORIES = [
    {"name": "Fruit & Veg", "slug": "fruit-vegetables"},
    {"name": "Meat & Seafood", "slug": "meat-seafood"},
    {"name": "Dairy & Eggs", "slug": "dairy-eggs-fridge"},
    {"name": "Bakery", "slug": "bakery"}
]

def fetch_coles_api(slug):
    # This endpoint is what the actual website uses to load products
    url = f"https://www.coles.com.au/api/bff/products/browse/{slug}?page=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.coles.com.au/",
    }
    
    # impersonate="chrome124" is the secret sauce. It mimics a real Chrome SSL handshake.
    r = requests.get(url, headers=headers, impersonate="chrome124", timeout=30)
    
    if r.status_code != 200:
        print(f"    ❌ API Blocked ({r.status_code}) for {slug}")
        return []
        
    data = r.json()
    return data.get("results", [])

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    
    all_new_rows = []
    all_updates = []

    for cat in CATEGORIES:
        print(f"  Fetching Coles Category: {cat['name']}")
        products = fetch_coles_api(cat['slug'])
        
        for p in products:
            if p.get("_type") != "PRODUCT": continue
            
            brand = p.get('brand', '')
            p_name = p.get('name', '')
            full_name = f"{brand} {p_name}".strip()
            
            pricing = p.get("pricing", {})
            price = pricing.get("now")
            was_price = pricing.get("was")
            
            img_id = p.get("imageUris", [{}])[0].get("uri", "")
            img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""

            if full_name and price:
                key = (full_name, STORE_NAME)
                if key in existing:
                    old = existing[key]
                    all_updates.append((old['row'], [cat['name'], STORE_NAME, price, was_price, "TRUE", img_url, ""]))
                else:
                    all_new_rows.append(["", full_name, cat['name'], STORE_NAME, price, was_price or "", "TRUE", img_url])
        
        time.sleep(random.uniform(2, 5))

    # Diagnostic tool will verify if this found data
    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()