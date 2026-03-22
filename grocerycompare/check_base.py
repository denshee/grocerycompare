import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ.get("AIRTABLE_TOKEN")
base_id = os.environ.get("AIRTABLE_BASE_ID")

url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, headers=headers)
print("Status Code:", resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    print("Tables found in base:")
    for t in data.get("tables", []):
        print(f"- {t['name']} (ID: {t['id']})")
        print("  Fields:")
        for f in t.get("fields", []):
            print(f"    - {f['name']} ({f['type']})")
else:
    print("Error:", resp.text)
