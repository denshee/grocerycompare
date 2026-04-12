"""
woolworths_full_catalog.py
--------------------------
Heavy monthly scraper: browses ALL Woolworths categories via their internal
browse API and writes every product to Google Sheets.
"""

import argparse
import json
import sys
import time
from datetime import datetime
import requests
import sheets_helper

# ── Configuration ─────────────────────────────────────────────────────────────

STORE_NAME = "Woolworths"
PAGE_SIZE   = 36
BATCH_WRITE_EVERY = 500
HTTP_DELAY  = 0.3

WW_BASE     = "https://www.woolworths.com.au"
BROWSE_API  = WW_BASE + "/apis/ui/browse/category"
CATS_API    = WW_BASE + "/apis/ui/PiesCategoriesWithSpecials"

WOOLWORTHS_CATEGORIES = [
    "fruit-veg", "meat-seafood", "dairy-eggs-fridge", "bakery", "deli",
    "pantry", "frozen-foods", "drinks", "health-beauty", "household",
    "baby", "pet", "international-foods", "entertaining",
]


def get_session_cookies(headless: bool = True) -> dict:
    """Launch a real Chromium browser to earn valid Akamai session cookies."""
    from playwright.sync_api import sync_playwright
    print("\n[Phase 1] Bootstrapping browser session...")
    cookies = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-AU",
        )
        page = context.new_page()
        page.goto(WW_BASE + "/", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4_000)
        for c in context.cookies():
            cookies[c["name"]] = c["value"]
        try:
            page.goto(WW_BASE + "/shop/browse/dairy-eggs-fridge?pageNumber=1", wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(2_000)
            for c in context.cookies():
                cookies[c["name"]] = c["value"]
        except Exception:
            pass
        browser.close()
    return cookies


def get_categories(session: requests.Session) -> list[str]:
    """Discover categories via API."""
    print("\n[Phase 2] Discovering categories...")
    try:
        resp = session.get(CATS_API, timeout=10)
        if resp.ok:
            data = resp.json()
            cats = []
            for item in data:
                url = item.get("NodeUrl") or item.get("UrlFriendlyName") or ""
                url = url.strip("/").split("/")[-1]
                if url: cats.append(url)
                for child in item.get("Children", []):
                    curl = child.get("NodeUrl") or child.get("UrlFriendlyName") or ""
                    curl = curl.strip("/").split("/")[-1]
                    if curl: cats.append(curl)
            if cats: return list(dict.fromkeys(cats))
    except Exception:
        pass
    return WOOLWORTHS_CATEGORIES


def fetch_category_products(session: requests.Session, category_slug: str, max_pages: int | None) -> list[dict]:
    """Fetch all products for a category."""
    products = []
    page_num  = 1
    while True:
        if max_pages is not None and page_num > max_pages: break
        params = {
            "url": f"/shop/browse/{category_slug}",
            "pageNumber": page_num,
            "pageSize": PAGE_SIZE,
            "formatObject": json.dumps({"name": "category"}),
            "inStoreFilters": "[]", "filters": "[]", "token": "", "isMobile": "false",
        }
        try:
            resp = session.get(BROWSE_API, params=params, timeout=15)
            if not resp.ok: break
            data = resp.json()
            bundles = (data.get("Bundles") or data.get("Products") or 
                       (data.get("SearchResultsJson") or {}).get("Products") or [])
            page_products = []
            for b in bundles:
                if isinstance(b, dict):
                    inner = b.get("Products", [])
                    if inner: page_products.extend(inner)
                    elif b.get("DisplayName"): page_products.append(b)
            if not page_products: break
            products.extend(page_products)
            total = data.get("TotalRecordCount") or data.get("Total") or 0
            if total and len(products) >= total: break
            page_num += 1
            time.sleep(HTTP_DELAY)
        except Exception:
            break
    return products


def normalise(raw: dict, category_slug: str) -> dict | None:
    """Extract and normalise product data."""
    name = (raw.get("DisplayName") or raw.get("Name") or "").strip()
    if not name: return None
    if not raw.get("IsAvailable", True): return None
    price      = raw.get("Price")
    was_price  = raw.get("WasPrice")
    return {
        "name": name,
        "price": float(price) if price is not None else None,
        "was_price": float(was_price) if was_price is not None else None,
        "in_stock": bool(raw.get("IsInStock", True)),
        "image": (raw.get("MediumImageFile") or raw.get("SmallImageFile") or ""),
    }


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

    created, updated = sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, price_updates, history_rows)
    return created, updated


def main():
    parser = argparse.ArgumentParser(description="Woolworths full catalogue scraper")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--categories", type=str, default=None)
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Woolworths Full Catalogue → Google Sheets (+ History)")
    print("=" * 60)

    cookies = get_session_cookies(headless=not args.no_headless)
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*", "Referer": WW_BASE + "/", "Origin": WW_BASE,
    })

    if args.categories:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    else:
        categories = get_categories(session)

    print("\n[Phase 3] Connecting to Google Sheets...")
    worksheet = None
    existing  = {}
    if not args.dry_run:
        worksheet = sheets_helper.get_listings_worksheet()
        existing  = sheets_helper.load_existing_listings(worksheet)

    print(f"\n[Phase 4] Scraping {len(categories)} categories...\n")
    buffer = []
    written_names = set()
    total_created = 0
    total_updated = 0

    for slug in categories:
        raw_products = fetch_category_products(session, slug, args.max_pages)
        for raw in raw_products:
            product = normalise(raw, slug)
            if product: buffer.append(product)

        if not args.dry_run and len(buffer) >= BATCH_WRITE_EVERY:
            print(f"  ══ Flushing {len(buffer)} products... ══")
            c, u = batch_write(worksheet, buffer, existing, written_names)
            total_created += c
            total_updated += u
            buffer = []

    if not args.dry_run and buffer:
        print(f"  ══ Final Flush: {len(buffer)} products... ══")
        c, u = batch_write(worksheet, buffer, existing, written_names)
        total_created += c
        total_updated += u

    print("\nCOMPLETED.")
    if not args.dry_run:
        print(f"  Created: {total_created} | Updated: {total_updated}")


if __name__ == "__main__":
    main()
