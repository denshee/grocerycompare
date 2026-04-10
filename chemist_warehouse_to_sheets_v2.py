import os
import requests
import time
from dotenv import load_dotenv
import sheets_helper

# Load environment variables
load_dotenv()

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

def clean_price(price_value):
    """Clean price value - remove $ and convert to float"""
    if not price_value:
        return None
    if isinstance(price_value, (int, float)):
        return float(price_value)
    cleaned = str(price_value).replace('$', '').replace(',', '').strip()
    try:
        return float(cleaned)
    except:
        return None

def upsert_to_sheets(products, existing_names, worksheet):
    """Upsert products to Google Sheets Listings table"""
    created_count = 0
    updated_count = 0
    
    for product in products:
        # Extract product details
        product_name = product.get('name') or product.get('title') or product.get('product_name')
        if isinstance(product_name, dict):
            product_name = product_name.get('en') or list(product_name.values())[0] if product_name else None
        if not product_name:
            continue
        
        # Extract prices safely
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
            
        # Check if product exists in our local set of Google Sheet names
        if product_name in existing_names:
            if current_price is not None and current_price > 0:
                # Update existing record's price
                success = sheets_helper.update_listing_price(worksheet, product_name, current_price)
                if success:
                    updated_count += 1
        else:
            # Create new record
            # Headers: Listing_ID | Product_name | Store | Current_price | Regular_price | In_stock | Image_URL
            row = [
                "", # Listing_ID (assuming auto-generated or intentionally blank)
                product_name,
                "Chemist Warehouse",
                current_price if current_price else "",
                regular_price if regular_price else "",
                True, # In_stock default
                image_url if image_url else ""
            ]
            worksheet.append_row(row)
            existing_names.add(product_name)
            created_count += 1
        
        # Google Sheets API has strict rate limits (60 per min per user usually), so throttle
        time.sleep(1.2)
    
    return created_count, updated_count

def main():
    print("Starting Chemist Warehouse data collection to Google Sheets...")
    print(f"Searching for {len(SEARCH_TERMS)} product categories")
    
    worksheet = sheets_helper.get_listings_worksheet()
    
    print("\nFetching existing Chemist Warehouse listings from Google Sheets...")
    all_records = worksheet.get_all_records()
    
    # Keep track of existing names to avoid duplicates
    existing_names = set()
    for record in all_records:
        if record.get('Store') == 'Chemist Warehouse' and record.get('Product_name'):
            existing_names.add(record['Product_name'])
            
    print(f"Found {len(existing_names)} existing CW listings")
    
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
        
        time.sleep(0.5)
    
    print(f"\n{'='*50}")
    print(f"Total products collected: {len(all_products)}")
    
    # Upsert to Google Sheets
    print("\nUpserting to Google Sheets...")
    created, updated = upsert_to_sheets(all_products, existing_names, worksheet)
    
    print(f"\n{'='*50}")
    print("COMPLETE!")
    print(f"Created: {created} new listings")
    print(f"Updated: {updated} existing listings")
    print(f"{'='*50}")

if __name__ == '__main__':
    main()
