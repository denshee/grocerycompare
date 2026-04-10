import os
import time
import requests
import urllib.parse
import sheets_helper
from dotenv import load_dotenv

load_dotenv()

# --- Algolia credentials for Chemist Warehouse ---
ALGOLIA_URL    = 'https://42np1v2i98-dsn.algolia.net/1/indexes/*/queries'
ALGOLIA_API_KEY = '3ce54af79eae81a18144a7aa7ee10ec2'
ALGOLIA_APP_ID  = '42NP1V2I98'
INDEX_NAME      = 'prod_cwr-cw-au_products_en'

# --- Search configuration ---
# For test mode: 1 page per term, 100 hits/page
# For full catalogue: increase PAGES_PER_TERM
PAGES_PER_TERM = 1
HITS_PER_PAGE  = 100

SEARCH_TERMS = [
    'vitamins', 'pain relief', 'cold flu', 'bandages', 'sunscreen',
    'shampoo', 'conditioner', 'moisturiser', 'deodorant', 'toothpaste',
    'nappies', 'baby formula', 'protein powder', 'fish oil', 'probiotics'
]


def search_chemist_warehouse(query, page=0, hits_per_page=100):
    """Search Chemist Warehouse via Algolia API. Returns list of hits."""
    headers = {
        'x-algolia-api-key': ALGOLIA_API_KEY,
        'x-algolia-application-id': ALGOLIA_APP_ID,
        'Content-Type': 'application/json'
    }
    params_str = (
        f"query={urllib.parse.quote(query)}"
        f"&page={page}&hitsPerPage={hits_per_page}&clickAnalytics=true"
    )
    payload = {"requests": [{"indexName": INDEX_NAME, "params": params_str}]}
    response = requests.post(ALGOLIA_URL, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    result = response.json()
    return result.get('results', [{}])[0].get('hits', [])


def clean_price(price_value):
    """Normalise price string/number to float."""
    if not price_value:
        return None
    if isinstance(price_value, (int, float)):
        return float(price_value)
    cleaned = str(price_value).replace('$', '').replace(',', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_cw_products(search_terms, pages_per_term=1, hits_per_page=100):
    """Scrape all products from Chemist Warehouse Algolia API.

    Returns a list of raw hit dicts.
    Sleeps briefly between HTTP requests only.
    """
    all_products = []

    for term in search_terms:
        for page in range(pages_per_term):
            print(f"  Fetching CW '{term}' page {page + 1}...")
            try:
                hits = search_chemist_warehouse(term, page=page, hits_per_page=hits_per_page)
                if not hits:
                    break  # No more results for this term
                all_products.extend(hits)
            except Exception as e:
                print(f"  Error fetching '{term}' page {page + 1}: {e}")
                break
            time.sleep(0.5)  # Polite delay between HTTP requests only

    return all_products


def build_upsert_data(products, store_name, existing):
    """Classify scraped Chemist Warehouse products into new rows vs price updates.

    Args:
        products: list of raw Algolia hit dicts
        store_name: str
        existing: dict from sheets_helper.load_existing_listings()

    Returns:
        new_rows: list of row lists ready to append
        price_updates: list of (row_number, price) tuples
    """
    new_rows = []
    price_updates = []
    seen_names = set()

    for product in products:
        # Extract product name (handle multilingual dict format)
        name = product.get('name') or product.get('title') or product.get('product_name')
        if isinstance(name, dict):
            name = name.get('en') or (list(name.values())[0] if name else None)
        if not name:
            continue
        name = str(name).strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        # Extract prices (Algolia stores cents in AUD.min)
        current_price = None
        regular_price = None
        aud = product.get('prices', {}).get('AUD', {})
        if aud:
            raw_min = aud.get('min')
            if raw_min:
                current_price = raw_min / 100.0
            vals = aud.get('priceValues', [])
            if vals:
                rrp_cents = vals[0].get('customFields', {}).get('rrp', {}).get('centAmount')
                if rrp_cents:
                    regular_price = rrp_cents / 100.0

        # Fallback: some hits use top-level price field
        if current_price is None:
            current_price = clean_price(product.get('price'))

        # Extract image
        images = product.get('images', [])
        image_url = images[0] if images else ""

        key = (name, store_name)
        if key in existing:
            if current_price is not None and current_price > 0:
                price_updates.append((existing[key], current_price))
        else:
            new_rows.append([
                "",            # Listing_ID
                name,
                store_name,
                current_price if current_price is not None else "",
                regular_price if regular_price is not None else "",
                True,          # In_stock assumed (CW doesn't reliably return stock)
                image_url
            ])

    return new_rows, price_updates


def main():
    print("=" * 50)
    print("Chemist Warehouse → Google Sheets")
    print("=" * 50)

    print("\n[1/4] Connecting to Google Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()

    print("\n[2/4] Loading existing sheet data...")
    existing = sheets_helper.load_existing_listings(worksheet)

    print(f"\n[3/4] Scraping Chemist Warehouse ({len(SEARCH_TERMS)} terms × {PAGES_PER_TERM} page(s))...")
    products = fetch_cw_products(SEARCH_TERMS, PAGES_PER_TERM, HITS_PER_PAGE)
    print(f"  Total raw products fetched: {len(products)}")

    print("\n[4/4] Classifying and writing to Google Sheets (batch)...")
    new_rows, price_updates = build_upsert_data(products, "Chemist Warehouse", existing)
    print(f"  New rows to append : {len(new_rows)}")
    print(f"  Price updates      : {len(price_updates)}")

    created, updated = sheets_helper.batch_upsert(worksheet, "Chemist Warehouse", new_rows, price_updates)

    print(f"\n{'=' * 50}")
    print("CHEMIST WAREHOUSE COMPLETE")
    print(f"  Created : {created} new listings")
    print(f"  Updated : {updated} existing prices")
    print(f"{'=' * 50}")


if __name__ == '__main__':
    main()
