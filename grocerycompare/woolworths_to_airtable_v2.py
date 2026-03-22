import os
import time
import json
import re
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

CATEGORIES = [
    "dairy-eggs-fridge", "fruit-veg", "pantry"
]

DRY_RUN = False
TEST_PAGE_LIMIT = 2

def clean_price(price_val):
    if not price_val: return None
    try:
        if isinstance(price_val, str):
            cleaned = re.sub(r'[^0-9.]', '', price_val)
            return float(cleaned) if cleaned else None
        return float(price_val)
    except:
        return None

def run_scraper():
    load_dotenv()
    print("="*50)
    print("WOOLWORTHS V2 SCRAPER (LIVE TEST MODE)")
    print("="*50)

    collected_products = []
    
    with sync_playwright() as p:
        is_ci = os.environ.get("CI") == "true"
        browser = p.chromium.launch(headless=is_ci)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        for cat_index, category in enumerate(CATEGORIES, 1):
            print(f"\n[{cat_index}/{len(CATEGORIES)}] Scanning Category Node: '{category}'")
            
            page_number = 1
            has_next_page = True
            category_extracted_count = 0
            total_category_products = 0

            while has_next_page:
                api_responses = {}
                def handle_response(response):
                    if "apis/ui/browse/category" in response.url:
                        try:
                            api_responses["browse"] = response.json()
                        except:
                            pass
                            
                page.on("response", handle_response)
                url = f"https://www.woolworths.com.au/shop/browse/{category}?pageNumber={page_number}"
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(4500)
                except Exception:
                    print(f"  -> Timeout traversing page {page_number}. Retrying iteration...")
                    page.remove_listener("response", handle_response)
                    break
                    
                page.remove_listener("response", handle_response)
                
                if "browse" not in api_responses:
                    print(f"  -> ❌ Failed extracting JSON array on Page {page_number}.")
                    break
                    
                data = api_responses["browse"]
                bundles = data.get("Bundles", [])
                
                if page_number == 1:
                    total_category_products = data.get("TotalRecordCount", 0)
                    if total_category_products == 0:
                        break
                        
                if not bundles:
                    break
                    
                page_products = []
                for b in bundles:
                    prods = b.get("Products", [])
                    for prod in prods:
                        if not prod.get("IsAvailable"):
                            continue
                            
                        p_name = prod.get("DisplayName")
                        if not p_name: continue
                        
                        raw_fields = {
                            "Listing name": p_name,
                            "Store": "Woolworths",
                            "Category": category.replace('-', ' ').title(),
                            "Image URL": prod.get("MediumImageFile"),
                            "Current price": clean_price(prod.get("Price")),
                            "Regular price": clean_price(prod.get("WasPrice")),
                            "On special": bool(prod.get("IsOnSpecial")),
                            "In stock": bool(prod.get("IsInStock"))
                        }
                        
                        page_products.append({k: v for k, v in raw_fields.items() if v not in [None, False, ""]})
                
                collected_products.extend(page_products)
                category_extracted_count += len(page_products)
                
                print(f"  -> P{page_number}: [Product {category_extracted_count}/{total_category_products}]")
                
                if category_extracted_count >= total_category_products or not bundles:
                    has_next_page = False
                else:
                    page_number += 1
                    
                if TEST_PAGE_LIMIT and page_number > TEST_PAGE_LIMIT:
                    print("  [!] TEST_PAGE_LIMIT ACTIVE: Terminating loop early for validation.")
                    break

        browser.close()
        
    print(f"\nScrape Complete! Extracted {len(collected_products)} products natively.")
    
    if DRY_RUN:
        return

    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "appryWRqjOFw4EajV")
    if not airtable_token:
        print("ERROR: Airtable bindings securely missing from environment vars.")
        return

    url = f"https://api.airtable.com/v0/{base_id}/Listings"
    headers = {"Authorization": f"Bearer {airtable_token}", "Content-Type": "application/json"}
    
    print("\nFetching native Airtable limits mapping overlapping identical stores...")
    existing_map = {}
    res = requests.get(f"{url}?filterByFormula=Store='Woolworths'", headers=headers)
    if res.ok:
        for r in res.json().get('records', []):
             existing_map[r['fields'].get('Listing name', '')] = r['id']
             
    print(f"Executing sequential UPSERT payload blocks tracing constraints (0.2s offsets) ...")
    updates, creates = 0, 0
    for p in collected_products:
        try:
            name = p.get("Listing name")
            if name in existing_map:
                req = requests.patch(f"{url}/{existing_map[name]}", json={"fields": p}, headers=headers)
                updates += 1
            else:
                req = requests.post(url, json={"fields": p}, headers=headers)
                if req.ok:
                    existing_map[name] = req.json()['id']
                    creates += 1
            time.sleep(0.2)
        except Exception as e:
            print(f"  [Error] Tracing {name}: {e}")
            
    print(f"\n[LIVE DB STATUS]: Created {creates} natively | Updated {updates} parameters.")

if __name__ == "__main__":
    run_scraper()
