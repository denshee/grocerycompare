import os
import requests
import time
from datetime import datetime
import sheets_helper

# Algolia credentials for Chemist Warehouse
ALGOLIA_URL = 'https://42np1v2i98-dsn.algolia.net/1/indexes/*/queries'
ALGOLIA_API_KEY = '3ce54af79eae81a18144a7aa7ee10ec2'
ALGOLIA_APP_ID = '42NP1V2I98'
INDEX_NAME = 'prod_cwr-cw-au_products_en'

STORE_NAME = 'Chemist Warehouse'

SEARCH_TERMS = [
    'vitamins', 'pain relief', 'cold flu', 'bandages', 'sunscreen',
    'shampoo', 'conditioner', 'moisturiser', 'deodorant', 'toothpaste',
    'nappies', 'baby formula', 'protein powder', 'fish oil', 'probiotics'
]

def search_chemist_warehouse(query, page=0, hits_per_page=100):
    """Search Chemist Warehouse via Algolia API"""
    headers = {
        'x-algolia-api-key': ALGOLIA_API_KEY,
        'x-algolia-application-id': ALGOLIA_APP_ID,
        'Content-Type': 'application/json'
    }
    
    import urllib.parse
    params_str = f"query={urllib.parse.quote(query)}&page={page}&hitsPerPage={hits_per_page}&clickAnalytics=true"
    
    payload = {
        "requests": [{
            "indexName": INDEX_NAME,
            "params": params_str
        }]
    }
    
    response = requests.post(ALGOLIA_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def build_upsert_data(products, existing):
    """Classify products for Google Sheets."""
    new_rows = []
    price_updates = []
    history_rows = []
    seen_names = set()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for product in products:
        # Extract name
        name = product.get('name') or product.get('title') or product.get('product_name')
        if isinstance(name, dict):
            name = name.get('en') or list(name.values())[0] if name else None
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        # Extract prices
        current_price = None
        regular_price = None
        aud_prices = product.get('prices', {}).get('AUD', {})
        if aud_prices:
            c_raw = aud_prices.get('min')
            if c_raw: current_price = c_raw / 100.0
            vals = aud_prices.get('priceValues', [])
            if vals:
                rrp = vals[0].get('customFields', {}).get('rrp', {}).get('centAmount')
                if rrp: regular_price = rrp / 100.0
        
        image_url = ""
        images = product.get("images", [])
        if images:
            image_url = images[0]

        key = (name, STORE_NAME)
        if key in existing:
            old_data = existing[key]
            price_changed = (current_price is not None and current_price != old_data['price'])
            reg_price_changed = (regular_price is not None and regular_price != old_data['reg_price'])

            if price_changed or reg_price_changed:
                print(f"  [Price Change] {name}: ${old_data['price']} -> ${current_price}")
                price_updates.append((old_data['row'], current_price, regular_price))
                # Log to history
                history_rows.append([now_str, name, STORE_NAME, current_price, regular_price or ""])
        else:
            new_rows.append([
                "", name, "Pharmacy", STORE_NAME,
                current_price if current_price is not None else "",
                regular_price if regular_price is not None else "",
                "TRUE", image_url
            ])
            # User said ONLY if price changed, so we skip history for new products if we follow strictly.
            # But usually we want initial price. I'll follow strict: ONLY if changed.
    
    return new_rows, price_updates, history_rows

def main():
    print("=" * 60)
    print("Chemist Warehouse → Google Sheets (+ Price History)")
    print("=" * 60)

    print("\n[1/4] Connecting to Google Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)

    print(f"\n[2/4] Searching Chemist Warehouse ({len(SEARCH_TERMS)} terms)...")
    all_products = []
    for term in SEARCH_TERMS:
        print(f"  Searching: {term}")
        try:
            result = search_chemist_warehouse(term)
            hits = result.get('results', [{}])[0].get('hits', [])
            all_products.extend(hits)
            print(f"    Found {len(hits)} products")
        except Exception as e:
            print(f"    Error searching '{term}': {e}")
        time.sleep(0.5)

    print(f"\n[3/4] Classifying {len(all_products)} products...")
    new_rows, price_updates, history_rows = build_upsert_data(all_products, existing)

    print(f"  New rows         : {len(new_rows)}")
    print(f"  Price updates    : {len(price_updates)}")
    print(f"  History entries  : {len(history_rows)}")

    print("\n[4/4] Writing to Google Sheets...")
    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates, history_rows
    )

    print("\nCOMPLETE!")
    print(f"Created: {created} | Updated: {updated} | History: {len(history_rows)}")

if __name__ == '__main__':
    main()
