import time
import random
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sheets_helper

STORE_NAME = "Coles"
# We focus on a small set of high-value searches to keep the run safe and fast
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken", "beef", "apples", "bananas"]

def clean_price(text):
    if not text: return 0.0
    match = re.search(r'(\d+\.?\d*)', text.replace('$', ''))
    return float(match.group(1)) if match else 0.0

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    all_new_rows, all_updates = [], []

    with sync_playwright() as p:
        # Launching with a slow-mo factor to be 'safer'
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        Stealth().use_sync(page)

        for term in SEARCH_TERMS:
            print(f"  [HUMAN MODE] Searching Coles for: {term}")
            try:
                # Use the public search URL
                url = f"https://www.coles.com.au/search?q={term}"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Slower: Wait 5-8 seconds just to mimic a user looking at the screen
                time.sleep(random.uniform(5, 8))
                
                # Wait for product tiles to appear
                page.wait_for_selector("[data-testid='product-tile']", timeout=30000)
                
                tiles = page.locator("[data-testid='product-tile']").all()
                for tile in tiles:
                    try:
                        name = tile.locator("h3.product__title").first.inner_text().strip()
                        price_text = tile.locator(".price__value").first.inner_text().strip()
                        price = clean_price(price_text)
                        
                        # Images are often lazy-loaded; we grab what's there
                        img_url = tile.locator("img").first.get_attribute("src") or ""

                        if name and price:
                            key = (name, STORE_NAME)
                            if key in existing:
                                old = existing[key]
                                all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img_url, ""]))
                            else:
                                all_new_rows.append(["", name, "Pantry", STORE_NAME, price, "", "TRUE", img_url])
                    except: continue
                
                # Safety: Large jitter between searches
                print(f"    Found {len(tiles)} items. Cooling down...")
                time.sleep(random.uniform(10, 15))
                
            except Exception as e:
                print(f"    ⚠️ Failed to scrape '{term}'. This usually means a bot-check appeared.")
                continue

        browser.close()

    # Write whatever we found to the sheet
    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()