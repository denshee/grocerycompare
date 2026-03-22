import os
import time
import requests
import urllib.parse
from dotenv import load_dotenv
from pyairtable import Api

def main():
    load_dotenv()

    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    if not airtable_token or not base_id:
        print("Missing AIRTABLE_TOKEN or AIRTABLE_BASE_ID in .env file.")
        return

    print("Initializing Airtable connection...")
    api = Api(airtable_token)
    table = api.table(base_id, "Listings")

    search_terms = [
        "milk", "bread", "eggs", "butter", "cheese", "yoghurt", 
        "chicken breast", "beef mince", "rice", "pasta", "cereal", 
        "orange juice", "chips", "chocolate", "coffee", "tea", 
        "toilet paper", "dishwashing liquid"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.woolworths.com.au/"
    }

    print("Fetching existing listings from Airtable to perform matching...")
    try:
        existing_records = table.all()
    except Exception as e:
        print(f"Error fetching from Airtable: {e}")
        return

    existing_map = {}
    for r in existing_records:
        fields = r.get("fields", {})
        key = (fields.get("Listing name"), fields.get("Store"))
        existing_map[key] = r["id"]

    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        print(f"\n=> Searching Woolworths for '{term}' (encoded: {encoded_term})...")
        url = f"https://www.woolworths.com.au/apis/ui/Search/products?searchTerm={encoded_term}&pageNumber=1&pageSize=36"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching data for '{term}' from Woolworths: {e}")
            continue

        bundles = data.get("Products", [])
        if not bundles:
            print(f"API Response did not contain any 'Products' for term '{term}'")
            continue

        for bundle in bundles:
            products = bundle.get("Products", [])
            for product in products:
                is_available = product.get("IsAvailable")
                if not is_available:
                    continue  # Skip unavailable products
                
                display_name = product.get("DisplayName", "")
                price = product.get("Price")
                was_price = product.get("WasPrice")
                is_on_special = product.get("IsOnSpecial")
                is_in_stock = product.get("IsInStock")
                image_url = product.get("MediumImageFile")
                
                # Extract nested CentreTag fields safely
                centre_tag = product.get("CentreTag") or {}
                member_price_data = centre_tag.get("MemberPriceData") or {}
                multibuy_data = centre_tag.get("MultibuyData") or {}
                
                member_price = member_price_data.get("MemberPrice")
                minimum_quantity = multibuy_data.get("MinimumQuantity")
                multi_buy_price = multibuy_data.get("NewPrice")

                # Prepare Airtable payload mapped fields
                raw_fields = {
                    "Listing name": display_name,
                    "Store": "Woolworths",
                    "Current price": price,
                    "Regular price": was_price,
                    "On special": is_on_special,
                    "In stock": is_in_stock,
                    "Image URL": image_url
                }

                if member_price is not None:
                    raw_fields["Member price"] = member_price
                if minimum_quantity is not None:
                    raw_fields["Multi-buy qty"] = minimum_quantity
                if multi_buy_price is not None:
                    raw_fields["Multi-buy price"] = multi_buy_price

                # Prune any fields where the value is exactly False or None
                fields = {k: v for k, v in raw_fields.items() if v is not False and v is not None}

                # Upsert process: Check if it exists in our map
                key = (display_name, "Woolworths")
                try:
                    record_id = existing_map.get(key)
                    if record_id:
                        table.update(record_id, fields)
                        print(f"  [Updated] {display_name}")
                    else:
                        new_record = table.create(fields)
                        existing_map[key] = new_record["id"]
                        print(f"  [Created] {display_name}")
                except Exception as e:
                    print(f"  [Error] Failed to push '{display_name}' to Airtable: {e}")
                
                # Guarantee a 0.2 second delay between every Airtable request
                time.sleep(0.2)
                
        print(f"Finished processing term: {term}")

if __name__ == "__main__":
    main()
