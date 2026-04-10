import time
import requests
import urllib.parse
import sheets_helper

def upsert_to_sheets(products, store_name, existing_names, worksheet):
    created_count = 0
    updated_count = 0
    
    for product in products:
        display_name = product.get("name")
        if not display_name: continue
            
        pricing = product.get("pricing", {})
        price = pricing.get("now")
        was_price = pricing.get("was")
        is_in_stock = product.get("availability") == True
        
        image_url = None
        image_uris = product.get("imageUris", [])
        if image_uris and isinstance(image_uris, list) and len(image_uris) > 0:
            image_url = image_uris[0].get("url")

        if display_name in existing_names:
            if price is not None and price > 0:
                success = sheets_helper.update_listing_price(worksheet, display_name, price)
                if success:
                    updated_count += 1
        else:
            row = [
                "", # Listing_ID
                display_name,
                store_name,
                price if price else "",
                was_price if was_price else "",
                bool(is_in_stock),
                image_url if image_url else ""
            ]
            worksheet.append_row(row)
            existing_names.add(display_name)
            created_count += 1

        time.sleep(1.2) # Throttle Google API

    return created_count, updated_count

def main():
    print("Initializing Coles Google Sheets connection...")
    worksheet = sheets_helper.get_listings_worksheet()

    search_terms = [
        "milk", "bread", "eggs", "butter", "cheese", "yoghurt", 
        "chicken breast", "beef mince", "rice", "pasta", "cereal", 
        "orange juice", "chips", "chocolate", "coffee", "tea", 
        "toilet paper", "dishwashing liquid"
    ]

    headers = {
        "ocp-apim-subscription-key": "eae83861d1cd4de6bb9cd8a2cd6f041e",
        "x-api-version": "2",
        "dsch-channel": "coles.online.1site.desktop",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.coles.com.au",
        "Origin": "https://www.coles.com.au"
    }

    print("Fetching existing Coles listings from Google Sheets...")
    all_records = worksheet.get_all_records()
    existing_names = {r.get('Product_name') for r in all_records if r.get('Store') == 'Coles' and r.get('Product_name')}
    print(f"Found {len(existing_names)} existing Coles listings")

    all_products = []
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        print(f"\n=> Searching Coles for '{term}'...")
        
        start = 0
        url = f"https://www.coles.com.au/api/bff/products/search?storeId=7674&start={start}&sortBy=salesDescending&searchTerm={encoded_term}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching data for '{term}': {e}")
            continue

        products = []
        if "results" in data:
            products = data["results"]
        elif "products" in data:
            products = data["products"]
        elif "pageProps" in data and "searchResults" in data["pageProps"]:
            products = data["pageProps"]["searchResults"]

        all_products.extend(products)
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Total products collected: {len(all_products)}")
    
    print("\nUpserting to Google Sheets...")
    created, updated = upsert_to_sheets(all_products, "Coles", existing_names, worksheet)
    
    print(f"\n{'='*50}")
    print("COMPLETE!")
    print(f"Created: {created} new listings")
    print(f"Updated: {updated} existing listings")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
