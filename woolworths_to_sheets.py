import os
import time
import random
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sheets_helper

STORE_NAME = "Woolworths"
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken", "beef", "apples", "bananas"]

def clean_price(text):
    if not text: return 0.0
    match = re.search(r'(\d+\.?\d*)', text.replace('$', ''))
    return float(match.group(1)) if match else 0.0

def human_delay(min_sec=2, max_sec=5):
    time.sleep(random.uniform(min_sec, max_sec))

def simulate_human_behavior(page):
    scroll_amount = random.randint(300, 800)
    page.mouse.wheel(0, scroll_amount)
    human_delay(1, 3)
    page.mouse.wheel(0, -random.randint(100, scroll_amount))
    
    for _ in range(3):
        x = random.randint(100, 1000)
        y = random.randint(100, 800)
        page.mouse.move(x, y, steps=10)
        time.sleep(random.uniform(0.1, 0.5))

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    all_new_rows, all_updates = [], []

    proxy_server = os.environ.get("PROXY_SERVER")
    proxy_username = os.environ.get("PROXY_USERNAME")
    proxy_password = os.environ.get("PROXY_PASSWORD")

    proxy_settings = None
    if proxy_server and proxy_username and proxy_password:
        proxy_settings = {
            "server": proxy_server,
            "username": proxy_username,
            "password": proxy_password
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            proxy=proxy_settings,
            slow_mo=random.randint(200, 500)
        ) 
        
        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-AU",
            timezone_id="Australia/Sydney"
        )
        page = context.new_page()
        Stealth().use_sync(page)

        print(f"  [WEEKLY PROXY MODE] Starting {STORE_NAME} Sync...")
        try:
            page.goto("https://www.woolworths.com.au/", timeout=90000)
            simulate_human_behavior(page)
        except Exception:
            pass

        for term in SEARCH_TERMS:
            print(f"  [WEEKLY] Searching: {term}")
            try:
                url = f"https://www.woolworths.com.au/shop/search/products?searchTerm={term}"
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                simulate_human_behavior(page)
                
                # Wait for Woolworths product grid
                page.wait_for_selector(".product-grid-v2--tile", timeout=60000)
                tiles = page.locator(".product-grid-v2--tile").all()
                
                for tile in tiles:
                    try:
                        name = tile.locator(".product-title-link").inner_text().strip()
                        price_text = tile.locator(".price-dollars").inner_text().strip()
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
                
                human_delay(5, 10)
            except Exception as e:
                print(f"    ⚠️ Timeout on {term}. Skipping.")
                continue

        browser.close()

    sheets_helper.batch_upsert(worksheet, STORE_NAME, all_new_rows, all_updates)
    print(f"  [WEEKLY PROXY MODE] {STORE_NAME} Sync complete.")

if __name__ == "__main__":
    main()