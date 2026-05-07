"""
cleanup_chemist_warehouse.py
----------------------------
Removes all rows from the Listings worksheet where the Store column is "Chemist Warehouse".
"""

import sheets_helper

def cleanup():
    print("🧹 Cleaning up Chemist Warehouse listings...")
    try:
        ws = sheets_helper.get_listings_worksheet()
        all_rows = ws.get_all_values()
        header = all_rows[0]
        data_rows = all_rows[1:]
        
        # Store is column C (index 2)
        filtered_rows = [header] + [row for row in data_rows if row[2] != "Chemist Warehouse"]
        
        removed_count = len(data_rows) - (len(filtered_rows) - 1)
        
        if removed_count > 0:
            ws.clear()
            ws.update('A1', filtered_rows)
            print(f"✅ Successfully removed {removed_count} Chemist Warehouse listings.")
        else:
            print("ℹ️ No Chemist Warehouse listings found.")
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

if __name__ == "__main__":
    cleanup()
