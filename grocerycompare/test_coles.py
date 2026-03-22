import requests
import json

url = "https://www.coles.com.au/api/bff/products/search?q=milk&storeId=76748&start=0"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.coles.com.au",
    "Origin": "https://www.coles.com.au"
}

print("Fetching from Coles API...")
response = requests.get(url, headers=headers)
print("Status Code:", response.status_code)

try:
    data = response.json()
    
    # Locate the array of products
    products = []
    if "results" in data:
        products = data["results"]
    elif "products" in data:
        products = data["products"]
    else:
        # Fallback recursive search for largest list
        for k, v in data.items():
            if isinstance(v, list) and len(v) > len(products):
                products = v
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, list) and len(v2) > len(products):
                        products = v2

    if products:
        print("\n=== FIRST 2 COLES PRODUCTS JSON ===")
        print(json.dumps(products[:2], indent=2))
    else:
        print("\n=== RAW COLES JSON (First 3000 chars) ===")
        print(json.dumps(data, indent=2)[:3000])

except Exception as e:
    print("Could not parse JSON:", e)
    print("Raw text:", response.text[:2000])
