"""
scrape_bestsellers.py
---------------------
Targeted scraper for high-frequency grocery items (top 50-100 per store) 
using Playwright for maximum resilience against bot detection.
Pivots to Category Browse for essentials as Search endpoints are highly protected.
"""

import time
import random
import re
import json
from datetime import datetime
import sheets_helper
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ── Configuration ─────────────────────────────────────────────────────────────

# Essential Categories (Proven Browse URLs are more stable than search)
WOOLWORTHS_BROWSE_PATHS = [
    ("/shop/browse/dairy-eggs-fridge/milk", "Milk"),
    ("/shop/browse/bakery/bread", "Bread"),
    ("/shop/browse/dairy-eggs-fridge/eggs", "Eggs"),
    ("/shop/browse/dairy-eggs-fridge/butter-margarine", "Butter"),
    ("/shop/browse/meat-seafood-deli/meat/chicken", "Chicken"),
    ("/shop/browse/meat-seafood-deli/meat/beef", "Beef"),
    ("/shop/browse/pantry/rice-pasta-grains", "Rice/Pasta"),
    ("/shop/browse/fruit-veg", "Fruit & Veg")
]

COLES_BROWSE_PATHS = [
    ("/browse/dairy-eggs-fridge/milk", "Milk"),
    ("/browse/bakery/bread", "Bread"),
    ("/browse/dairy-eggs-fridge/eggs", "Eggs"),
    ("/browse/meat-seafood/chicken", "Chicken"),
    ("/browse/meat-seafood/beef-veal", "Beef"),
    ("/browse/pantry/pasta-rice-legumes", "Rice/Pasta"),
    ("/browse/fruit-vegetables", "Fruit & Veg")
]

ALDI_TARGET_PATHS = [
    ("/products/fruits-vegetables/k/950000000", "Fruits & Veg"),
    ("/products/meat-seafood/k/940000000", "Meat & Seafood"),
    ("/products/dairy-eggs-fridge/k/960000000", "Dairy & Eggs"),
    ("/products/bakery/k/920000000", "Bakery"),
    ("/products/pantry/k/970000000", "Pantry"),
    ("/products/cleaning-household/k/1050000000", "Household")
]

