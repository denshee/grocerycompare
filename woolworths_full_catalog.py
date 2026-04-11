"""
woolworths_full_catalog.py
--------------------------
Heavy monthly scraper: browses ALL Woolworths categories via their internal
browse API and writes every product to Google Sheets.

Strategy
--------
1. Playwright boots a real Chromium browser once to earn valid Akamai session
   cookies (_abck, bm_sz, etc.)
2. Those cookies are handed to a requests.Session for fast API calls — one
   browser session, hundreds of API page requests
3. Products are collected in memory then written to Google Sheets in a single
   batch_upsert() call (1 read + 2 writes total)

Config
------
Set MAX_PAGES_PER_CATEGORY = None for truly unlimited (full catalogue).
Start with a small number (e.g. 3) to validate before going unlimited.

Usage
-----
    python woolworths_full_catalog.py                    # full run
    python woolworths_full_catalog.py --max-pages 2     # limit depth (testing)
    python woolworths_full_catalog.py --categories dairy-eggs-fridge,bakery
"""

import argparse
import json
import sys
import time
import requests
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Woolworths"
PAGE_SIZE   = 36      # Woolworths max per page
BATCH_WRITE_EVERY = 500   # write to Sheets every N new products collected
HTTP_DELAY  = 0.3    # seconds between API page requests (polite, not throttled)

# Woolworths internal browse API base
WW_BASE     = "https://www.woolworths.com.au"
BROWSE_API  = WW_BASE + "/apis/ui/browse/category"
CATS_API    = WW_BASE + "/apis/ui/PiesCategoriesWithSpecials"

# Top-level category slugs — used as fallback if the categories API is gated.
# This list covers the full Woolworths grocery catalogue.
WOOLWORTHS_CATEGORIES = [
    "fruit-veg",
    "meat-seafood",
    "dairy-eggs-fridge",
    "bakery",
    "deli",
    "pantry",
    "frozen-foods",
    "drinks",
    "health-beauty",
    "household",
    "baby",
    "pet",
    "international-foods",
    "entertaining",
]


# ── Phase 1: Playwright session bootstrap ────────────────────────────────────

def get_session_cookies(headless: bool = True) -> dict:
    """Launch a real Chromium browser, load the Woolworths homepage to
    acquire valid Akamai session cookies, then return them as a dict.

    headless=True works in GitHub Actions (Ubuntu + Xvfb not needed for
    cookie acquisition).  Set headless=False for local debugging.
    """
    from playwright.sync_api import sync_playwright

    print("\n[Phase 1] Bootstrapping browser session to acquire Akamai cookies...")
    cookies = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-AU",
        )
        page = context.new_page()

        print("  → Navigating to woolworths.com.au...")
        page.goto(WW_BASE + "/", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4_000)  # let Akamai sensor script run

        # Grab all cookies from the context
        for c in context.cookies():
            cookies[c["name"]] = c["value"]

        # Also capture the session cookie Woolworths uses for browse API auth
        # by making one real browse navigation inside the browser
        try:
            page.goto(
                WW_BASE + "/shop/browse/dairy-eggs-fridge?pageNumber=1",
                wait_until="domcontentloaded",
                timeout=20_000
            )
            page.wait_for_timeout(2_000)
            for c in context.cookies():
                cookies[c["name"]] = c["value"]
        except Exception as e:
            print(f"  ⚠ Browse navigation skipped ({e}); cookies may still be sufficient")

        browser.close()

    key_cookies = {k: v for k, v in cookies.items()
                   if k in ("_abck", "bm_sz", "WowWidgetPageSession",
                             "wowWidgetPublicSessionId", "bm_sv", "ak_bmsc")}
    print(f"  ✓ Captured {len(cookies)} cookies total "
          f"({len(key_cookies)} Akamai/session keys)")
    return cookies


# ── Phase 2: Category discovery ───────────────────────────────────────────────

