"""
coles_full_catalog.py
---------------------
Heavy monthly scraper: browses ALL Coles categories strictly through Playwright
DOM inspection to perfectly bypass Datadome and extract the full catalogue.

Strategy
--------
1. Launch Chromium via Playwright, ensuring Datadome passes correctly.
2. Iterate through high-level Category URL slugs.
3. For each category, paginate through the specific ?page=N query parameters.
4. Scrape native DOM tiles ([data-testid='product-tile'])
5. Batch write every 500 items using sheets_helper to stay well within quotas.
"""

import argparse
import sys
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Coles"
BATCH_WRITE_EVERY = 500

WW_BASE = "https://www.coles.com.au"

COLES_CATEGORIES = [
    "meat-seafood",
    "fruit-vegetables",
    "dairy-eggs-fridge",
    "bakery",
    "deli",
    "pantry",
    "drinks",
    "frozen",
    "household",
    "health-beauty",
    "baby",
    "pet",
    "liquor"
]

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
            existing[key] = -1

        written_names.add(name)

    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates
    )
    return created, updated

def extract_price(text: str) -> float | None:
    """Takes pricing strings like '$3.50' or '80c' and normalises to float."""
    import re
    if not text:
        return None
    # If using cents
    if text.endswith('c'):
        val = re.sub(r'[^\d]', '', text)
        return float(val) / 100.0 if val else None
    
    val = re.sub(r'[^\d\.]', '', text)
    try:
        if val:
            return float(val)
    except:
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Coles full catalogue scraper")
    parser.add_argument("--max-pages",   type=int,   default=None,
                        help="Max pages per category (default: unlimited)")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Scrape but do NOT write to Google Sheets")
    args = parser.parse_args()

    print("=" * 60)
    print("Coles Full Catalogue → Google Sheets")
    print("=" * 60)
    
    # ── Phase 1: Connect to Sheets (once) ─────────────────────────────────
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

    print(f"\n[Phase 2] Booting Playwright to scrape {len(COLES_CATEGORIES)} Categories natively...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # Warm up Datadome constraints by interacting with the homepage natively first.
        page.goto("https://www.coles.com.au/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        for cat_idx, slug in enumerate(COLES_CATEGORIES, 1):
            print(f"\n  [{cat_idx}/{len(COLES_CATEGORIES)}] Category: {slug}")
            page_num = 1
            
            while True:
                if args.max_pages and page_num > args.max_pages:
                    print(f"    Reached max pages ({args.max_pages}) for category")
                    break

                # The literal category query syntax Coles uses:
                url = f"https://www.coles.com.au/browse/{slug}?page={page_num}"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    # wait explicitly for Native rendered grid payload
                    page.wait_for_selector("[data-testid='product-tile']", timeout=15_000)
                except Exception as e:
                    # Timeouts generally denote we've hit the exact end of pagination structure
                    # or there were no items on the queried page!
                    print(f"    Page {page_num} rendered no products, stopping {slug}.")
                    break

                page.wait_for_timeout(1000) # Quick hydration buffer

                tiles = page.locator("[data-testid='product-tile']").all()
                if not tiles:
                    break

                products_on_page = 0
                for tile in tiles:
                    try:
                        name_el = tile.locator(".product__title")
                        price_el = tile.locator(".price__value")
                        if not name_el.is_visible() or not price_el.is_visible():
                            continue
                            
                        name = name_el.first.inner_text().strip()
                        price_str = price_el.first.inner_text().strip()
                        price = extract_price(price_str)
                        
                        # Was price handling
                        was_price = None
                        if tile.locator(".price__was").is_visible():
                            was = tile.locator(".price__was").first.inner_text().strip()
                            was_price = extract_price(was)

                        # Image handling
                        img_url = ""
                        if tile.locator("img[data-testid='product-image']").is_visible():
                            img_url = tile.locator("img[data-testid='product-image']").get_attribute("src") or ""

                        # In-stock checks
                        in_stock = True
                        if tile.locator("text='Temporarily unavailable'").is_visible():
                            in_stock = False

                        if name and price:
                            buffer.append({
                                "name": name,
                                "price": price,
                                "was_price": was_price,
                                "in_stock": in_stock,
                                "image": img_url,
                                "category": slug
                            })
                            products_on_page += 1
                    except Exception as ex:
                        pass
                
                total_scraped += products_on_page
                print(f"    Page {page_num}: +{products_on_page} products "
                      f"(running: {total_scraped}) / buffer {len(buffer)}")

                if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
                    print(f"\n  ══ Flushing {len(buffer)} products to Sheets... ══")
                    c, u = batch_write(worksheet, buffer, existing, written_names)
                    total_created += c
                    total_updated += u
                    buffer = []
                    print(f"  ══ Flush done: +{c} new, ~{u} updated ══\n")

                if products_on_page < 48:
                    # Coles maps precisely 48 products structurally per array page
                    # if < 48, it is universally the last functional pagination block
                    print(f"    Reached end of category {slug} (found {products_on_page} < 48 blocks)")
                    break

                page_num += 1

        browser.close()

    # Final flush
    if not args.dry_run and buffer:
        print(f"\n[Phase 3] Final flush: {len(buffer)} products...")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print(f"\n{'=' * 60}")
    print("COLES FULL CATALOGUE — COMPLETE")
    print(f"  Categories scraped : {len(COLES_CATEGORIES)}")
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
