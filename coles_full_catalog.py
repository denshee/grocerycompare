import time
import random
from datetime import datetime
from curl_cffi import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import sheets_helper

STORE_NAME = "Coles"

COLES_CAT_MAP = {
    "fruit-vegetables": "Fruit & Veg",
    "meat-seafood": "Meat & Seafood",
    "dairy-eggs-fridge": "Dairy, Eggs & Fridge",
    "bakery": "Bakery",
    "pantry": "Pantry",
    "drinks": "Drinks",
    "frozen": "Frozen",
    "household": "Household"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.coles.com.au",
}

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
def fetch_coles_page(slug, page):
    url = f"https://www.coles.com.au/api/bff/products/browse/{slug}?page={page}"
    r = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=30)
    r.raise_for_status()
    return r.json()

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for slug, cat_name in COLES_CAT_MAP.items():
        print(f"  Crawling Coles: {cat_name}")
        page = 1
        while page <= 10: # Safety cap for Best Sellers
            data = fetch_coles_page(slug, page)
            results = data.get("results", [])
            if not results: break
            
            new_rows, updates = [], []
            for res in results:
                if res.get("_type") != "PRODUCT": continue
                name = f"{res.get('brand', '')} {res.get('name', '')}".strip()
                price = res.get("pricing", {}).get("now")
                img_id = res.get("imageUris", [{}])[0].get("uri", "")
                img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}"

                key = (name, STORE_NAME)
                if key in existing:
                    old = existing[key]
                    updates.append((old['row'], [cat_name, STORE_NAME, price, None, "TRUE", img_url, ""]))
                else:
                    new_rows.append(["", name, cat_name, STORE_NAME, price, "", "TRUE", img_url])
            
            if new_rows or updates:
                sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, updates)
            
            page += 1
            time.sleep(2)

if __name__ == "__main__":
    main()