# Targeted search terms for specific brands (less frequency, lower block risk)
BRAND_SEARCH_TERMS = [
    "Bega cheese", "Devondale milk", "Cadbury chocolate", "Arnott's biscuits",
    "Streets ice cream", "Golden Circle juice", "SPC baked beans",
    "Weet-Bix", "Kellogg's cornflakes", "Uncle Tobys",
    "Masterfoods", "Fountain sauce", "Praise mayonnaise"
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_price(text):
    if not text: return None
    try:
        cleaned = re.sub(r'[^\d.]', '', text)
        return float(cleaned) if cleaned else None
    except: return None

def build_upsert_data(products, store_name, existing):
    new_rows = []
    price_updates = []
    history_rows = []
    seen_names = set()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for p in products:
        name = p.get("name", "").strip()
        if not name or name in seen_names: continue
        seen_names.add(name)

        price = p.get("price")
        was_price = p.get("was_price")
        in_stock = p.get("in_stock", True)
        image_url = p.get("image", "")

        key = (name, store_name)
        if key in existing:
            old_data = existing[key]
            price_changed = (price is not None and price != old_data['price'])
            reg_price_changed = (was_price is not None and was_price != old_data['reg_price'])
            image_missing = not old_data.get('image') or "placeholder" in old_data.get('image','').lower()

            if price_changed or reg_price_changed or image_missing:
                img_update = image_url if image_missing else None
                price_updates.append((old_data['row'], price, was_price, img_update))
                if price_changed or reg_price_changed:
                    history_rows.append([now_str, name, store_name, price, was_price or ""])
        else:
            new_rows.append([
                "", name, store_name,
                price if price is not None else "",
                was_price if was_price is not None else "",
                "TRUE" if in_stock else "FALSE",
                image_url
            ])
            history_rows.append([now_str, name, store_name, price if price is not None else "", was_price or ""])
            existing[key] = {'row': -1, 'price': price, 'reg_price': was_price}

    return new_rows, price_updates, history_rows

# ── Store Scrapers ───────────────────────────────────────────────────────────

def fetch_woolworths(page):
    results = []
    print("  Woolworths: Scraping top products from essentials categories...")
    for path, cat_name in WOOLWORTHS_BROWSE_PATHS:
        url = f"https://www.woolworths.com.au{path}?sortBy=TraderRelevance"
        print(f"    {cat_name}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            for _ in range(2):
                page.mouse.wheel(0, 800)
                page.wait_for_timeout(1000)
            
            tiles = page.locator("wc-product-tile, wow-product-tile, .product-tile").all()
            count = 0
            for tile in tiles:
                try:
                    name_el = tile.locator(".product-title-link, .product-tile-title, h3").first
                    if not name_el.is_visible(): continue
                    name = name_el.inner_text().strip()
                    price_text = tile.locator(".primary, .product-tile-price, .price").first.inner_text().strip()
                    price = clean_price(price_text)
                    img = tile.locator("img.product-tile-image, img").first.get_attribute("src") or ""
                    if name and price:
                        results.append({"name": name, "price": price, "was_price": None, "in_stock": True, "image": img})
                        count += 1
                    if count >= 30: break 
                except: pass
            print(f"      Found {count} items.")
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"      Error on {cat_name}: {e}")
    return results

def fetch_coles(page):
    results = []
    print("  Coles: Scraping top products from essentials categories...")
    for path, cat_name in COLES_BROWSE_PATHS:
        url = f"https://www.coles.com.au{path}"
        print(f"    {cat_name}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(2000)

            raw_json = page.evaluate('() => document.getElementById("__NEXT_DATA__")?.textContent')
            count = 0
            if raw_json:
                data = json.loads(raw_json)
                items = data.get("props", {}).get("pageProps", {}).get("searchResults", {}).get("results", [])
                for item in items:
                    if item.get("_type") != "PRODUCT": continue
                    pricing = item.get("pricing", {})
                    img_uris = item.get("imageUris", [])
                    img_url = img_uris[0].get("url") if img_uris else ""
                    results.append({
                        "name": f"{item.get('brand','')} {item.get('name','')}".strip(),
                        "price": pricing.get("now"),
                        "was_price": pricing.get("was"),
                        "in_stock": item.get("availability") is True,
                        "image": img_url
                    })
                    count += 1
                    if count >= 30: break
            print(f"      Found {count} items.")
            time.sleep(random.uniform(3, 6))
        except Exception as e:
            print(f"      Error on {cat_name}: {e}")
    return results

def fetch_aldi(page):
    results = []
    print("  Aldi: Scraping first page of Essentials categories...")
    for path, name in ALDI_TARGET_PATHS:
        url = "https://www.aldi.com.au" + path
        print(f"    {name}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            tiles = page.locator("div.product-tile").all()
            count = 0
            for tile in tiles:
                try:
                    name_el = tile.locator(".product-tile__name p").first
                    price_el = tile.locator(".base-price__regular span").first
                    if not name_el.is_visible(): continue
                    brand = ""
                    if tile.locator(".product-tile__brandname p").is_visible():
                        brand = tile.locator(".product-tile__brandname p").first.inner_text().strip()
                    full_name = name_el.inner_text().strip()
                    if brand: full_name = f"{brand} {full_name}"
                    price = clean_price(price_el.inner_text())
                    img = tile.locator(".product-tile__picture img").first.get_attribute("src") or ""
                    if img.startswith("//"): img = "https:" + img
                    if full_name and price:
                        results.append({"name": full_name, "price": price, "was_price": None, "in_stock": True, "image": img})
                        count += 1
                except: pass
            print(f"      Found {count} items.")
        except Exception as e:
            print(f"      Error on Aldi {name}: {e}")
    return results

def fetch_brand_searches(page):
    """Fallback search for brand-specific items if needed."""
    # (Optional: can be added if category browse misses key brands)
    pass

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("BEST SELLERS SYNC (BROWSE HARDENED)")
    print("=" * 60)

    print("\n[P1] Sheets setup...")
    try:
        worksheet = sheets_helper.get_listings_worksheet()
        existing = sheets_helper.load_existing_listings(worksheet)
    except Exception as e:
        print(f"  Error setup sheets: {e}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36")
        page = context.new_page()
        Stealth().use_sync(page)

        print("\n[P2] Scraping Woolworths Browse...")
        ww_data = fetch_woolworths(page) or []
        
        print("\n[P3] Scraping Coles Browse...")
        coles_data = fetch_coles(page) or []

        print("\n[P4] Scraping Aldi Browse...")
        aldi_data = fetch_aldi(page) or []
        
        browser.close()

    print("\n[P5] Syncing to Sheets...")
    for s_name, data in [("Woolworths", ww_data), ("Coles", coles_data), ("Aldi", aldi_data)]:
        if not data: continue
        print(f"  {s_name}: {len(data)} products.")
        new, up, hist = build_upsert_data(data, s_name, existing)
        sheets_helper.batch_upsert(worksheet, s_name, new, up, hist)

    print("\n" + "=" * 60)
    print("BEST SELLERS SYNC COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
