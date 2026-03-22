import os
import requests
from dotenv import load_dotenv

load_dotenv()
AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN')
BASE_ID = 'appryWRqjOFw4EajV'
LISTINGS_TABLE = 'Listings'

url = f'https://api.airtable.com/v0/{BASE_ID}/{LISTINGS_TABLE}'
headers = {'Authorization': f'Bearer {AIRTABLE_TOKEN}'}
params = {'filterByFormula': '{Store} = "Chemist Warehouse"'}

all_records = []
while True:
    res = requests.get(url, headers=headers, params=params)
    data = res.json()
    all_records.extend(data.get('records', []))
    if 'offset' not in data:
        break
    params['offset'] = data['offset']

print(f"TOTAL: {len(all_records)}")
print("SAMPLES:")
for r in all_records[:5]:
    print(f"- {r['fields'].get('Listing name')} | ${r['fields'].get('Current price', 'N/A')}")
