import os
import requests
import time
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN')
BASE_ID = 'appryWRqjOFw4EajV'
LISTINGS_TABLE = 'Listings'

# Algolia credentials for Chemist Warehouse
ALGOLIA_URL = 'https://42np1v2i98-dsn.algolia.net/1/indexes/*/queries'
ALGOLIA_API_KEY = '3ce54af79eae81a18144a7aa7ee10ec2'
ALGOLIA_APP_ID = '42NP1V2I98'
INDEX_NAME = 'prod_cwr-cw-au_products_en'

# Search terms for common pharmacy products
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

def get_existing_listings():
    """Fetch all existing Chemist Warehouse listings from Airtable"""
    url = f'https://api.airtable.com/v0/{BASE_ID}/{LISTINGS_TABLE}'
    headers = {'Authorization': f'Bearer {AIRTABLE_TOKEN}'}
    
    all_records = []
    params = {'filterByFormula': '{Store} = "Chemist Warehouse"'}
    
    while True:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        all_records.extend(data.get('records', []))
        
        if 'offset' not in data:
            break
        params['offset'] = data['offset']
        time.sleep(0.2)
    
    return {record['fields'].get('Listing name'): record['id'] 
            for record in all_records if 'Listing name' in record['fields']}

def clean_price(price_value):
    """Clean price value - remove $ and convert to float"""
    if not price_value:
        return None
    if isinstance(price_value, (int, float)):
        return float(price_value)
    # Handle string prices like "$12.99"
    cleaned = str(price_value).replace('$', '').replace(',', '').strip()
    try:
        return float(cleaned)
    except:
        return None

def upsert_to_airtable(products, existing_listings):
    """Upsert products to Airtable Listings table"""
    url = f'https://api.airtable.com/v0/{BASE_ID}/{LISTINGS_TABLE}'
    headers = {
        'Authorization': f'Bearer {AIRTABLE_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    created_count = 0
    updated_count = 0
    
    for product in products:
        # Extract product details
        product_name = product.get('name') or product.get('title') or product.get('product_name')
        if isinstance(product_name, dict):
            product_name = product_name.get('en') or list(product_name.values())[0] if product_name else None
        if not product_name:
            continue
        
        # Extract prices safely from AUD limits dividing 'centAmount' correctly
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
                
        image_url = None
        images = product.get("images", [])
        if images and len(images) > 0:
            image_url = images[0]
            
        category = None
        try:
            lvl0 = product.get("categories", {}).get("en", {}).get("lvl0", [])
            if lvl0:
                parts = lvl0[0].split('>')
                category = parts[-1].strip() if len(parts) > 1 else parts[0].strip()
        except:
            pass
        
        # Build Airtable record - strip None/False values
        fields = {
            'Listing name': product_name,
            'Store': 'Chemist Warehouse'
        }
        
        if image_url: fields['Image URL'] = image_url
        if category: fields['Category'] = category
        
        # Only add price fields if they have valid values
        if current_price is not None and current_price > 0:
            fields['Current price'] = current_price
        
        if regular_price is not None and regular_price > 0:
            fields['Regular price'] = regular_price
        
        # Check if product exists
        if product_name in existing_listings:
            # Update existing record
            record_id = existing_listings[product_name]
            update_url = f'{url}/{record_id}'
            response = requests.patch(update_url, json={'fields': fields}, headers=headers)
            response.raise_for_status()
            updated_count += 1
        else:
            # Create new record
            response = requests.post(url, json={'fields': fields}, headers=headers)
            response.raise_for_status()
            created_count += 1
        
        time.sleep(0.2)  # Respect Airtable rate limit
    
    return created_count, updated_count

def main():
    print("Starting Chemist Warehouse data collection...")
    print(f"Searching for {len(SEARCH_TERMS)} product categories")
    
    # Get existing listings
    print("\nFetching existing Chemist Warehouse listings from Airtable...")
    existing_listings = get_existing_listings()
    print(f"Found {len(existing_listings)} existing listings")
    
    # Collect all products
    all_products = []
    
    for term in SEARCH_TERMS:
        print(f"\nSearching: {term}")
        try:
            result = search_chemist_warehouse(term)
            hits = result.get('results', [{}])[0].get('hits', [])
            print(f"  Found {len(hits)} products")
            all_products.extend(hits)
        except Exception as e:
            print(f"  Error searching '{term}': {e}")
        
        time.sleep(0.5)  # Be nice to Algolia
    
    print(f"\n{'='*50}")
    print(f"Total products collected: {len(all_products)}")
    
    # Upsert to Airtable
    print("\nUpserting to Airtable...")
    created, updated = upsert_to_airtable(all_products, existing_listings)
    
    print(f"\n{'='*50}")
    print("COMPLETE!")
    print(f"Created: {created} new listings")
    print(f"Updated: {updated} existing listings")
    print(f"{'='*50}")

if __name__ == '__main__':
    main()
