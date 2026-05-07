import time
import random
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sheets_helper

STORE_NAME = "Coles"
# We focus on the core "Best Sellers" to establish a stable bridge first
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
        # Launch with 'Slow-Mo' to mimic human reading speed
        browser = p.chromium.launch(headless=True, slow_mo=500)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        Stealth().use_sync(page)

        for term in SEARCH_TERMS:
            print(f"  [PRINCIPLE: PERFECTION] Searching: {term}")
            try:
                page.goto(f"https://www.coles.com.au/search?q={term}", wait_until="networkidle", timeout=90000)
                
                # Wait for the actual product container, not just the page
                page.wait_for_selector("section[data-testid='product-grid']", timeout=45000)
                
                # Human-like scroll to trigger lazy loading
                page.mouse.wheel(0, 500)
                time.sleep(2)
                
                tiles = page.locator("div[data-testid='product-tile']").all()
                for tile in tiles:
                    try:
                        # Using stable data-testids instead of volatile CSS classes
                        name = tile.locator("[data-testid='product-title']").inner_text().strip()
                        price_text = tile.locator("[data-testid='total-price']").inner_text().strip()
                        price = clean_price(price_text)
                        
                        img = tile.locator("img").first.get_attribute("src") or ""

                        if name and price:
                            key = (name, STORE_NAME)
                            if key in existing:
                                old = existing[key]
                                all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img, ""]))
                            else:
                                all_new_rows.append(["", name, "Pantry", STORE_NAME, price, "", "TRUE", img])
                    except: continue
                
                print(f"    Successfully extracted {len(tiles)} items for {term}")
                time.sleep(random.uniform(8, 12)) # The 'Safe' delay
                
            except Exception as e:
                print(f"    ⚠️ Failed to extract {term}. Page structure may have shifted.")
                continue

        browser.close()

    # Final write with our diagnostic guardrails
    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)

if __name__ == "__main__":
    main()