"""
coles_full_catalog.py
---------------------
Heavy monthly scraper: browses ALL Coles categories strictly through Playwright
DOM inspection to perfectly bypass Datadome and extract the full catalogue.
"""

import argparse
from datetime import datetime
import re
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Coles"
BATCH_WRITE_EVERY = 500

COLES_CATEGORIES = [
    "meat-seafood", "fruit-vegetables", "dairy-eggs-fridge", "bakery",
    "deli", "pantry", "drinks", "frozen", "household", "health-beauty",
    "baby", "pet", "liquor"
]

def batch_write(worksheet, products_buffer: list[dict],
                existing: dict, written_names: set) -> tuple[int, int]:
    """Classify buffered products and flush to Google Sheets with history logs."""
    new_rows      = []
    price_updates = []
    history_rows  = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for p in products_buffer:
        name = p["name"]
        if name in written_names:
            continue

        key = (name, STORE_NAME)
        if key in existing:
            old_data = existing[key]
            price_changed = (p["price"] is not None and p["price"] != old_data['price'])
            reg_price_changed = (p["was_price"] is not None and p["was_price"] != old_data['reg_price'])

            if price_changed or reg_price_changed:
                price_updates.append((old_data['row'], p["price"], p["was_price"]))
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

def extract_price(text: str) -> float | None:
    """Takes pricing strings like '$3.50' or '80c' and normalises to float."""
    if not text: return None
    if text.endswith('c'):
        val = re.sub(r'[^\d]', '', text)
        return float(val) / 100.0 if val else None
    val = re.sub(r'[^\d\.]', '', text)
    try:
        return float(val) if val else None
    except:
        return None

def main():
    parser = argparse.ArgumentParser(description="Coles full catalogue scraper")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Coles Full Catalogue → Google Sheets (+ History)")
    print("=" * 60)
    
    print("\n[Phase 1] Connecting to Google Sheets...")
    worksheet = None
    existing  = {}
    if not args.dry_run:
        worksheet = sheets_helper.get_listings_worksheet()
        existing  = sheets_helper.load_existing_listings(worksheet)

    buffer = []
    written_names = set()
    total_created = 0
    total_updated = 0
    total_scraped = 0

    from playwright.sync_api import sync_playwright
    print(f"\n[Phase 2] Booting Playwright...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        page.goto("https://www.coles.com.au/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        for slug in COLES_CATEGORIES:
            print(f"\n  Category: {slug}")
            page_num = 1
            while True:
                if args.max_pages and page_num > args.max_pages: break
                url = f"https://www.coles.com.au/browse/{slug}?page={page_num}"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_selector("[data-testid='product-tile']", timeout=15_000)
                except:
                    break

                page.wait_for_timeout(1000)
                tiles = page.locator("[data-testid='product-tile']").all()
                if not tiles: break

                products_on_page = 0
                for tile in tiles:
                    try:
                        name_el = tile.locator(".product__title")
                        price_el = tile.locator(".price__value")
                        if not name_el.is_visible() or not price_el.is_visible(): continue
                            
                        name = name_el.first.inner_text().strip()
                        price = extract_price(price_el.first.inner_text().strip())
                        
                        was_price = None
                        if tile.locator(".price__was").is_visible():
                            was_price = extract_price(tile.locator(".price__was").first.inner_text().strip())

                        img_url = ""
                        if tile.locator("img[data-testid='product-image']").is_visible():
                            img_url = tile.locator("img[data-testid='product-image']").get_attribute("src") or ""

                        if name and price:
                            buffer.append({"name": name, "price": price, "was_price": was_price, "in_stock": True, "image": img_url})
                            products_on_page += 1
                    except: pass
                
                total_scraped += products_on_page
                print(f"    Page {page_num}: +{products_on_page} products")

                if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
                    print(f"  ══ Flushing {len(buffer)} items... ══")
                    c, u = batch_write(worksheet, buffer, existing, written_names)
                    total_created += c
                    total_updated += u
                    buffer = []

                if products_on_page < 48: break
                page_num += 1

        browser.close()

    if not args.dry_run and buffer:
        print(f"  ══ Final Flush: {len(buffer)} items... ══")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print(f"\nCOMPLETED. Created: {total_created} | Updated: {total_updated}")

if __name__ == "__main__":
    main()
