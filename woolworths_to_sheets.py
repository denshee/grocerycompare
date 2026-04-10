import time
import requests
import urllib.parse
import sheets_helper

def upsert_to_sheets(products, store_name, existing_names, worksheet):
    created_count = 0
    updated_count = 0
    
    for product in products:
        is_available = product.get("IsAvailable")
        if not is_available: continue
        
        display_name = product.get("DisplayName", "")
        if not display_name: continue
        
        price = product.get("Price")
        was_price = product.get("WasPrice")
        is_in_stock = product.get("IsInStock")
        image_url = product.get("MediumImageFile")

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

        time.sleep(1.2) # Avoid aggressive Google rate limits

    return created_count, updated_count

def main():
    print("Initializing Woolworths Google Sheets connection...")
    worksheet = sheets_helper.get_listings_worksheet()

    search_terms = [
        "milk", "bread", "eggs", "butter", "cheese", "yoghurt", 
        "chicken breast", "beef mince", "rice", "pasta", "cereal", 
        "orange juice", "chips", "chocolate", "coffee", "tea", 
        "toilet paper", "dishwashing liquid"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.woolworths.com.au/"
    }

    print("Fetching existing Woolworths listings from Google Sheets...")
    all_records = worksheet.get_all_records()
    existing_names = {r.get('Product_name') for r in all_records if r.get('Store') == 'Woolworths' and r.get('Product_name')}
    print(f"Found {len(existing_names)} existing Woolworths listings")

    all_products = []
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        print(f"\n=> Searching Woolworths for '{term}'...")
        url = f"https://www.woolworths.com.au/apis/ui/Search/products?searchTerm={encoded_term}&pageNumber=1&pageSize=36"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching data for '{term}': {e}")
            continue

        bundles = data.get("Products", [])
        if not bundles:
            continue

        for bundle in bundles:
            products = bundle.get("Products", [])
            all_products.extend(products)
            
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Total products collected: {len(all_products)}")
    
    print("\nUpserting to Google Sheets...")
    created, updated = upsert_to_sheets(all_products, "Woolworths", existing_names, worksheet)
    
    print(f"\n{'='*50}")
    print("COMPLETE!")
    print(f"Created: {created} new listings")
    print(f"Updated: {updated} existing listings")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
