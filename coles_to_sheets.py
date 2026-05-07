import time
import random
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sheets_helper

STORE_NAME = "Coles"
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken breast", "beef mince", "apples", "bananas"]

def clean_price(text):
    if not text: return 0.0
    # Extracts numbers from strings like '$4.50' or '2 for $9'
    match = re.search(r'(\d+\.?\d*)', text.replace('$', ''))
    return float(match.group(1)) if match else 0.0

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    
    all_new_rows = []
    all_updates = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a high-quality User Agent to avoid detection
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        Stealth().use_sync(page)

        for term in SEARCH_TERMS:
            print(f"  Searching Coles for: {term}")
            try:
                # Go directly to the search results page
                url = f"https://www.coles.com.au/search?q={term}"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for product tiles to appear
                page.wait_for_selector("[data-testid='product-tile']", timeout=30000)
                
                # Scrape the visible product tiles
                tiles = page.locator("[data-testid='product-tile']").all()
                
                for tile in tiles:
                    try:
                        # Find name and price within the tile
                        name_el = tile.locator("h3.product__title").first
                        price_el = tile.locator(".price__value").first
                        
                        name = name_el.inner_text().strip()
                        price = clean_price(price_el.inner_text().strip())
                        
                        # Grab image
                        img_el = tile.locator("img").first
                        img_url = img_el.get_attribute("src") or ""

                        if name and price:
                            key = (name, STORE_NAME)
                            if key in existing:
                                old = existing[key]
                                all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img_url, ""]))
                            else:
                                all_new_rows.append(["", name, "Pantry", STORE_NAME, price, "", "TRUE", img_url])
                    except:
                        continue
                
                time.sleep(random.uniform(2, 4)) # Random pause between searches
                
            except Exception as e:
                print(f"    ⚠️ Could not find results for '{term}': {e}")
                continue

        browser.close()

    # Final write to sheet
    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()