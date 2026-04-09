import os
import re
import time
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv("grocerycompare/.env")

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appryWRqjOFw4EajV")

# DRY RUN MODE - Set to False to actually write to Airtable
DRY_RUN = False

def normalize_name(name):
    # Basic normalization: lower case, remove extra spaces
    name = name.lower().strip()
    return name

def extract_size(name):
    # Look for patterns like 2L, 700g, 1.5kg, 500ml, etc.
    match = re.search(r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pack|pk|ea|s))', name, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""

def extract_category(name):
    # Very basic category extraction based on keywords
    name_lower = name.lower()
    if 'milk' in name_lower or 'cheese' in name_lower or 'yoghurt' in name_lower or 'butter' in name_lower:
        return 'Dairy'
    elif 'bread' in name_lower or 'loaf' in name_lower or 'rolls' in name_lower:
        return 'Bakery'
    elif 'apple' in name_lower or 'banana' in name_lower or 'carrot' in name_lower or 'tomato' in name_lower:
        return 'Fruit & Veg'
    elif 'chicken' in name_lower or 'beef' in name_lower or 'lamb' in name_lower or 'pork' in name_lower:
        return 'Meat'
    return 'Uncategorized'

def main():
    print(f"Starting Migration Script (DRY_RUN: {DRY_RUN})")
    if not AIRTABLE_TOKEN:
        print("Error: AIRTABLE_TOKEN not found.")
        return

    api = Api(AIRTABLE_TOKEN)
    listings_table = api.table(BASE_ID, 'Listings')
    
    try:
        if not DRY_RUN:
            products_table = api.table(BASE_ID, 'Products')
    except Exception as e:
        print(f"Error accessing tables: {e}")
        return

    print("Fetching all records from Listings table...")
    try:
        all_listings = listings_table.all()
        print(f"Fetched {len(all_listings)} listings.")
    except Exception as e:
        print(f"Error fetching listings: {e}")
        return

    # Group listings by normalized name
    grouped_products = {}
    valid_records = 0
    for record in all_listings:
        fields = record.get('fields', {})
        listing_id = record.get('id')
        name = fields.get('Listing name', '')
        if not name:
            continue
        
        valid_records += 1
        norm_name = normalize_name(name)
        
        if norm_name not in grouped_products:
            grouped_products[norm_name] = {
                'original_names': set(),
                'size': extract_size(name),
                'category': extract_category(name) or fields.get('Category', 'Uncategorized'),
                'image_url': fields.get('Image URL', ''),
                'listing_ids': []
            }
        
        grouped_products[norm_name]['original_names'].add(name)
        grouped_products[norm_name]['listing_ids'].append(listing_id)
        
        # Grab first available image if we don't have one yet
        if not grouped_products[norm_name]['image_url'] and fields.get('Image URL'):
            grouped_products[norm_name]['image_url'] = fields.get('Image URL')

    total_products = len(grouped_products)
    print(f"\nGrouped {valid_records} valid records into {total_products} unique products.")
    
    if DRY_RUN:
        print("\n--- DRY RUN PREVIEW (First 5 Products) ---")
        count = 0
        for norm_name, data in grouped_products.items():
            if count >= 5:
                break
            print(f"\nProduct: {list(data['original_names'])[0]}")
            print(f"  Normalized: {norm_name}")
            print(f"  Category: {data['category']}")
            print(f"  Size: {data['size']}")
            print(f"  Image: {'Yes' if data['image_url'] else 'No'} ({data['image_url'][:30]}...)")
            print(f"  Linked Listings: {len(data['listing_ids'])}")
            count += 1
            
        print(f"\nWould create {total_products} products and link to existing {valid_records} listings.")
        return

    # Live Run Logic (skipped during dry run)
    print("\n--- LIVE RUN ---")
    created_count = 0
    for norm_name, data in grouped_products.items():
        # 1. Create Product
        primary_name = list(data['original_names'])[0] # Use one of the original names for display
        new_product = {
            "Product name": primary_name,
            "Category": data['category'],
            "Weight / volume": data['size'],
            "Primary_Image": data['image_url']
        }
        
        try:
            created_record = products_table.create(new_product)
            product_id = created_record['id']
            
            # 2. Link Listings to Product
            # Requires a field in Listings called "Product" that links to Products table
            for listing_id in data['listing_ids']:
                listings_table.update(listing_id, {"Product": [product_id]})
                
            created_count += 1
            print(f"Created product {created_count} of {total_products}, linked {len(data['listing_ids'])} listings")
            time.sleep(0.2) # Rate limit
            
        except Exception as e:
            print(f"Error processing product '{norm_name}': {e}")
            
    print(f"\nFinished! Created {created_count} products.")

if __name__ == "__main__":
    main()
