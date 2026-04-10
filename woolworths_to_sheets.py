import time
import requests
import urllib.parse
import sheets_helper

# --- Search configuration ---
# For test mode: 1 page per term (~36 products/term)
# For full catalogue: increase PAGES_PER_TERM (each page = up to 36 products)
PAGES_PER_TERM = 1
PAGE_SIZE = 36

SEARCH_TERMS = [
    "milk", "bread", "eggs", "butter", "cheese", "yoghurt",
    "chicken breast", "beef mince", "rice", "pasta", "cereal",
    "orange juice", "chips", "chocolate", "coffee", "tea",
    "toilet paper", "dishwashing liquid"
]


def fetch_woolworths_products(search_terms, pages_per_term=1, page_size=36):
    """Scrape all products from Woolworths API.

    Returns a list of raw product dicts.
    Sleeps briefly between HTTP requests only (not between sheet writes).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.woolworths.com.au/"
    }

    all_products = []

    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        for page in range(1, pages_per_term + 1):
            url = (
                f"https://www.woolworths.com.au/apis/ui/Search/products"
                f"?searchTerm={encoded_term}&pageNumber={page}&pageSize={page_size}"
            )
            print(f"  Fetching Woolworths '{term}' page {page}...")
            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                print(f"  Error fetching '{term}' page {page}: {e}")
                continue

            bundles = data.get("Products", [])
            if not bundles:
                break  # No more results for this term

            for bundle in bundles:
                all_products.extend(bundle.get("Products", []))

            time.sleep(0.5)  # Polite delay between HTTP requests only

    return all_products


def build_upsert_data(products, store_name, existing):
    """Classify scraped products into new rows vs price updates.

    Args:
        products: list of raw product dicts from the Woolworths API
        store_name: str
        existing: dict from sheets_helper.load_existing_listings()

    Returns:
        new_rows: list of row lists ready to append
        price_updates: list of (row_number, price) tuples
        seen_names: set of product names processed (for dedup within batch)
    """
    new_rows = []
    price_updates = []
    seen_names = set()

    for product in products:
        if not product.get("IsAvailable"):
            continue

        name = product.get("DisplayName", "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        price     = product.get("Price")
        was_price = product.get("WasPrice")
        in_stock  = product.get("IsInStock")
        image_url = product.get("MediumImageFile", "")

        key = (name, store_name)
        if key in existing:
            # Existing product — queue a price update
            if price is not None and price > 0:
                price_updates.append((existing[key], price))
        else:
            # New product — queue a full row append
            new_rows.append([
                "",           # Listing_ID
                name,
                store_name,
                price if price is not None else "",
                was_price if was_price is not None else "",
                bool(in_stock),
                image_url or ""
            ])

    return new_rows, price_updates


def main():
    print("=" * 50)
    print("Woolworths → Google Sheets")
    print("=" * 50)

    print("\n[1/3] Connecting to Google Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()

    print("\n[2/3] Loading existing sheet data...")
    existing = sheets_helper.load_existing_listings(worksheet)

    print(f"\n[3/3] Scraping Woolworths ({len(SEARCH_TERMS)} terms × {PAGES_PER_TERM} page(s))...")
    products = fetch_woolworths_products(SEARCH_TERMS, PAGES_PER_TERM, PAGE_SIZE)
    print(f"  Total raw products fetched: {len(products)}")

    print("\n[4/4] Classifying and writing to Google Sheets (batch)...")
    new_rows, price_updates = build_upsert_data(products, "Woolworths", existing)
    print(f"  New rows to append : {len(new_rows)}")
    print(f"  Price updates      : {len(price_updates)}")

    created, updated = sheets_helper.batch_upsert(worksheet, "Woolworths", new_rows, price_updates)

    print(f"\n{'=' * 50}")
    print("WOOLWORTHS COMPLETE")
    print(f"  Created : {created} new listings")
    print(f"  Updated : {updated} existing prices")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
