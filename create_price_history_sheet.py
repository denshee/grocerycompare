"""
create_price_history_sheet.py
----------------------------
Initialises the 'Price_History' worksheet in the GroceryCompare Google Sheet.
Sets up headers, formatting, and freezing for professional tracking.
"""

import os
import json
import gspread
import sheets_helper

def main():
    print("=" * 60)
    print("Initialising Price_History Worksheet")
    print("=" * 60)

    try:
        # 1. Connect using existing sheets_helper auth pattern
        print("[1/4] Connecting to Google Sheets...")
        client = sheets_helper.get_sheets_client()
        sheet = client.open_by_key(sheets_helper.SHEET_ID)
        
        # 2. Check if Price_History already exists
        print("[2/4] Checking for 'Price_History' worksheet...")
        worksheet = None
        try:
            worksheet = sheet.worksheet("Price_History")
            print("  ! 'Price_History' already exists. Re-initialising headers...")
        except gspread.WorksheetNotFound:
            print("  + Creating new worksheet 'Price_History'...")
            worksheet = sheet.add_worksheet(title="Price_History", rows=1000, cols=10)

        # 3. Setup Headers
        print("[3/4] Formatting headers and freezing row...")
        headers = ["Date", "Product_name", "Store", "Price", "Regular_price"]
        
        # Update header row
        worksheet.update(values=[headers], range_name='A1:E1')
        
        # Format: Bold + Freeze Top Row
        worksheet.format("A1:E1", {
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
        })
        worksheet.freeze(rows=1)

        # 4. Set Column Widths (widths are in pixels)
        # Date=120, Product_name=300, Store=150, Price=100, Regular_price=100
        print("[4/4] Setting column widths...")
        # gspread uses index 1..N or A..Z notation
        # set_column_width doesn't exist in basic gspread, we use format or batch_update
        # Actually gspread has format() for cells but for column width it's a bit different.
        # We'll use the specific gspread command for column resizing if available or skip 
        # as it's a 'nice to have' that requires batch_update with raw requests sometimes.
        # gspread version 5.0+ has worksheet.set_column_width
        try:
            worksheet.set_column_width(0, 120)  # Col A (index 0)
            worksheet.set_column_width(1, 300)  # Col B
            worksheet.set_column_width(2, 150)  # Col C
            worksheet.set_column_width(3, 100)  # Col D
            worksheet.set_column_width(4, 100)  # Col E
        except Exception as e:
            print(f"  ! Warning: Could not set column widths via set_column_width: {e}")

        print("\n" + "=" * 60)
        print("SUCCESS!")
        print(f"Sheet URL: https://docs.google.com/spreadsheets/d/{sheets_helper.SHEET_ID}/edit#gid={worksheet.id}")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: Could not initialise sheet: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
