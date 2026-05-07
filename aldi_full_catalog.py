import time
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sheets_helper

STORE_NAME = "Aldi"
ALDI_CATEGORIES = ["https://www.aldi.com.au/en/groceries/super-savers/"] # Start with Super Savers

def clean_aldi_price(text):
    if not text: return 0.0
    # Handles '$4.99', '99c', and '$10.00'
    match = re.search(r'(\d+\.?\d*)', text.replace('c', '.0').replace('$', ''))
    return float(match.group(1)) if match else 0.0

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        Stealth().use_sync(page)

        for url in ALDI_CATEGORIES:
            print(f"  Attempting Aldi: Super Savers")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("div.product-tile", timeout=30000)
            
            tiles = page.locator("div.product-tile").all()
            new_rows, updates = [], []
            
            for tile in tiles:
                name = tile.locator(".product-tile__name").first.inner_text().strip()
                price_text = tile.locator(".base-price__regular").first.inner_text().strip()
                price = clean_aldi_price(price_text)
                
                key = (name, STORE_NAME)
                if key in existing:
                    old = existing[key]
                    updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", "", ""]))
                else:
                    new_rows.append(["", name, "Pantry", STORE_NAME, price, "", "TRUE", ""])
            
            sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, updates)
        browser.close()

if __name__ == "__main__":
    main()