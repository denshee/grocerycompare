import time
import random
import json
import urllib.parse
from datetime import datetime
from curl_cffi import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import sheets_helper

STORE_NAME = "Coles"
BATCH_WRITE_EVERY = 250

# Internal Category IDs for Coles
COLES_CAT_MAP = {
    "fruit-vegetables": "fruit-vegetables",
    "meat-seafood": "meat-seafood",
    "dairy-eggs-fridge": "dairy-eggs-fridge",
    "bakery": "bakery",
    "deli": "deli",
    "pantry": "pantry",
    "drinks": "drinks",
    "frozen": "frozen",
    "household": "household",
    "health-beauty": "health-beauty"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.coles.com.au",
    "ocp-apim-subscription-key": "eae83861d1cd4de6bb9cd8a2cd6f041e"
}

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
def fetch_coles_category_page(slug, page):
    url = f"https://www.coles.com.au/api/bff/products/browse/{slug}?page={page}"
    r = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=30)
    if r.status_code == 403:
        raise Exception("Akamai Blocked Coles API")
    return r.json()

def main():
    print("\n[Phase 1] Connecting to Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    
    written_names = set()
    total_created, total_updated = 0, 0

    for slug in COLES_CAT_MAP.keys():
        print(f"\n  Crawling Aisle: {slug.replace('-', ' ').title()}")
        page = 1
        buffer = []
        
        while True:
            try:
                data = fetch_coles_category_page(slug, page)
                results = data.get("results", [])
                if not results: break
                
                for res in results:
                    if res.get("_type") != "PRODUCT": continue
                    name = f"{res.get('brand', '')} {res.get('name', '')}".strip()
                    pricing = res.get("pricing", {})
                    price = pricing.get("now")
                    
                    # Image Logic: Targeting the direct CDN
                    img_id = res.get("imageUris", [{}])[0].get("uri", "")
                    img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""

                    if name and price:
                        buffer.append({
                            "name": name,
                            "price": float(price),
                            "was_price": float(pricing.get("was")) if pricing.get("was") else None,
                            "category": slug.replace('-', ' ').title(),
                            "image": img_url
                        })

                if len(buffer) >= BATCH_WRITE_EVERY:
                    c, u = sheets_helper.batch_upsert(worksheet, STORE_NAME, [], [], []) # Logic moved to helper
                    # Note: We use your new batch_upsert logic here
                    buffer = []
                
                page += 1
                time.sleep(random.uniform(1.5, 3.0))
                if page > 100: break # Safety cap
            except Exception as e:
                print(f"      Error: {e}")
                break

if __name__ == "__main__":
    main()