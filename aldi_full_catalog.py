"""
aldi_full_catalog.py
--------------------
Heavy monthly scraper: browses ALL Aldi AU core grocery categories via Playwright
DOM extraction and writes every product to Google Sheets.

Strategy
--------
1. Launch Chromium via Playwright.
2. Iterate through core Aldi Grocery Category URLs (discovered via sitemap).
3. For each category, scrape product tiles (div.product-tile).
4. Normalise pricing ($1.23 or 80c handled).
5. Batch write to Google Sheets using sheets_helper (500 items per flush).
"""

import argparse
import re
import sys
import time
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Aldi"
BATCH_WRITE_EVERY = 500

ALDI_BASE = "https://www.aldi.com.au"

# Curated grocery-specific category URLs from sitemap exploration
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

# ── Normalization Helpers ────────────────────────────────────────────────────

def clean_price(price_text: str) -> float | None:
    """Handles '$1.23', '80c', '1.23', etc."""
    if not price_text:
        return None
    
    # Check for cents format (e.g. 80c)
    if 'c' in price_text.lower():
        digits = re.sub(r'[^\d]', '', price_text)
        if digits:
            return float(digits) / 100.0
            
    # Standard dollar format ($1.23)
    cleaned = re.sub(r'[^\d.]', '', price_text)
    try:
        if cleaned:
            return float(cleaned)
    except (ValueError, TypeError):
        pass
    return None

# ── Batch Write Helper ───────────────────────────────────────────────────────

def batch_write(worksheet, products_buffer: list[dict],
                existing: dict, written_names: set) -> tuple[int, int]:
    """Classify buffered products and flush to Google Sheets."""
    new_rows      = []
    price_updates = []

    for p in products_buffer:
        name = p["name"]
        if name in written_names:
            continue

        key = (name, STORE_NAME)
        if key in existing:
            if p["price"] is not None and p["price"] > 0:
                price_updates.append((existing[key], p["price"]))
        else:
            new_rows.append([
                "",                              # Listing_ID
                name,
                STORE_NAME,
                p["price"] if p["price"] is not None else "",
                p["was_price"] if p["was_price"] is not None else "",
                p["in_stock"],
                p["image"],
            ])
            # Locally mark as -1 to avoid duplicates in SAME run
            existing[key] = -1

        written_names.add(name)

    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates
    )
    return created, updated

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Aldi full catalogue scraper")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Sheets")
    args = parser.parse_args()

    print("=" * 60)
    print("Aldi AU Full Catalogue → Google Sheets")
    print("=" * 60)

    # 1. Connect to Sheets
    print("\n[Phase 1] Connecting to Google Sheets...")
    worksheet = None
    existing  = {}
    if not args.dry_run:
        worksheet = sheets_helper.get_listings_worksheet()
        existing  = sheets_helper.load_existing_listings(worksheet)

    buffer = []
    written_names: set[str] = set()
    total_created = 0
    total_updated = 0
    total_scraped = 0

    from playwright.sync_api import sync_playwright

    print(f"\n[Phase 2] Booting Playwright to scrape {len(ALDI_CATEGORIES)} Categories...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            # Block unnecessary resources for speed
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        for cat_idx, url in enumerate(ALDI_CATEGORIES, 1):
            category_name = url.split('/')[-3]
            print(f"\n  [{cat_idx}/{len(ALDI_CATEGORIES)}] Category: {category_name}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                # Wait for tiles to hydrated
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"    ✗ Error loading {category_name}: {e}")
                continue

            # Aldi core range usually hasn't got heavy pagination, but if it does:
            # We scrape the current view.
            
            tiles = page.locator("div.product-tile").all()
            print(f"    Found {len(tiles)} product tiles")
            
            products_on_page = 0
            for tile in tiles:
                try:
                    # Selectors identified via research phase
                    name_el = tile.locator(".product-tile__name p").first
                    price_el = tile.locator(".base-price__regular span").first
                    img_el = tile.locator(".product-tile__picture img").first
                    
                    if not name_el.is_visible() or not price_el.is_visible():
                        continue
                        
                    name = name_el.inner_text().strip()
                    price_str = price_el.inner_text().strip()
                    price = clean_price(price_str)
                    
                    # Brand extraction (optional, but good for uniqueness)
                    brand = ""
                    if tile.locator(".product-tile__brandname p").is_visible():
                        brand = tile.locator(".product-tile__brandname p").first.inner_text().strip()
                        if brand:
                            name = f"{brand} {name}"

                    img_url = img_el.get_attribute("src") or ""
                    if img_url and img_url.startswith("//"):
                        img_url = "https:" + img_url

                    if name and price:
                        buffer.append({
                            "name": name,
                            "price": price,
                            "was_price": None, # Aldi rarely shows simple was_price in catalog
                            "in_stock": True,
                            "image": img_url
                        })
                        products_on_page += 1
                except Exception:
                    continue

            total_scraped += products_on_page
            print(f"    → Extracted {products_on_page} items from {category_name}")

            if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
                print(f"\n  ══ Flushing {len(buffer)} products to Sheets... ══")
                c, u = batch_write(worksheet, buffer, existing, written_names)
                total_created += c
                total_updated += u
                buffer = []
                print(f"  ══ Flush done: +{c} new, ~{u} updated ══\n")

        browser.close()

    # Final flush
    if not args.dry_run and buffer:
        print(f"\n[Phase 3] Final flush: {len(buffer)} products...")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print(f"\n{'=' * 60}")
    print("ALDI FULL CATALOGUE COMPLETE")
    print(f"  Categories scraped : {len(ALDI_CATEGORIES)}")
    print(f"  Raw products seen  : {total_scraped}")
    print(f"  Unique processed   : {len(written_names)}")
    if not args.dry_run:
        print(f"  Created in Sheets  : {total_created}")
        print(f"  Updated in Sheets  : {total_updated}")
    else:
        print("  Sheets writes      : SKIPPED (dry run)")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
