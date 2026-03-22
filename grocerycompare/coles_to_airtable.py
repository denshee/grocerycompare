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
        "ocp-apim-subscription-key": "eae83861d1cd4de6bb9cd8a2cd6f041e",
        "x-api-version": "2",
        "dsch-channel": "coles.online.1site.desktop",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.coles.com.au",
        "Origin": "https://www.coles.com.au"
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
        print(f"\n=> Searching Coles for '{term}'...")
        
        start = 0
        url = f"https://www.coles.com.au/api/bff/products/search?storeId=7674&start={start}&sortBy=salesDescending&searchTerm={encoded_term}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching data for '{term}' from Coles: {e}")
            continue

        products = []
        if "results" in data:
            products = data["results"]
        elif "products" in data:
            products = data["products"]
        elif "pageProps" in data and "searchResults" in data["pageProps"]:
            products = data["pageProps"]["searchResults"]

        if not products:
            print(f"API Response did not contain any products for term '{term}'")
            continue

        for product in products:
            display_name = product.get("name")
            if not display_name:
                continue
                
            pricing = product.get("pricing", {})
            price = pricing.get("now")
            was_price = pricing.get("was")
            
            is_on_special = (pricing.get("onlineSpecial") == True) or (pricing.get("promotionType") == "SPECIAL")
            is_in_stock = product.get("availability") == True
            
            image_url = None
            image_uris = product.get("imageUris", [])
            if image_uris and isinstance(image_uris, list) and len(image_uris) > 0:
                image_url = image_uris[0].get("url")

            raw_fields = {
                "Listing name": display_name,
                "Store": "Coles",
                "Current price": price,
                "On special": is_on_special,
                "In stock": is_in_stock,
                "Image URL": image_url
            }

            if was_price and was_price != 0:
                raw_fields["Regular price"] = was_price

            # Prune any fields where the value is exactly False, "false" string, or None
            fields = {}
            for k, v in raw_fields.items():
                if v in [False, "False", "false", None]:
                    continue
                fields[k] = v

            key = (display_name, "Coles")
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
            
            time.sleep(0.2)
            
        print(f"Finished processing term: {term}")

if __name__ == "__main__":
    main()
