import os
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()
airtable_token = os.getenv('AIRTABLE_TOKEN')
base_id = os.getenv('AIRTABLE_BASE_ID', 'appryWRqjOFw4EajV')

api = Api(airtable_token)
table = api.table(base_id, 'Listings')

stores = ["Woolworths", "Coles", "Chemist Warehouse", "Aldi"]
total_val = 0

for store in stores:
    records = table.all(formula=f"Store='{store}'")
    count = len(records)
    total_val += count
    print(f"STORE: {store} (TOTAL: {count})")

print(f"\nOVERALL TOTAL: {total_val}")