def get_categories(session: requests.Session) -> list[str]:
    """Try the categories API; fall back to the hardcoded list."""
    print("\n[Phase 2] Discovering categories...")
    try:
        resp = session.get(CATS_API, timeout=10)
        if resp.ok:
            data = resp.json()
            # Response shape: list of category objects with 'NodeUrl'
            cats = []
            for item in data:
                url = item.get("NodeUrl") or item.get("UrlFriendlyName") or ""
                url = url.strip("/").split("/")[-1]
                if url:
                    cats.append(url)
                # Include children
                for child in item.get("Children", []):
                    curl = child.get("NodeUrl") or child.get("UrlFriendlyName") or ""
                    curl = curl.strip("/").split("/")[-1]
                    if curl:
                        cats.append(curl)
            if cats:
                print(f"  ✓ API returned {len(cats)} category slugs")
                return list(dict.fromkeys(cats))  # deduplicate, preserve order
    except Exception as e:
        print(f"  ⚠ Categories API failed ({e}), using hardcoded list")

    print(f"  → Using hardcoded list: {len(WOOLWORTHS_CATEGORIES)} categories")
    return WOOLWORTHS_CATEGORIES


# ── Phase 3: Per-category product fetching ────────────────────────────────────

def fetch_category_products(session: requests.Session,
                            category_slug: str,
                            max_pages: int | None) -> list[dict]:
    """Fetch all pages for a single category via the browse API.

    Returns a list of raw product dicts.
    """
    products = []
    page_num  = 1

    while True:
        if max_pages is not None and page_num > max_pages:
            break

        url = BROWSE_API
        params = {
            "url":         f"/shop/browse/{category_slug}",
            "pageNumber":  page_num,
            "pageSize":    PAGE_SIZE,
            "formatObject": json.dumps({"name": "category"}),
            "inStoreFilters": "[]",
            "filters":     "[]",
            "token":       "",
            "isMobile":    "false",
        }

        try:
            resp = session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            print(f"    ✗ Network error on page {page_num}: {e}")
            break

        if resp.status_code == 403:
            print(f"    ✗ 403 Forbidden — session may have expired (page {page_num})")
            break
        if not resp.ok:
            print(f"    ✗ HTTP {resp.status_code} on page {page_num}")
            break

        try:
            data = resp.json()
        except Exception:
            print(f"    ✗ Invalid JSON on page {page_num}")
            break

        # Navigate the response: Bundles → Products
        bundles = (
            data.get("Bundles") or
            data.get("Products") or
            (data.get("SearchResultsJson") or {}).get("Products") or
            []
        )

        page_products = []
        for bundle in bundles:
            # Bundles contain a "Products" array
            if isinstance(bundle, dict):
                inner = bundle.get("Products", [])
                if inner:
                    page_products.extend(inner)
                elif bundle.get("DisplayName"):
                    # Some responses put products directly in Bundles
                    page_products.append(bundle)

        if not page_products:
            break  # No more products — done with this category

        products.extend(page_products)
        total_shown = data.get("TotalRecordCount") or data.get("Total") or 0
        print(f"    Page {page_num}: +{len(page_products)} products "
              f"(running: {len(products)}/{total_shown or '?'})")

        # Check if we've fetched all products
        if total_shown and len(products) >= total_shown:
            break

        page_num += 1
        time.sleep(HTTP_DELAY)

    return products


# ── Product normalisation ─────────────────────────────────────────────────────

def normalise(raw: dict, category_slug: str) -> dict | None:
    """Extract and normalise a single product dict from the API response."""
    name = (raw.get("DisplayName") or raw.get("Name") or "").strip()
    if not name:
        return None

    price      = raw.get("Price")
    was_price  = raw.get("WasPrice")
    in_stock   = raw.get("IsInStock", True)
    is_avail   = raw.get("IsAvailable", True)
    image      = (raw.get("MediumImageFile") or raw.get("SmallImageFile") or "")
    size       = (raw.get("PackageSize") or raw.get("CupMeasure") or "")
    stockcode  = raw.get("Stockcode") or raw.get("StockCode") or ""

    if not is_avail:
        return None

    return {
        "name":          name,
        "price":         float(price) if price is not None else None,
        "was_price":     float(was_price) if was_price is not None else None,
        "in_stock":      bool(in_stock),
        "image":         image,
        "size":          size,
        "stockcode":     str(stockcode),
        "category":      category_slug,
    }


# ── Phase 4: Classify and batch-write ─────────────────────────────────────────

