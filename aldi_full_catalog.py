import time
from datetime import datetime
import sheets_helper
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

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

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)

    with sync_playwright() as p:
        # We launch with a specific viewport to force the desktop site
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        Stealth().use_sync(page)

        for url in ALDI_CATEGORIES:
            cat_name = url.split('/')[-2].replace('-', ' ').title()
            print(f"  Attempting Aldi: {cat_name}")
            
            # CRITICAL CHANGE: We only wait for 'commit', then manually wait for the tile
            page.goto(url, wait_until="commit", timeout=60000)
            try:
                page.wait_for_selector("div.product-tile", timeout=30000)
                
                # Scroll to bottom to load all lazy-loaded prices
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(3)
                
                tiles = page.locator("div.product-tile").all()
                new_rows, updates = [], []
                
                for tile in tiles:
                    name = tile.locator(".product-tile__name").first.inner_text().strip()
                    price_text = tile.locator(".base-price__regular").first.inner_text().strip()
                    # Clean price (e.g., '$4.99' -> 4.99)
                    price = float(''.join(c for c in price_text if c.isdigit() or c == '.'))
                    
                    key = (name, "Aldi")
                    if key in existing:
                        old = existing[key]
                        updates.append((old['row'], [cat_name, "Aldi", price, None, "TRUE", "", ""]))
                    else:
                        new_rows.append(["", name, cat_name, "Aldi", price, "", "TRUE", ""])
                
                sheets_helper.batch_upsert(worksheet, "Aldi", new_rows, updates)
                print(f"    Successfully scraped {cat_name}")
                
            except Exception as e:
                print(f"    Failed to find products in {cat_name}. Website may have changed layout.")
        
        browser.close()

if __name__ == "__main__":
    main()