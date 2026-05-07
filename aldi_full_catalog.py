import time
import random
import re
from datetime import datetime
import sheets_helper
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

STORE_NAME = "Aldi"
ALDI_CATEGORIES = [
    "https://www.aldi.com.au/en/groceries/super-savers/",
    "https://www.aldi.com.au/en/groceries/fresh-produce/",
    "https://www.aldi.com.au/en/groceries/meat-seafood/",
    "https://www.aldi.com.au/en/groceries/bakery/",
    "https://www.aldi.com.au/en/groceries/dairy-eggs-fridge/",
    "https://www.aldi.com.au/en/groceries/pantry/",
    "https://www.aldi.com.au/en/groceries/freezer/",
    "https://www.aldi.com.au/en/groceries/drinks/",
    "https://www.aldi.com.au/en/groceries/laundry-household/",
    "https://www.aldi.com.au/en/groceries/beauty-personal-care/"
]

def clean_price(text):
    if not text: return None
    if 'c' in text.lower():
        digits = re.sub(r'[^\d]', '', text)
        return float(digits) / 100.0 if digits else None
    cleaned = re.sub(r'[^\d.]', '', text)
    try: return float(cleaned) if cleaned else None
    except: return None

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    buffer = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        Stealth().use_sync(page)

        for url in ALDI_CATEGORIES:
            cat_name = url.split('/')[-2].replace('-', ' ').title()
            print(f"  Scraping Aldi {cat_name}...")
            
            try:
                # Increased timeout to 90s and using 'domcontentloaded' for speed/reliability
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                time.sleep(random.uniform(3, 6)) # Human-like pause
                
                tiles = page.locator("div.product-tile").all()
                products_found = 0
                for tile in tiles:
                    try:
                        name_el = tile.locator(".product-tile__name").first
                        price_el = tile.locator(".base-price__regular").first
                        
                        if not name_el.is_visible(): continue
                        
                        name = name_el.inner_text().strip()
                        price = clean_price(price_el.inner_text().strip())
                        
                        img_url = ""
                        img_el = tile.locator("img").first
                        if img_el.count() > 0:
                            img_url = img_el.get_attribute("src")
                            if img_url and img_url.startswith("//"): img_url = "https:" + img_url

                        if name and price:
                            buffer.append({
                                "name": name, 
                                "category": cat_name, 
                                "price": price, 
                                "was_price": None, 
                                "in_stock": "TRUE", 
                                "image": img_url
                            })
                            products_found += 1
                    except: continue
                
                print(f"    Found {products_found} items in {cat_name}")

                if buffer:
                    # Leverage your built-in upsert logic
                    new_rows, updates, history = [], [], []
                    for item in buffer:
                        key = (item["name"], STORE_NAME)
                        if key in existing:
                            old = existing[key]
                            if item["price"] != old['price'] or old.get('category') == "Uncategorized":
                                # row_slice: [Category, Store, Price, WasPrice, InStock, Image, CanonicalID]
                                updates.append((old['row'], [item["category"], STORE_NAME, item["price"], None, "TRUE", item["image"], ""]))
                        else:
                            new_rows.append(["", item["name"], item["category"], STORE_NAME, item["price"], "", "TRUE", item["image"]])
                    
                    sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, updates, history)
                    buffer = [] # Clear buffer after each category
                    
            except Exception as e:
                print(f"  [Skip] Error loading {cat_name}: {e}")
                continue

        browser.close()

if __name__ == "__main__":
    main()