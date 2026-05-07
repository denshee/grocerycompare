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
    
    with sync_playwright() as p:
        # Launching with specific flags to improve performance in Docker/GitHub environments
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox"
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        Stealth().use_sync(page)

        for url in ALDI_CATEGORIES:
            cat_name = url.split('/')[-2].replace('-', ' ').title()
            print(f"  Scraping Aldi {cat_name}...")
            
            success = False
            for attempt in range(3): # 3 Hard retries per category
                try:
                    # Increased timeout to 120s (2 minutes)
                    page.goto(url, wait_until="commit", timeout=120000)
                    # Instead of waiting for network, we wait for the actual container to exist
                    page.wait_for_selector("div.product-tile", timeout=60000)
                    
                    # Human-like scroll to trigger lazy loading of prices/images
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                    time.sleep(2)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(3)
                    
                    tiles = page.locator("div.product-tile").all()
                    buffer = []
                    for tile in tiles:
                        try:
                            name = tile.locator(".product-tile__name").first.inner_text().strip()
                            price_el = tile.locator(".base-price__regular").first
                            price = clean_price(price_el.inner_text().strip())
                            
                            img_url = ""
                            img_el = tile.locator("img").first
                            if img_el.count() > 0:
                                img_url = img_el.get_attribute("src")
                                if img_url and img_url.startswith("//"): img_url = "https:" + img_url

                            if name and price:
                                buffer.append({"name": name, "category": cat_name, "price": price, "image": img_url})
                        except: continue
                    
                    if buffer:
                        new_rows, updates = [], []
                        for item in buffer:
                            key = (item["name"], STORE_NAME)
                            if key in existing:
                                old = existing[key]
                                updates.append((old['row'], [item["category"], STORE_NAME, item["price"], None, "TRUE", item["image"], ""]))
                            else:
                                new_rows.append(["", item["name"], item["category"], STORE_NAME, item["price"], "", "TRUE", item["image"]])
                        
                        sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, updates)
                        print(f"    SUCCESS: Uploaded {len(buffer)} items for {cat_name}")
                        success = True
                        break # Break retry loop on success
                
                except Exception as e:
                    print(f"    Attempt {attempt + 1} failed for {cat_name}. Retrying... ({e})")
                    time.sleep(10) # Wait before retry

            if not success:
                # If all 3 attempts fail, we raise an error to stop the build. 
                # This ensures we don't 'pass' a failing job.
                raise Exception(f"CRITICAL FAILURE: Could not scrape Aldi {cat_name} after 3 attempts.")

        browser.close()

if __name__ == "__main__":
    main()