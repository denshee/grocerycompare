"""
validate_listings.py
--------------------
Checks each listing for mandatory fields and valid values.
"""

import sheets_helper

def validate():
    print("🚦 Starting Data Validation Check...")
    ws = sheets_helper.get_listings_worksheet()
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("Empty sheet.")
        return

    header = rows[0]
    data = rows[1:]

    # Indices
    # 0: ID, 1: Name, 2: Store, 3: Price, 4: Regular_price, 5: In_stock, 6: Image_URL
    NAME_IDX = 1
    STORE_IDX = 2
    PRICE_IDX = 3
    IN_STOCK_IDX = 5
    IMAGE_IDX = 6

    invalid_indices = []
    
    print(f"Validating {len(data)} listings...")
    
    for i, r in enumerate(data):
        row_num = i + 2 # 1-indexed + header
        errors = []
        
        # 1. Product Name
        if not r[NAME_IDX].strip():
            errors.append("Missing Product Name")
            
        # 2. Store
        valid_stores = ["Woolworths", "Coles", "Aldi"]
        if r[STORE_IDX] not in valid_stores:
            errors.append(f"Invalid Store: {r[STORE_IDX]}")
            
        # 3. Price
        try:
            price = float(r[PRICE_IDX])
            if price <= 0:
                errors.append(f"Invalid Price: {price}")
        except:
            errors.append(f"Non-numeric Price: {r[PRICE_IDX]}")
            
        # 4. Image URL
        if not r[IMAGE_IDX].startswith("http"):
            errors.append("Invalid Image URL")
            
        # 5. In Stock (default to TRUE)
        if not r[IN_STOCK_IDX]:
            # This is an auto-fixable one
            pass

        if errors:
            print(f"  Row {row_num} [{r[STORE_IDX]} - {r[NAME_IDX][:20]}...]: {', '.join(errors)}")
            invalid_indices.append(i)

    print("\n" + "="*40)
    print("DATA VALIDATION SUMMARY")
    print("="*40)
    print(f"Total Listings:  {len(data)}")
    print(f"Valid Listings:  {len(data) - len(invalid_indices)}")
    print(f"Flagged Errors:  {len(invalid_indices)}")
    
    if invalid_indices:
        print("\n[ACTION REQUIRED] Please clean up flagged rows or run a full sync.")

if __name__ == "__main__":
    validate()
