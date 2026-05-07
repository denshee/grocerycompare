from sheets_helper import get_history_worksheet, COL_CANONICAL_ID
from datetime import datetime

def verify_and_seed():
    print("--- Verifying Price_History Schema ---")
    try:
        ws = get_history_worksheet()
        headers = ws.row_values(1)
        print(f"Current Headers: {headers}")
        
        # Check if we need to update headers
        expected_headers = ["Date", "Canonical_ID", "Product_name", "Store", "Price", "Regular_price"]
        if headers != expected_headers:
            print("Updating headers to 6-column format...")
            ws.update('A1:F1', [expected_headers])
            
        # Add a test row
        test_row = [
            datetime.now().strftime("%Y-%m-%d"),
            "cream-full-milk_3L",
            "Full Cream Milk 3L",
            "Woolworths",
            "4.50",
            "4.50"
        ]
        print(f"Adding test row: {test_row}")
        ws.append_row(test_row)
        print("Success!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_and_seed()
