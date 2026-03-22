import os, requests
from dotenv import load_dotenv

load_dotenv()
headers = {'Authorization': f'Bearer {os.getenv("AIRTABLE_TOKEN")}'}
res = requests.get('https://api.airtable.com/v0/appryWRqjOFw4EajV/Listings?filterByFormula=Store="Aldi"', headers=headers)
records = res.json().get('records', [])
print(f"TOTAL ALDI: {len(records)}")
for r in records[:5]:
    print(r['fields'].get('Listing name', ''), "|", r['fields'].get('Current price', ''))
