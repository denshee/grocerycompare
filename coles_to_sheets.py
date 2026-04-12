import time
import requests
import urllib.parse
from datetime import datetime
import sheets_helper

# --- Search configuration ---
PAGES_PER_TERM = 1
PAGE_SIZE = 20

SEARCH_TERMS = [
    "milk", "bread", "eggs", "butter", "cheese", "yoghurt",
    "chicken breast", "beef mince", "rice", "pasta", "cereal",
    "orange juice", "chips", "chocolate", "coffee", "tea",
    "toilet paper", "dishwashing liquid"
]

HEADERS = {
    "ocp-apim-subscription-key": "eae83861d1cd4de6bb9cd8a2cd6f041e",
    "x-api-version": "2",
    "dsch-channel": "coles.online.1site.desktop",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.coles.com.au",
    "Origin": "https://www.coles.com.au"
}


def fetch_coles_products(search_terms, pages_per_term=1, page_size=20):
    """Scrape all products from Coles API."""
    all_products = []

    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        for page in range(pages_per_term):
            start = page * page_size
            url = (
                f"https://www.coles.com.au/api/bff/products/search"
                f"?storeId=7674&start={start}&sortBy=salesDescending&searchTerm={encoded_term}"
            )
            print(f"  Fetching Coles '{term}' page {page + 1}...")
            try:
                response = requests.get(url, headers=HEADERS, timeout=15)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                print(f"  Error fetching '{term}' page {page + 1}: {e}")
                break

            products = []
            if "results" in data:
                products = data["results"]
            elif "products" in data:
                products = data["products"]
            elif "pageProps" in data and "searchResults" in data["pageProps"]:
                products = data["pageProps"]["searchResults"]

            if not products:
                break 

            all_products.extend(products)
            time.sleep(0.5)

    return all_products


def build_upsert_data(products, store_name, existing):
    """Classify scraped products into new rows, price updates, and history logs."""
    new_rows = []
    price_updates = []
    history_rows = []
    seen_names = set()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for product in products:
        name = (product.get("name") or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        pricing   = product.get("pricing", {})
        price     = pricing.get("now")
        was_price = pricing.get("was")
        in_stock  = product.get("availability") is True

        image_url = ""
        image_uris = product.get("imageUris", [])
        if isinstance(image_uris, list) and image_uris:
            image_url = image_uris[0].get("url", "")

        key = (name, store_name)
        if key in existing:
            old_data = existing[key]
            # Compare prices
            price_changed = (price is not None and price != old_data['price'])
            reg_price_changed = (was_price is not None and was_price != old_data['reg_price'])

            if price_changed or reg_price_changed:
                print(f"  [Price Change] {name}: ${old_data['price']} -> ${price}")
                price_updates.append((old_data['row'], price, was_price))
                history_rows.append([now_str, name, store_name, price, was_price or ""])
        else:
            new_rows.append([
                "",           # Listing_ID
                name,
                store_name,
                price if price is not None else "",
                was_price if was_price is not None else "",
                bool(in_stock),
                image_url
            ])
            history_rows.append([now_str, name, store_name, price if price is not None else "", was_price or ""])

    return new_rows, price_updates, history_rows


def main():
    print("=" * 50)
    print("Coles → Google Sheets (+ Price History)")
    print("=" * 50)

    print("\n[1/4] Connecting to Google Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()

    print("\n[2/4] Loading existing sheet data...")
    existing = sheets_helper.load_existing_listings(worksheet)

    print(f"\n[3/4] Scraping Coles ({len(SEARCH_TERMS)} terms)...")
    products = fetch_coles_products(SEARCH_TERMS, PAGES_PER_TERM, PAGE_SIZE)
    print(f"  Total raw products fetched: {len(products)}")

    print("\n[4/4] Classifying and writing to Google Sheets (batch)...")
    new_rows, price_updates, history_rows = build_upsert_data(products, "Coles", existing)
    
    print(f"  New rows to append   : {len(new_rows)}")
    print(f"  Price updates        : {len(price_updates)}")
    print(f"  History logs to append: {len(history_rows)}")

    created, updated = sheets_helper.batch_upsert(
        worksheet, "Coles", new_rows, price_updates, history_rows
    )

    print(f"\n{'=' * 50}")
    print("COLES COMPLETE")
    print(f"  Created : {created} new listings")
    print(f"  Updated : {updated} existing prices")
    print(f"  Logged  : {len(history_rows)} history entries")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
