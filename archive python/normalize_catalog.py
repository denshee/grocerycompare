import re
import uuid
import time
from thefuzz import process
import sheets_helper

# Configuration
CONFIDENCE_THRESHOLD = 85
STORE_BRANDS = ["Woolworths", "Coles", "Aldi", "Farmdale", "Community Co", "Dairy Farmers", "Vitasoy", "Bega"]

def extract_standardized_volume(name):
    """Extract and normalize weight/volume (e.g., '1000g' -> '1kg')"""
    # Pattern for numbers followed by common units
    pattern = r'(\d+(?:\.\d+)?)\s*(l|ml|g|kg|pk|pack|units|tabs)'
    match = re.search(pattern, name, re.IGNORECASE)
    if not match:
        return "std"
    
    val = float(match.group(1))
    unit = match.group(2).lower()
    
    # Normalization logic
    if unit == 'ml' and val >= 1000:
        return f"{int(val/1000)}l"
    if unit == 'g' and val >= 1000:
        return f"{int(val/1000)}kg"
    if unit in ['pack', 'units', 'tabs']:
        unit = 'pk'
        
    # Return clean string (e.g., '2l', '500g')
    return f"{int(val) if val.is_integer() else val}{unit}"

def get_base_name(name):
    """Strip brands and volume info to get the core commodity name."""
    # 1. Remove standardized volume info
    vol = extract_standardized_volume(name)
    clean = name
    if vol != "std":
        clean = re.sub(r'\d+(?:\.\d+)?\s*(l|ml|g|kg|pk|pack|units|tabs)', '', clean, flags=re.IGNORECASE)
    
    # 2. Remove store brands
    for brand in STORE_BRANDS:
        clean = re.sub(rf'\b{brand}\b', '', clean, flags=re.IGNORECASE)
    
    # 3. Clean up punctuation and whitespace
    clean = re.sub(r'[^\w\s]', ' ', clean)
    return ' '.join(clean.split()).strip().lower()

def main():
    print("="*60)
    print("GROCERY CATALOG NORMALIZATION ENGINE")
    print("="*60)

    # 1. Fetch Listings
    print("\n[1/4] Fetching all listings from Google Sheets...")
    worksheet = sheets_helper.get_listings_worksheet()
    listings = worksheet.get_all_records()
    print(f"  Found {len(listings)} listings.")

    # 2. Bucket by Volume
    print("\n[2/4] Bucketing items by standardized volume...")
    buckets = {} # vol -> list of items
    for item in listings:
        name = item.get('Product_name') or item.get('product_name')
        if not name: continue
        
        vol = extract_standardized_volume(name)
        if vol not in buckets:
            buckets[vol] = []
        
        # Store essential data
        buckets[vol].append({
            'original_name': name,
            'base_name': get_base_name(name),
            'image': item.get('Image_URL') or item.get('image') or "",
            'category': item.get('Category') or item.get('category') or "Uncategorized"
        })

    # 3. Fuzzy Grouping within Buckets
    print("\n[3/4] Performing fuzzy grouping (Confidence: 85%)...")
    unique_products = [] # List of [UUID, Name, Category, Vol, Image]

    for vol, items in buckets.items():
        grouped_in_bucket = [] # List of {canonical_name: ..., category: ..., image: ...}
        
        for item in items:
            base = item['base_name']
            if not base: continue
            
            # Check if this base matches anything already in this bucket
            match = None
            if grouped_in_bucket:
                names_in_bucket = [g['canonical_name'] for g in grouped_in_bucket]
                match_res = process.extractOne(base, names_in_bucket)
                if match_res and match_res[1] >= CONFIDENCE_THRESHOLD:
                    match = match_res[0]

            if match:
                # Group with existing product
                continue 
            else:
                # Create new product entry
                # Use the shortest/cleanest name found so far for this group
                unique_products.append([
                    str(uuid.uuid4())[:8].upper(), # Short ID
                    base.title(),
                    item['category'],
                    vol,
                    item['image']
                ])
                grouped_in_bucket.append({'canonical_name': base})

    print(f"  Generated {len(unique_products)} unique products.")

    # 4. Write to Products Sheet
    print("\n[4/4] Updating 'Products' sheet...")
    client = sheets_helper.get_sheets_client()
    sheet = client.open_by_key(sheets_helper.SHEET_ID)
    
    try:
        products_ws = sheet.worksheet('Products')
    except:
        print("  'Products' sheet not found. Creating it...")
        products_ws = sheet.add_worksheet(title="Products", rows=1000, cols=5)
    
    # Clear and set headers
    products_ws.clear()
    headers = ["Product_ID", "Standardized_Name", "Category", "Weight_Volume", "Master_Image_URL"]
    products_ws.append_row(headers, value_input_option='USER_ENTERED')
    
    # Batch write
    if unique_products:
        products_ws.append_rows(unique_products, value_input_option='USER_ENTERED')
        print(f"  Successfully wrote {len(unique_products)} rows to 'Products'.")

    print("\nNORMALIZATION COMPLETE!")

if __name__ == '__main__':
    main()
