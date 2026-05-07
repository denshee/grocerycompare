import time
from curl_cffi import requests
from datetime import datetime
import sheets_helper

# Comprehensive Master List
SEARCH_TERMS = ["apples", "bananas", "strawberries", "blueberries", "grapes", "watermelon", "avocado", "potatoes", "onions", "carrots", "broccoli", "lettuce", "tomatoes", "cucumber", "mushrooms", "chicken breast", "chicken thighs", "beef mince", "steak", "lamb chops", "pork mince", "bacon", "ham", "eggs", "milk", "butter", "cheese", "yoghurt", "bread", "rice", "pasta", "cereal", "chips", "chocolate", "toilet paper", "laundry detergent"]

def fetch_coles_products(term):
    # This is the stable public search endpoint used by the web storefront
    url = f"https://www.coles.com.au/api/bff/products/search?searchTerm={term}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.coles.com.au/",
    }
    
    # We use impersonate="chrome" to handle the TLS fingerprinting Coles uses
    r = requests.get(url, headers=headers, impersonate="chrome", timeout=30)
    if r.status_code != 200:
        return []
    
    data = r.json()
    return data.get("results", [])

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    all_new_rows = []
    all_updates = []

    for term in SEARCH_TERMS:
        print(f"  Scraping Coles: {term}")
        products = fetch_coles_products(term)
        
        for p in products:
            if p.get("_type") != "PRODUCT": continue
            name = f"{p.get('brand', '')} {p.get('name', '')}".strip()
            price = p.get("pricing", {}).get("now")
            was_price = p.get("pricing", {}).get("was")
            img_id = p.get("imageUris", [{}])[0].get("uri", "")
            img_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""
            
            key = (name, "Coles")
            if key in existing:
                old = existing[key]
                # Update logic (Aligning to Columns C:I)
                all_updates.append((old['row'], [old['category'], "Coles", price, was_price, "TRUE", img_url or old['image'], ""]))
            else:
                # New row logic
                all_new_rows.append(["", name, "Uncategorized", "Coles", price, was_price, "TRUE", img_url])
        
        time.sleep(2) # Prevent rate limiting

    sheets_helper.batch_upsert(worksheet, "Coles", all_new_rows, all_updates)

if __name__ == "__main__":
    main()