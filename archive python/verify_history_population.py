"""
verify_history_population.py
----------------------------
Counts rows in Price_History to confirm baseline population.
"""

import sheets_helper

def main():
    print("Verifying Price_History population...")
    try:
        ws = sheets_helper.get_history_worksheet()
        rows = ws.get_all_values()
        count = len(rows) - 1 # exclude header
        print(f"\n✅ Total history records found: {count}")
        if count > 0:
            print(f"Latest record: {rows[-1]}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
