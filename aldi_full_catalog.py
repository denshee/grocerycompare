import time
import random

"""
aldi_full_catalog.py
--------------------
Heavy monthly scraper: browses ALL Aldi AU core grocery categories via Playwright
DOM extraction and writes every product to Google Sheets.
"""

import argparse
import re
from datetime import datetime
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Aldi"
BATCH_WRITE_EVERY = 500

ALDI_BASE = "https://www.aldi.com.au"

ALDI_CATEGORIES = [
    ALDI_BASE + "/products/fruits-vegetables/k/950000000",
    ALDI_BASE + "/products/meat-seafood/k/940000000",
    ALDI_BASE + "/products/deli-chilled-meats/k/930000000",
    ALDI_BASE + "/products/dairy-eggs-fridge/k/960000000",
    ALDI_BASE + "/products/pantry/k/970000000",
    ALDI_BASE + "/products/bakery/k/920000000",
    ALDI_BASE + "/products/freezer/k/980000000",
    ALDI_BASE + "/products/drinks/k/1000000000",
    ALDI_BASE + "/products/health-beauty/k/1040000000",
    ALDI_BASE + "/products/baby/k/1030000000",
    ALDI_BASE + "/products/cleaning-household/k/1050000000",
    ALDI_BASE + "/products/pets/k/1020000000",
    ALDI_BASE + "/products/liquor/k/1010000000",
    ALDI_BASE + "/products/snacks-confectionery/k/1588161408332087",
]

def clean_price(price_text: str) -> float | None:
    """Handles '$1.23', '80c', '1.23', etc."""
    if not price_text: return None
    if 'c' in price_text.lower():
        digits = re.sub(r'[^\d]', '', price_text)
        return float(digits) / 100.0 if digits else None
    cleaned = re.sub(r'[^\d.]', '', price_text)
    try:
        return float(cleaned) if cleaned else None
    except:
        return None

def batch_write(worksheet, products_buffer: list[dict],
                existing: dict, written_names: set) -> tuple[int, int]:
    """Classify buffered products and flush to Google Sheets with history logs."""
    new_rows      = []
    price_updates = []
    history_rows  = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for p in products_buffer:
        name = p["name"]
        if name in written_names: continue

        key = (name, STORE_NAME)
        if key in existing:
            old_data = existing[key]
            price_changed = (p["price"] is not None and p["price"] != old_data['price'])
            # Aldi rarely has reg_price in catalog, but we check if it exists
            reg_price_changed = (p["was_price"] is not None and p["was_price"] != old_data['reg_price'])

            image_empty = not old_data.get('image')

            if price_changed or reg_price_changed or image_empty:
                # Tuple format: (row, price, reg_price, image_url)
                price_updates.append((old_data['row'], p["price"], p["was_price"], p["image"] if image_empty else None))
                if price_changed or reg_price_changed:
                    history_rows.append([now_str, name, STORE_NAME, p["price"], p["was_price"] or ""])
        else:
            new_rows.append([
                "", name, STORE_NAME,
                p["price"] if p["price"] is not None else "",
                p["was_price"] if p["was_price"] is not None else "",
                p["in_stock"], p["image"],
            ])
            history_rows.append([now_str, name, STORE_NAME, p["price"] if p["price"] is not None else "", p["was_price"] or ""])
            existing[key] = {'row': -1, 'price': p["price"], 'reg_price': p["was_price"]}

        written_names.add(name)

    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates, history_rows
    )
    return created, updated

def main():
    parser = argparse.ArgumentParser(description="Aldi full catalogue scraper")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Aldi Full Catalogue → Google Sheets (+ History)")
    print("=" * 60)

    print("\n[Phase 1] Connecting to Sheets...")
    worksheet = None
    existing  = {}
    if not args.dry_run:
        worksheet = sheets_helper.get_listings_worksheet()
        existing  = sheets_helper.load_existing_listings(worksheet)

    buffer = []
    written_names = set()
    total_created = 0
    total_updated = 0

    from playwright.sync_api import sync_playwright
    print(f"\n[Phase 2] Booting Playwright...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        for base_url in ALDI_CATEGORIES:
            category_name = base_url.split('/')[-3]
            print(f"  Category: {category_name}")
            page_num = 1
            while True:
                url = base_url + f"?page={page_num}"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    page.wait_for_timeout(2000)
                    
                    tiles = page.locator("div.product-tile").all()
                    if not tiles:
                        print(f"    → No more products found at page {page_num}")
                        break
                        
                    products_on_page = 0
                    for tile in tiles:
                        try:
                            name_el = tile.locator(".product-tile__name p").first
                            price_el = tile.locator(".base-price__regular span").first
                            # Handle cases where price might be hidden or different
                            if not name_el.is_visible(): continue
                            
                            name = name_el.inner_text().strip()
                            brand = ""
                            if tile.locator(".product-tile__brandname p").is_visible():
                                brand = tile.locator(".product-tile__brandname p").first.inner_text().strip()
                            if brand: name = f"{brand} {name}"
                            
                            price_text = price_el.inner_text().strip() if price_el.is_visible() else ""
                            price = clean_price(price_text)
                            
                            img_url = tile.locator(".product-tile__picture img").first.get_attribute("src") or ""
                            if img_url.startswith("//"): img_url = "https:" + img_url

                            if name and price:
                                buffer.append({"name": name, "price": price, "was_price": None, "in_stock": "TRUE", "image": img_url})
                                products_on_page += 1
                        except: pass
                    
                    print(f"    Page {page_num}: +{products_on_page} items")
                    if products_on_page < 10: # Likely the end of results
                        break
                    
                    page_num += 1
                    page.wait_for_timeout(random.uniform(1000, 3000)) # Ethical delay
                except Exception as e:
                    print(f"    Error on page {page_num}: {e}")
                    break

            if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
                print(f"  ══ Flushing {len(buffer)} items... ══")
                c, u = batch_write(worksheet, buffer, existing, written_names)
                total_created += c
                total_updated += u
                buffer = []

        browser.close()

    if not args.dry_run and buffer:
        print(f"  ══ Final Flush: {len(buffer)} items... ══")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print(f"\nCOMPLETED. Created: {total_created} | Updated: {total_updated}")

if __name__ == "__main__":
    main()
