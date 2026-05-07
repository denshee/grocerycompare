import time
from curl_cffi import requests
from tenacity import retry, wait_exponential, stop_after_attempt
import urllib.parse
from datetime import datetime
import sheets_helper

PAGES_PER_TERM = 1
PAGE_SIZE = 20

SEARCH_TERMS = [
    "apples", "bananas", "strawberries", "blueberries", "grapes", "watermelon", "avocado",
    "potatoes", "onions", "carrots", "broccoli", "lettuce", "tomatoes", "cucumber", "mushrooms",
    "chicken breast", "chicken thighs", "beef mince", "steak", "lamb chops", "pork mince", "bacon", "ham", "eggs",
    "milk", "full cream milk", "almond milk", "oat milk", "butter", "margarine", "greek yoghurt", 
    "cheddar cheese", "mozzarella", "feta", "cream cheese", "sour cream", "dips",
    "white bread", "wholemeal bread", "sourdough", "muffins", "crumpets", "tortillas", "rolls",
    "white rice", "basmati rice", "pasta", "spaghetti", "pasta sauce", "olive oil", "vegetable oil",
    "flour", "sugar", "honey", "peanut butter", "jam", "vegemite", "tinned tuna", "tinned tomatoes",
    "baked beans", "corn flakes", "weet-bix", "oats", "muesli", "salt", "pepper", "mayonnaise",
    "laundry detergent", "fabric softener", "dishwashing liquid", "dishwasher tablets", 
    "toilet paper", "paper towels", "garbage bags", "multipurpose spray", "window cleaner", 
    "shampoo", "conditioner", "body wash", "hand soap", "toothpaste", "sunscreen",
    "frozen chips", "ice cream", "frozen pizza", "frozen peas", "frozen berries", "frozen meals",
    "coffee beans", "instant coffee", "tea bags", "orange juice", "apple juice", "coca-cola", 
    "sparkling water", "potato chips", "corn chips", "crackers", "chocolate", "biscuits",
    "nappies", "baby wipes", "baby formula", "baby food", "cat food", "dog food", "cat litter"
]

HEADERS = {
    "ocp-apim-subscription-key": "eae83861d1cd4de6bb9cd8a2cd6f041e",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.coles.com.au"
}

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
def fetch_coles_products(search_terms):
    all_products = []
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        url = f"https://www.coles.com.au/api/bff/products/search?start=0&sortBy=salesDescending&searchTerm={encoded_term}"
        print(f"  Fetching Coles '{term}'...")
        try:
            r = requests.get(url, headers=HEADERS, impersonate="chrome110", timeout=15)
            r.raise_for_status()
            data = r.json()
            products = data.get("results", [])
            all_products.extend(products)
            time.sleep(1)
        except Exception as e:
            print(f"  Error fetching '{term}': {e}")
    return all_products

def build_upsert_data(products, store_name, existing):
    new_rows, price_updates, history_rows = [], [], []
    seen_names = set()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for product in products:
        if product.get("_type") != "PRODUCT": continue
        name = f"{product.get('brand', '')} {product.get('name', '')}".strip()
        if not name or name in seen_names: continue
        seen_names.add(name)

        pricing = product.get("pricing", {})
        price = pricing.get("now")
        was_price = pricing.get("was")
        
        img_id = product.get("imageUris", [{}])[0].get("uri", "")
        image_url = f"https://cdn.productimages.coles.com.au/productimages{img_id}" if img_id else ""

        key = (name, store_name)
        if key in existing:
            old = existing[key]
            price_changed = (price is not None and price != old['price'])
            if price_changed or not old.get('image') or old.get('category') == "Uncategorized":
                row_slice = [old.get('category'), store_name, price, was_price, "TRUE", image_url or old.get('image'), old.get('canonical_id')]
                price_updates.append((old['row'], row_slice))
                if price_changed:
                    history_rows.append([now_str, name, store_name, price, was_price or ""])
        else:
            new_rows.append(["", name, "Uncategorized", store_name, price or "", was_price or "", "TRUE", image_url])
    return new_rows, price_updates, history_rows

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    products = fetch_coles_products(SEARCH_TERMS)
    new_rows, price_updates, history_rows = build_upsert_data(products, "Coles", existing)
    sheets_helper.batch_upsert(worksheet, "Coles", new_rows, price_updates, history_rows)

if __name__ == "__main__":
    main()