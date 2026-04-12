"""
deduplicate_listings.py
-----------------------
Finds and removes duplicate product entries for the same store.
Prioritizes keeping entries with Image URLs.
"""

import sheets_helper

def deduplicate():
    print("🚀 Starting Database Deduplication...")
    ws = sheets_helper.get_listings_worksheet()
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("Sheet empty.")
        return

    header = rows[0]
    data = rows[1:]

    # 1: Name, 2: Store, 6: Image_URL
    NAME_IDX = 1
    STORE_IDX = 2
    IMAGE_IDX = 6

    seen = {} # {(name, store): row_index}
    to_delete = [] # list of row numbers (1-indexed)

    # We iterate backwards to make deletion easier (no, we'll just batch delete)
    # Actually gspread batch delete is complex, we'll just rewrite the whole sheet.
    
    unique_data = {} # {(name, store): row_data}

    for r in data:
        name = r[NAME_IDX].strip()
        store = r[STORE_IDX].strip()
        image = r[IMAGE_IDX].strip()
        
        key = (name, store)
        if key not in unique_data:
            unique_data[key] = r
        else:
            # If current has image but previous didn't, replace
            if image and not unique_data[key][IMAGE_IDX]:
                unique_data[key] = r

    final_rows = [header] + list(unique_data.values())
    
    # Sort for tidiness
    final_rows[1:] = sorted(final_rows[1:], key=lambda x: (x[STORE_IDX], x[NAME_IDX]))

    print(f"Original: {len(rows)} | After Deduplication: {len(final_rows)}")
    
    # Overwrite sheet
    # Warning: this clears formatting. But it's the safest way.
    ws.clear()
    ws.update('A1', final_rows)
    print("DONE.")

if __name__ == "__main__":
    deduplicate()
