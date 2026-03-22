import os
import time
import requests
import re
from dotenv import load_dotenv
from pyairtable import Api
from apify_client import ApifyClient

# Search terms mimicking typical grocery arrays
SEARCH_TERMS = [
    'milk', 'bread', 'eggs', 'cheese', 'butter', 'chicken', 'beef', 
    'pasta', 'rice', 'cereal', 'yogurt', 'juice', 'coffee', 'tea', 'biscuits'
]

def clean_price(price_val):
    if not price_val:
        return None
    try:
        if isinstance(price_val, str):
            # Remove $ and commas cleanly preserving float limits
            cleaned = re.sub(r'[^0-9.]', '', price_val)
            if cleaned:
                return float(cleaned)
            return None
        return float(price_val)
    except (ValueError, TypeError):
        return None

def fetch_existing_listings(api, base_id, table_name="Listings"):
    table = api.table(base_id, table_name)
    print("Fetching existing Aldi listings from Airtable...")
    # Restrict fetch bounds purely to Aldi isolating overhead
    formula = "Store='Aldi'"
    records = table.all(formula=formula)
    
    existing = {}
    for r in records:
        name = r['fields'].get('Listing name')
        if name:
            existing[name] = r['id']
            
    print(f"Found {len(existing)} existing listings")
    return existing

def upsert_to_airtable(products, existing_listings):
    load_dotenv()
    
    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID") or "appryWRqjOFw4EajV"
    
    if not airtable_token or not base_id:
        print("Missing Airtable credentials")
        return 0, 0
        
    print("\nUpserting to Airtable...")
    created_count = 0
    updated_count = 0
    
    url = f"https://api.airtable.com/v0/{base_id}/Listings"
    headers = {
        "Authorization": f"Bearer {airtable_token}",
        "Content-Type": "application/json"
    }
    
    for product in products:
        # Safely extract dynamic Actor tags
        product_name = product.get('name') or product.get('title') or product.get('productName')
        if not product_name:
            continue
            
        current_price = clean_price(product.get('price') or product.get('currentPrice'))
        image_url = product.get('image') or product.get('imageUrl') or product.get('image_url')
        unit_price = product.get('unitPrice') or product.get('unit_price')
        
        fields = {
            'Listing name': product_name,
            'Store': 'Aldi'
        }
        
        if current_price is not None and current_price > 0:
            fields['Current price'] = current_price
            
        if image_url:
            fields['Image URL'] = image_url
            
        if unit_price:
            fields['Unit price'] = str(unit_price)

        # Safely strip unprocessable dict values mapping correctly against Airtable payload limits
        cleaned_fields = {k: v for k, v in fields.items() if v not in [None, False, ""]}
        
        try:
            if product_name in existing_listings:
                record_id = existing_listings[product_name]
                patch_url = f"{url}/{record_id}"
                response = requests.patch(patch_url, json={"fields": cleaned_fields}, headers=headers)
                response.raise_for_status()
                updated_count += 1
            else:
                response = requests.post(url, json={"fields": cleaned_fields}, headers=headers)
                response.raise_for_status()
                if response.ok:
                    data = response.json()
                    existing_listings[product_name] = data['id']
                    created_count += 1
                    
        except requests.exceptions.HTTPError as e:
            print(f"Airtable API Error on {product_name}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(e.response.text)
                
        # Preserve global token constraints per the 0.2s rule
        time.sleep(0.2)
        
    return created_count, updated_count

def main():
    load_dotenv()
    
    apify_token = os.environ.get("APIFY_TOKEN")
    if not apify_token:
        print("ERROR: APIFY_TOKEN not set in environment.")
        return
        
    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID") or "appryWRqjOFw4EajV"
    
    if airtable_token and base_id:
        try:
            api = Api(airtable_token)
            existing_listings = fetch_existing_listings(api, base_id)
        except Exception as e:
            print(f"Failed to fetch Airtable listings: {e}")
            existing_listings = {}
    else:
        existing_listings = {}

    client = ApifyClient(apify_token)
    all_products = []
    
    print("Starting Aldi Apify extraction...")
    for term in SEARCH_TERMS:
        print(f"\nSearching: {term}")
        
        run_input = {
            "query": term,
        }
        
        try:
            run = client.actor("stealth_mode/aldi-product-search-scraper").call(run_input=run_input)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            print(f"  Found {len(items)} products natively on Apify")
            all_products.extend(items)
            
        except Exception as e:
            print(f"  Error searching '{term}': {e}")
            
    print(f"\n==================================================")
    print(f"Total Aldi products collected: {len(all_products)}")
    
    if all_products:
        print("\n--- FIRST 3 RAW PRODUCTS & MAPPING ---")
        import json
        for i, p in enumerate(all_products[:3]):
            print(f"\nRAW {i+1}: {json.dumps(p, indent=2)}")
            p_name = p.get('name') or p.get('title') or p.get('productName')
            c_price = clean_price(p.get('price') or p.get('currentPrice'))
            print(f"  -> MAPPED NAME: {p_name}")
            print(f"  -> MAPPED PRICE: {c_price}")

        created, updated = upsert_to_airtable(all_products, existing_listings)
        print(f"\n==================================================")
        print("COMPLETE!")
        print(f"Created: {created} new listings")
        print(f"Updated: {updated} existing listings")
        print(f"==================================================")

if __name__ == "__main__":
    main()
