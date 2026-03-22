import os, requests
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()
headers={'Authorization': f'Bearer {os.getenv("AIRTABLE_TOKEN")}'}
formula='OR(FIND("panadol",LOWER({Listing name}))>0, FIND("panadol",LOWER({Category}))>0)'
res=requests.get(f'https://api.airtable.com/v0/appryWRqjOFw4EajV/Listings?filterByFormula={quote(formula)}', headers=headers)
print('STATUS:', res.status_code)
print(res.text[:1000])
