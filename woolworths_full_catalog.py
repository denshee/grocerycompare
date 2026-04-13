"""
woolworths_full_catalog.py
--------------------------
Heavy monthly scraper: browses ALL Woolworths categories via Playwright DOM 
extraction for maximum resilience against API/cookie blocking.
"""

import argparse
import random
import sys
import time
from datetime import datetime
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Woolworths"
BATCH_WRITE_EVERY = 500

WW_BASE     = "https://www.woolworths.com.au"

WOOLWORTHS_CATEGORIES = [
    "fruit-veg", "meat-seafood", "dairy-eggs-fridge", "bakery", "deli",
    "pantry", "frozen-foods", "drinks", "health-beauty", "household",
    "baby", "pet", "international-foods", "entertaining",
]

def clean_price(price_text: str) -> float | None:
    import re
    if not price_text: return None
    cleaned = re.sub(r'[^\d.]', '', price_text)
    try:
        return float(cleaned) if cleaned else None
    except:
        return None

def batch_write(worksheet, products_buffer: list[dict], existing: dict, written_names: set) -> tuple[int, int]:
    """Classify and flush to Google Sheets with history logging."""
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
            reg_price_changed = (p["was_price"] is not None and p["was_price"] != old_data['reg_price'])
            
            image_empty = not old_data.get('image') or "/placeholder" in old_data.get('image', '').lower()
            
            if price_changed or reg_price_changed or image_empty:
                img_to_update = p["image"] if image_empty else None
                price_updates.append((old_data['row'], p["price"], p["was_price"], img_to_update))
                if price_changed or reg_price_changed:
                    history_rows.append([now_str, name, STORE_NAME, p["price"], p["was_price"] or ""])
        else:
            new_rows.append([
                "", name, STORE_NAME,
                p["price"] if p["price"] is not None else "",
                p["was_price"] if p["was_price"] is not None else "",
                "TRUE", p["image"],
            ])
            history_rows.append([now_str, name, STORE_NAME, p["price"] if p["price"] is not None else "", p["was_price"] or ""])
            existing[key] = {'row': -1, 'price': p["price"], 'reg_price': p["was_price"], 'image': p["image"]}

        written_names.add(name)

    created, updated = sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, price_updates, history_rows)
    return created, updated

def main():
    parser = argparse.ArgumentParser(description="Woolworths full catalogue scraper")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Woolworths Full Catalogue → Google Sheets (DOM Extraction)")
    print("=" * 60)

    print("\n[Phase 1] Connecting to Google Sheets...")
    worksheet = None
    existing  = {}
    if not args.dry_run:
        worksheet = sheets_helper.get_listings_worksheet()
        existing  = sheets_helper.load_existing_listings(worksheet)

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    
    print(f"\n[Phase 2] Booting Playwright...")
    
    total_created = 0
    total_updated = 0
    buffer = []
    written_names = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        for idx, slug in enumerate(WOOLWORTHS_CATEGORIES):
            # Session Rotation: New context every 2 categories
            if idx % 2 == 0:
                print(f"\n[Session Rotation] Creating new context...")
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 1024}
                )
                page = context.new_page()
                Stealth().use_sync(page)
                time.sleep(2)

            print(f"\n  Category: {slug}")
            page_num = 1
            while True:
                if args.max_pages and page_num > args.max_pages: break
                
                url = f"{WW_BASE}/shop/browse/{slug}?pageNumber={page_num}"
                try:
                    time.sleep(random.uniform(3, 7)) # Jitter
                    print(f"      Loading page {page_num}...")
                    page.goto(url, wait_until="networkidle", timeout=90_000)
                    
                    # Wait for at least one product tile to appear
                    try:
                        page.wait_for_selector("wc-product-tile, wow-product-tile", timeout=30_000)
                    except:
                        print(f"      [Timeout] No product tiles appeared on page {page_num}.")
                        # Check for 'No results' text
                        if "no results" in page.content().lower():
                            print("      [End] No results found. Category complete.")
                            break
                        # Maybe we are blocked
                        if "access denied" in page.content().lower() or "blocked" in page.content().lower():
                            print("      [BLOCKED] Akamai block detected.")
                            break
                    
                    # Human-like scrolling
                    for _ in range(3):
                        page.mouse.wheel(0, 1000)
                        page.wait_for_timeout(random.randint(1000, 2000))

                    tiles = page.locator("wc-product-tile, wow-product-tile").all()
                    if not tiles:
                        print(f"      No products found on page {page_num}. Ending category.")
                        break
                        
                    products_on_page = 0
                    for tile in tiles:
                        try:
                            # Woolworths title is usually in a.product-title-link
                            name_el = tile.locator("a.product-title-link").first
                            if not name_el.is_visible(): continue
                            
                            name = name_el.inner_text().strip()
                            # Price is in .primary
                            price_el = tile.locator(".primary").first
                            price_text = price_el.inner_text().strip() if price_el.is_visible() else ""
                            price = clean_price(price_text)
                            
                            # Image is the first img in the tile
                            img_el = tile.locator("img").first
                            img_url = img_el.get_attribute("src") or ""
                            
                            if name and price:
                                buffer.append({
                                    "name": name,
                                    "price": price,
                                    "was_price": None, # Heavy scraper focus on current price
                                    "in_stock": "TRUE",
                                    "image": img_url
                                })
                                products_on_page += 1
                        except:
                            continue
                    
                    print(f"    Page {page_num}: +{products_on_page} items")
                    
                    if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
                        print(f"  ══ Flushing {len(buffer)} items... ══")
                        c, u = batch_write(worksheet, buffer, existing, written_names)
                        total_created += c
                        total_updated += u
                        buffer = []
                        
                    if products_on_page < 10: break
                    page_num += 1
                except Exception as e:
                    print(f"    Error on page {page_num}: {e}")
                    break
            
            page.close()
            context.close()

        browser.close()

    if not args.dry_run and buffer:
        print(f"  ══ Final Flush: {len(buffer)} items... ══")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print(f"\nCOMPLETED. Created: {total_created} | Updated: {total_updated}")

if __name__ == "__main__":
    main()