def batch_write(worksheet, products_buffer: list[dict],
                existing: dict, written_names: set) -> tuple[int, int]:
    """Classify buffered products and flush to Google Sheets.

    Returns (created, updated) counts for this flush.
    """
    new_rows      = []
    price_updates = []

    for p in products_buffer:
        name = p["name"]
        if name in written_names:
            continue  # already written in a previous batch this run

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
            existing[key] = -1  # mark to avoid re-adding in same run

        written_names.add(name)

    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates
    )
    return created, updated


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Woolworths full catalogue scraper")
    parser.add_argument("--max-pages",   type=int,   default=None,
                        help="Max pages per category (default: unlimited)")
    parser.add_argument("--categories",  type=str,   default=None,
                        help="Comma-separated category slugs to scrape (default: all)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Run browser visibly (local debugging only)")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Scrape but do NOT write to Google Sheets")
    args = parser.parse_args()

    print("=" * 60)
    print("Woolworths Full Catalogue → Google Sheets")
    print("=" * 60)
    if args.max_pages:
        print(f"  Mode      : LIMITED ({args.max_pages} pages/category)")
    else:
        print("  Mode      : FULL CATALOGUE (unlimited pages)")
    if args.dry_run:
        print("  Dry run   : ON (no writes to Sheets)")

    # ── Phase 1: Get browser session cookies ──────────────────────────────
    headless = not args.no_headless
    cookies  = get_session_cookies(headless=headless)

    # Build a requests session with those cookies + browser-like headers
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent":       ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/122.0.0.0 Safari/537.36"),
        "Accept":           "application/json, text/plain, */*",
        "Accept-Language":  "en-AU,en;q=0.9",
        "Referer":          WW_BASE + "/",
        "Origin":           WW_BASE,
    })

    # ── Phase 2: Discover categories ──────────────────────────────────────
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
        print(f"\n[Phase 2] Using provided categories: {categories}")
    else:
        categories = get_categories(session)

    # ── Phase 3: Connect to Sheets (once) ─────────────────────────────────
    print("\n[Phase 3] Connecting to Google Sheets...")
    worksheet = None
    existing  = {}
    if not args.dry_run:
        worksheet = sheets_helper.get_listings_worksheet()
        existing  = sheets_helper.load_existing_listings(worksheet)

    # ── Phase 4: Scrape each category ─────────────────────────────────────
    print(f"\n[Phase 4] Scraping {len(categories)} categories...\n")
    buffer       = []
    written_names: set[str] = set()
    total_created = 0
    total_updated = 0
    total_scraped = 0
    total_skipped = 0

    for cat_idx, slug in enumerate(categories, 1):
        print(f"\n  [{cat_idx}/{len(categories)}] Category: {slug}")
        raw_products = fetch_category_products(session, slug, args.max_pages)

        for raw in raw_products:
            product = normalise(raw, slug)
            if product:
                buffer.append(product)
            else:
                total_skipped += 1

        total_scraped += len(raw_products)
        print(f"  → Collected {len(raw_products)} raw / "
              f"{len(buffer)} buffered (buffer total: {len(buffer)})")

        # Flush to Sheets every BATCH_WRITE_EVERY products
        if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
            print(f"\n  ══ Flushing {len(buffer)} products to Sheets... ══")
            c, u = batch_write(worksheet, buffer, existing, written_names)
            total_created += c
            total_updated += u
            buffer = []
            print(f"  ══ Flush done: +{c} new, ~{u} updated ══\n")

    # Final flush for remaining buffer
    if not args.dry_run and buffer:
        print(f"\n[Phase 5] Final flush: {len(buffer)} products...")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("WOOLWORTHS FULL CATALOGUE — COMPLETE")
    print(f"  Categories scraped : {len(categories)}")
    print(f"  Raw products seen  : {total_scraped}")
    print(f"  Skipped (no name)  : {total_skipped}")
    print(f"  Unique processed   : {len(written_names)}")
    if not args.dry_run:
        print(f"  Created in Sheets  : {total_created}")
        print(f"  Updated in Sheets  : {total_updated}")
    else:
        print("  Sheets writes      : SKIPPED (dry run)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
