import time
import random
from datetime import datetime
from curl_cffi import requests
import sheets_helper

STORE_NAME = "Coles"
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken breast", "beef mince", "apples", "bananas"]

# Updated headers to match a real 2026 Chrome browser on Windows 11
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.coles.com.au/",
}

def fetch_coles_robust(term):
    # This endpoint is more stable than the 'bff/products/search' version
    url = f"https://www.coles.com.au/api/products/search?searchTerm={term}"
    
    # We use impersonate="chrome124" for the latest TLS fingerprinting bypass
    r = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=30)
    
    if r.status_code != 200:
        print(f"    ⚠️ Server returned status {r.status_code} for '{term}'")
        return []
        
    data = r.json()
    # Coles sometimes wraps results in 'results' or 'products'
    return data.get("results") or data.get("products") or []

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    
    all_new_rows = []
    all_updates = []
    seen_names = set()

    for term in SEARCH_TERMS:
        print(f"  Scraping Coles: {term}")
        products = fetch_coles_robust(term)
        
        for p in products:
            # Flexible name extraction
            brand = p.get('brand', '')
            name_part = p.get('name', p.get('displayName', ''))
            full_name = f"{brand} {name_part}".strip()
            
            if not full_name or full_name in seen_names: continue
            seen_names.add(full_name)

            # Flexible price extraction
            pricing = p.get("pricing", {})
            price = pricing.get("now") or p.get("price")
            
            # Flexible image extraction
            img_id = p.get("imageUris", [{}])[0].get("uri", "")
            img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""

            if full_name and price:
                key = (full_name, STORE_NAME)
                if key in existing:
                    old = existing[key]
                    # Format for C:I range [Category, Store, Price, WasPrice, InStock, Image, ID]
                    all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img_url, ""]))
                else:
                    all_new_rows.append(["", full_name, "Pantry", STORE_NAME, price, "", "TRUE", img_url])
        
        time.sleep(random.uniform(2, 4))

    # This will now trigger the diagnostic in sheets_helper
    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()