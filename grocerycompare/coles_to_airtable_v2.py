import os
import time
import json
import re
import requests
from dotenv import load_dotenv
from pyairtable import Api
from playwright.sync_api import sync_playwright

CATEGORIES = [
    "dairy-eggs-fridge", "fruit-vegetables", "pantry"
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
    print("COLES CATEGORY SCRAPER V2 (LIVE TEST MODE)")
    print("="*50)

    collected_products = []
    
    with sync_playwright() as p:
        is_ci = os.environ.get("CI") == "true"
        browser = p.chromium.launch(headless=is_ci)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
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
                url = f"https://www.coles.com.au/browse/{category}?page={page_number}"
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(4500)
                except Exception:
                    print(f"  -> Timeout traversing page {page_number}. Retrying...")
                    break
                    
                if page_number == 1:
                    try:
                        count_text = page.locator("[data-testid='pagination-summary'], .sc-coles-typography").first.inner_text(timeout=5000)
                        match = re.search(r'of ([0-9,]+)', count_text)
                        if match:
                            total_category_products = int(match.group(1).replace(',', ''))
                    except:
                        pass
                
                cards = page.locator("[data-testid='product-tile']").all()
                if not cards:
                    print(f"  -> ❌ Failed rendering DOM elements on Page {page_number}. DataDome may have blocked the page.")
                    break
                    
                page_products = []
                for c in cards:
                    try:
                        p_name = c.locator(".product__title").first.inner_text()
                        if not p_name: continue
                        
                        price = c.locator(".price__value").first.inner_text().replace('\n', '')
                        
                        was_price = None
                        try:
                            if c.locator(".price__was").count() > 0:
                                was_price = c.locator(".price__was").first.inner_text().replace('\n', '')
                        except: pass
                        
                        is_on_special = False
                        try:
                            if c.locator(".product__badge, .badge").count() > 0:
                                badges = c.locator(".product__badge, .badge").all_inner_texts()
                                is_on_special = any("SPECIAL" in b.upper() or "SAVE" in b.upper() for b in badges)
                        except: pass
                        
                        img_url = None
                        try:
                            if c.locator("img").count() > 0:
                                img_url = c.locator("img").first.get_attribute("src")
                                if img_url and img_url.startswith('/'):
                                    img_url = f"https://www.coles.com.au{img_url}"
                        except: pass

                        raw_fields = {
                            "Listing name": p_name.strip(),
                            "Store": "Coles",
                            "Category": category.replace('-', ' ').title(),
                            "Image URL": img_url,
                            "Current price": clean_price(price),
                            "Regular price": clean_price(was_price) if was_price else None,
                            "On special": is_on_special,
                            "In stock": True
                        }
                        
                        page_products.append({k: v for k, v in raw_fields.items() if v not in [None, False, ""]})
                    except Exception:
                        pass
                
                collected_products.extend(page_products)
                category_extracted_count += len(page_products)
                
                print(f"  -> P{page_number}: [Product {category_extracted_count}/{total_category_products}]")
                
                if len(cards) < 48 or (total_category_products > 0 and category_extracted_count >= total_category_products):
                    has_next_page = False
                else:
                    page_number += 1
                    
                if TEST_PAGE_LIMIT and page_number > TEST_PAGE_LIMIT:
                    print("  [!] TEST_PAGE_LIMIT ACTIVE: Terminating loop early.")
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
    
    print("\nInitializing native Airtable REST pipeline...")
    api = Api(airtable_token)
    table = api.table(base_id, "Listings")

    existing_map = {}
    print("Fetching active Coles elements dropping identical collisions...")
    try:
        records = table.all(formula="Store='Coles'")
        for r in records:
            existing_map[r['fields'].get('Listing name', '')] = r['id']
    except Exception as e:
        print(f"Failure establishing active table parameters: {e}")
             
    print(f"Executing 0.2s explicit offset sequence POST/PATCH hooks...")
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
