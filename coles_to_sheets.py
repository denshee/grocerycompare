import time
import random
from datetime import datetime
from curl_cffi import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import sheets_helper

STORE_NAME = "Coles"

# Comprehensive Master List for Best Sellers
SEARCH_TERMS = [
    "milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken breast", 
    "beef mince", "apples", "bananas", "potatoes", "onions", "carrots"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.coles.com.au",
}

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
def fetch_coles_search(term):
    # Updated to the 2026 stable search endpoint
    url = f"https://www.coles.com.au/api/bff/products/search?searchTerm={term}"
    r = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=30)
    r.raise_for_status()
    
    data = r.json()
    # Resilient extraction: check multiple possible keys
    return data.get("results") or data.get("products") or data.get("data", {}).get("products", [])

def main():
    print(f"\n[Phase 1] Connecting to Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    
    all_new_rows = []
    all_updates = []
    seen_names = set()

    print(f"\n[Phase 2] Scraping Coles Best Sellers...")
    for term in SEARCH_TERMS:
        try:
            print(f"  Fetching: {term}")
            products = fetch_coles_search(term)
            
            if not products:
                print(f"    ⚠️ No products found for '{term}'")
                continue

            for p in products:
                # Support both flat and nested JSON structures
                brand = p.get('brand') or p.get('brandName', '')
                p_name = p.get('name') or p.get('displayName', '')
                full_name = f"{brand} {p_name}".strip()
                
                if not full_name or full_name in seen_names: continue
                seen_names.add(full_name)

                # Resilient pricing extraction
                pricing = p.get("pricing", {})
                price = pricing.get("now") or p.get("price", {}).get("current")
                
                # Resilient image extraction
                images = p.get("imageUris", [])
                img_id = images[0].get("uri") if images else p.get("thumbnail")
                img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""

                if full_name and price:
                    key = (full_name, STORE_NAME)
                    if key in existing:
                        old = existing[key]
                        all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img_url, ""]))
                    else:
                        all_new_rows.append(["", full_name, "Pantry", STORE_NAME, price, "", "TRUE", img_url])
            
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            print(f"    ❌ Error on '{term}': {e}")

    # Send to helper for final write
    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()