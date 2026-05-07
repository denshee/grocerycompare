import time
from curl_cffi import requests
import sheets_helper

STORE_NAME = "Woolworths"
CAT_MAP = {"1-E5BEE36E": "Fruit & Veg", "1_6E4E4E4": "Dairy, Eggs & Fridge"}

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)

    for cat_id, cat_name in CAT_MAP.items():
        print(f"  Scraping Woolies: {cat_name}")
        url = "https://www.woolworths.com.au/apis/ui/browse/category"
        params = {"categoryId": cat_id, "pageNumber": 1, "pageSize": 36}
        
        r = requests.get(url, params=params, impersonate="chrome124")
        bundles = r.json().get('Bundles', [])
        
        new_rows, updates = [], []
        for b in bundles:
            p = b.get('Products', [{}])[0]
            name = p.get('Name')
            price = p.get('Price')
            img = p.get('MediumImageFile')

            key = (name, STORE_NAME)
            if key in existing:
                old = existing[key]
                updates.append((old['row'], [cat_name, STORE_NAME, price, None, "TRUE", img, ""]))
            else:
                new_rows.append(["", name, cat_name, STORE_NAME, price, "", "TRUE", img])
        
        if new_rows or updates:
            sheets_helper.batch_upsert(worksheet, STORE_NAME, new_rows, updates)

if __name__ == "__main__":
    main()