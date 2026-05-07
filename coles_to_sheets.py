import time
import random
import re
from playwright.sync_api import sync_playwright
import sheets_helper

STORE_NAME = "Coles"
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken breast", "beef mince", "apples", "bananas"]

def clean_price(text):
    if not text: return 0.0
    match = re.search(r'(\d+\.?\d*)', text.replace('$', ''))
    return float(match.group(1)) if match else 0.0

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    all_new_rows, all_updates = [], []

    with sync_playwright() as p:
        # Use a Remote Browser WebSocket if you have one (e.g., Browserless)
        # For now, we use a 'Hard-Launch' with specific args to bypass typical CI blocks
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage'
        ])
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for term in SEARCH_TERMS:
            print(f"  [REMOTE BROWSER] Searching Coles: {term}")
            try:
                # We use the mobile-friendly search URL which has lighter security
                url = f"https://www.coles.com.au/search?q={term}"
                page.goto(url, wait_until="load", timeout=90000)
                
                # Check for "Access Denied" or "Challenge"
                if "Access Denied" in page.content():
                    print(f"    ❌ Blocked by Coles Security on term: {term}")
                    continue

                page.wait_for_selector("[data-testid='product-tile']", timeout=45000)
                
                tiles = page.locator("[data-testid='product-tile']").all()
                for tile in tiles:
                    try:
                        name = tile.locator("h3.product__title").first.inner_text().strip()
                        price_text = tile.locator(".price__value").first.inner_text().strip()
                        price = clean_price(price_text)
                        img_url = tile.locator("img").first.get_attribute("src") or ""

                        if name and price:
                            key = (name, STORE_NAME)
                            if key in existing:
                                old = existing[key]
                                all_updates.append((old['row'], ["Pantry", STORE_NAME, price, None, "TRUE", img_url, ""]))
                            else:
                                all_new_rows.append(["", name, "Pantry", STORE_NAME, price, "", "TRUE", img_url])
                    except: continue
                
                time.sleep(random.uniform(5, 10)) # Long pauses to avoid IP flagging
            except Exception as e:
                print(f"    ⚠️ Failed {term}: {e}")
                continue
                
        browser.close()

    if all_new_rows or all_updates:
        sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)
    else:
        print("❌ NO DATA EXTRACTED. Security wall is still up.")

if __name__ == "__main__":
    main()