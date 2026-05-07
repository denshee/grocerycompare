import time
from curl_cffi import requests
from tenacity import retry, wait_exponential, stop_after_attempt
import urllib.parse
from datetime import datetime
import sheets_helper

PAGES_PER_TERM = 1
PAGE_SIZE = 36

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

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
def fetch_woolworths_products(search_terms):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0 Safari/537.36"}
    all_products = []
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        url = f"https://www.woolworths.com.au/apis/ui/Search/products?searchTerm={encoded_term}&pageNumber=1&pageSize=36"
        print(f"  Fetching Woolies '{term}'...")
        try:
            r = requests.get(url, headers=headers, impersonate="chrome110", timeout=15)
            r.raise_for_status()
            bundles = r.json().get("Products", [])
            for b in bundles:
                all_products.extend(b.get("Products", []))
            time.sleep(1)
        except Exception as e:
            print(f"  Error fetching '{term}': {e}")
    return all_products

def build_upsert_data(products, store_name, existing):
    new_rows, price_updates, history_rows = [], [], []
    seen_names = set()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for p in products:
        if not p.get("IsAvailable"): continue
        name = p.get("DisplayName", "").strip()
        if not name or name in seen_names: continue
        seen_names.add(name)

        price, was_price = p.get("Price"), p.get("WasPrice")
        img_url = p.get("MediumImageFile", "")

        key = (name, store_name)
        if key in existing:
            old = existing[key]
            price_changed = (price is not None and price != old['price'])
            if price_changed or not old.get('image') or old.get('category') == "Uncategorized":
                row_slice = [old.get('category'), store_name, price, was_price, "TRUE", img_url or old.get('image'), old.get('canonical_id')]
                price_updates.append((old['row'], row_slice))
                if price_changed:
                    history_rows.append([now_str, name, store_name, price, was_price or ""])
        else:
            new_rows.append(["", name, "Uncategorized", store_name, price or "", was_price or "", "TRUE", img_url])
    return new_rows, price_updates, history_rows

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    products = fetch_woolworths_products(SEARCH_TERMS)
    new_rows, price_updates, history_rows = build_upsert_data(products, "Woolworths", existing)
    sheets_helper.batch_upsert(worksheet, "Woolworths", new_rows, price_updates, history_rows)

if __name__ == "__main__":
    main()