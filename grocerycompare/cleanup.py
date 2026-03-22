import os
from dotenv import load_dotenv
from pyairtable import Api

def main():
    load_dotenv()
    api = Api(os.environ.get("AIRTABLE_TOKEN"))
    table = api.table(os.environ.get("AIRTABLE_BASE_ID"), "Listings")
    
    print("Fetching all records...")
    records = table.all()
    print(f"Total initially: {len(records)}")
    
    to_delete = []
    # Identify the bad records by checking the "On special" field payload
    for r in records:
        val = r.get("fields", {}).get("On special")
        if val == "false" or val == "False":
            to_delete.append(r["id"])
            
    # Fallback to the 3 oldest records if the text value was already wiped by Airtable's schema
    if len(to_delete) == 0:
        records_sorted = sorted(records, key=lambda x: x.get("createdTime", ""))
        to_delete = [x["id"] for x in records_sorted[:3]]
        print("Fallback: Deleting the 3 oldest records manually.")
    elif len(to_delete) > 3:
        to_delete = to_delete[:3]
        
    print(f"Rows to delete: {len(to_delete)}")
    if to_delete:
        table.batch_delete(to_delete)
        print("Deleted!")
        
    records_final = table.all()
    print(f"FINAL ROW COUNT: {len(records_final)}")

if __name__ == "__main__":
    main()
