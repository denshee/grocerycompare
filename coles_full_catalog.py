import time
import random

"""
coles_full_catalog.py
---------------------
Heavy monthly scraper: browses ALL Coles categories strictly through Playwright.
Uses verified __NEXT_DATA__ extraction for 100% image and price reliability.
"""

import argparse
from datetime import datetime
import json
import re
import requests
import urllib.parse
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
        if name in written_names: continue

        key = (name, STORE_NAME)
        if key in existing:
            old_data = existing[key]
            price_changed = (p["price"] is not None and p["price"] != old_data['price'])
            reg_price_changed = (p["was_price"] is not None and p["was_price"] != old_data['reg_price'])
            
            # We aggressively update image if it's missing or looks like a ghost image
            image_missing = not old_data.get('image') or "/placeholder" in old_data.get('image', '').lower()
            
            if price_changed or reg_price_changed or image_missing:
                img_to_update = p["image"] if image_missing else None
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

    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates, history_rows
    )
    return created, updated

def main():
    parser = argparse.ArgumentParser(description="Coles full catalogue scraper")
    parser.add_argument("--category", type=str, help="Specific category slug to scrape")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target_categories = COLES_CATEGORIES
    if args.category:
        if args.category in COLES_CATEGORIES:
            target_categories = [args.category]
        else:
            print(f"Error: Category '{args.category}' not found.")
            import sys; sys.exit(1)

    print("=" * 60)
    print(f"Coles Scrape {'(All)' if not args.category else args.category} → Google Sheets")
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
    from playwright_stealth import Stealth
    print(f"\n[Phase 2] Booting Playwright with Stealth...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        for idx, slug in enumerate(target_categories):
            # Session Rotation
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 1024}
            )
            page = context.new_page()
            Stealth().use_sync(page)
            time.sleep(random.uniform(5, 10))

            print(f"\n  Category: {slug}")
            page_num = 1
            while True:
                if args.max_pages and page_num > args.max_pages: break
                url = f"https://www.coles.com.au/browse/{slug}?page={page_num}"
                
                try:
                    # Random jitter before request
                    time.sleep(random.uniform(5, 12))
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # More natural human behavior
                    page.evaluate("window.scrollTo(0, 300)")
                    page.wait_for_timeout(random.randint(1000, 3000))
                    page.evaluate("window.scrollTo(0, 600)")
                    page.wait_for_timeout(random.randint(2000, 4000))
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(2000)
                except: pass

                # Extract __NEXT_DATA__
                try:
                    # Robust check for the element
                    raw_json = page.evaluate('''() => {
                        const el = document.getElementById("__NEXT_DATA__");
                        return el ? el.textContent : null;
                    }''')
                    
                    if not raw_json:
                        print(f"      No __NEXT_DATA__ found on {url}")
                        # Check if we are blocked
                        if "access denied" in page.content().lower() or "blocked" in page.content().lower() or "challenge" in page.content().lower():
                            print(f"      [BLOCKED] Coles anti-bot detected on page {page_num}. Terminating category.")
                            break
                        page_num += 1
                        continue

                    data = json.loads(raw_json)
                    results = data.get("props", {}).get("pageProps", {}).get("searchResults", {}).get("results", [])
                    
                    if not results:
                        print(f"      No results in JSON for {url}")
                        break

                    products_on_page = 0
                    for res in results:
                        if res.get("_type") != "PRODUCT": continue

                        name = f"{res.get('brand', '')} {res.get('name', '')}".strip()
                        if not name: continue
                        
                        pricing = res.get("pricing", {})
                        price = pricing.get("now")
                        was_price = pricing.get("was")
                        
                        # Image URL construction (Fixed!)
                        img_id = ""
                        uris = res.get("imageUris", [])
                        if uris:
                            img_id = uris[0].get("uri", "")
                        
                        img_url = ""
                        if img_id:
                            # img_id already contains the leading slash from the JSON: "/2/2263179.jpg"
                            cdn_base = "https://cdn.productimages.coles.com.au/productimages"
                            full_cdn = cdn_base + img_id # result: .../productimages/2/2263179.jpg
                            img_url = f"https://www.coles.com.au/_next/image?url={urllib.parse.quote(full_cdn)}&w=640&q=90"

                        if name and price is not None:
                            buffer.append({
                                "name": name,
                                "price": float(price),
                                "was_price": float(was_price) if was_price else None,
                                "in_stock": "TRUE",
                                "image": img_url
                            })
                            products_on_page += 1
                    
                    total_scraped += products_on_page
                    print(f"    Page {page_num}: +{products_on_page} products")

                    if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
                        print(f"  ══ Flushing {len(buffer)} items... ══")
                        c, u = batch_write(worksheet, buffer, existing, written_names)
                        total_created += c
                        total_updated += u
                        buffer = []

                    if products_on_page < 10: break
                    page_num += 1

                except Exception as e:
                    print(f"      Error: {e}")
                    break

        browser.close()

    if not args.dry_run and buffer:
        print(f"  ══ Final Flush: {len(buffer)} items... ══")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print(f"\nCOMPLETED. Created: {total_created} | Updated: {total_updated}")

if __name__ == "__main__":
    main()
