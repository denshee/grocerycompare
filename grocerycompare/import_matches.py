import os
import csv
import time
from dotenv import load_dotenv
from pyairtable import Api

def main():
    load_dotenv()
    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    if not airtable_token or not base_id:
        print("Error: Missing credentials in .env")
        return

    csv_file = "pairs_matched.csv"
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found.")
        return

    print("Initializing Airtable connection...")
    api = Api(airtable_token)
    match_table = api.table(base_id, "Match Queue")

    print(f"Reading offline validations from {csv_file}...")
    matches_to_push = []
    
    with open(csv_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            comparable_raw = str(row.get("comparable", "")).strip().lower()
            if comparable_raw not in ["true", "1", "yes", "t", "y"]:
                continue
                
            try:
                conf = float(row.get("confidence", 0))
            except ValueError:
                conf = 0.0
                
            if conf >= 80:
                status = "Approved"
            else:
                status = "Pending"
                
            match_obj = {
                "Listing A": row.get("listing_a", ""),
                "Listing B": row.get("listing_b", ""),
                "AI confidence": int(conf),
                "Status": status,
                "Notes": row.get("reason", "")
            }
            matches_to_push.append(match_obj)

    print(f"Total verified 'comparable=True' pairs isolated: {len(matches_to_push)}")
    
    if matches_to_push:
        print("Pushing matches securely to Airtable applying mandatory 0.2s throttle boundary...")
        total_pushed = 0
        for match in matches_to_push:
            try:
                match_table.create(match)
                total_pushed += 1
                if total_pushed % 10 == 0 or total_pushed < 5:
                    print(f"  [Push OK {total_pushed}/{len(matches_to_push)}] {match['Listing A']} <=> {match['Listing B']} ({status})")
            except Exception as e:
                print(f"  [Push Error] Failed isolated match {match['Listing A']} <=> {match['Listing B']}: {e}")
            
            # Rigid 0.2s sleep between executions explicitly to enforce rate limits 
            time.sleep(0.2)
            
        print(f"\n✅ Total successfully imported pipeline matched: {total_pushed}")
    else:
        print("No valid matches found to push.")

if __name__ == "__main__":
    main()
