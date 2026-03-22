import os
import requests
from dotenv import load_dotenv

load_dotenv()
airtable_token = os.getenv("AIRTABLE_TOKEN")
base_id = os.getenv("AIRTABLE_BASE_ID", "appryWRqjOFw4EajV")

url = f"https://api.airtable.com/v0/{base_id}/Listings"
headers = {"Authorization": f"Bearer {airtable_token}"}

res = requests.get(f"{url}?filterByFormula=Store='Coles'&sort%5B0%5D%5Bfield%5D=createdTime&sort%5B0%5D%5Bdirection%5D=desc", headers=headers)
records = res.json().get("records", [])

print(f"\nTotal Coles Database Record Count: {len(records)}\n")

success_count = 0
for r in records[:5]:
    f = r.get('fields', {})
    name = f.get('Listing name', 'MISSING')
    price = f.get('Current price', 'MISSING')
    category = f.get('Category', 'MISSING')
    image = f.get('Image URL', 'MISSING')
    store = f.get('Store', 'MISSING')
    
    print(f"-> {name} | ${price}")
    print(f"   Category: {category}")
    print(f"   Image URL: {image[:50] if isinstance(image, str) else image}...")
    print(f"   Store: {store}\n")
    if category != 'MISSING' and image != 'MISSING' and store == 'Coles':
        success_count += 1
        
print(f"Verified Data Target Schemas: {success_count}/5 successful categorical arrays mapped correctly!")
