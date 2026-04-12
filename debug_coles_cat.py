import requests
import json

HEADERS = {
    "ocp-apim-subscription-key": "eae83861d1cd4de6bb9cd8a2cd6f041e",
    "x-api-version": "2",
    "dsch-channel": "coles.online.1site.desktop",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def test():
    # Attempting various parameters for category:
    urls = [
        "https://www.coles.com.au/api/bff/products/category?slug=dairy-eggs-fridge",
        "https://www.coles.com.au/api/bff/products/search?slug=dairy-eggs-fridge",
        "https://www.coles.com.au/api/bff/products/search?category=dairy-eggs-fridge",
        "https://www.coles.com.au/api/bff/products/search?categoryId=dairy-eggs-fridge",
    ]
    
    for url in urls:
        print(f"Testing: {url}")
        res = requests.get(url, headers=HEADERS)
        print("Status", res.status_code)
        if res.status_code == 200:
            data = res.json()
            if "pageProps" in data and "searchResults" in data["pageProps"]:
                print("Found products:", len(data["pageProps"]["searchResults"]))
                return
            if "results" in data or "products" in data:
                print("Found products:", len(data.get("results", data.get("products", []))))
                return
            # Let's see keys
            print("Keys:", data.keys())

test()
