from playwright.sync_api import sync_playwright
import time
import re
import json

def run():
    print("1. Fetching Coles Category Tree...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        # Tracking Coles specific `bff` (Backend For Frontend) API JSON structures.
        api_responses = {}
        def handle_response(response):
            if "api/bff/products" in response.url:
                try:
                    api_responses["category"] = response.json()
                except:
                    pass
                    
        page.on("response", handle_response)
        
        print("   -> Navigating to Coles Homepage to trigger Datadome passes...")
        page.goto("https://www.coles.com.au/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        try:
            if page.locator("button:has-text('Categories'), button[data-testid='categories-menu-button']").is_visible():
                page.locator("button:has-text('Categories'), button[data-testid='categories-menu-button']").click(timeout=3000)
                page.wait_for_timeout(2000)
        except:
            pass

        # Locate URLs corresponding strictly to /browse/ nodes
        category_nodes = page.locator("a[href*='/browse/']").all_inner_texts()
        categories = list(dict.fromkeys([c.strip() for c in category_nodes if len(c.strip()) > 2]))
        
        print(f"\n✅ Found {len(categories)} Main Category Nodes:")
        for c in categories[:10]:
            print(f"   - {c}")
        if len(categories) > 10:
            print(f"   - ... and {len(categories)-10} more.")
            
        print("\n2. Testing Pagination on explicit logic URL: '/browse/dairy-eggs-fridge'...")
        page.goto("https://www.coles.com.au/browse/dairy-eggs-fridge", wait_until="networkidle")
        page.wait_for_timeout(4000)
        
        total_products = 0
        try:
            count_text = page.locator("[data-testid='pagination-summary'], .sc-coles-typography").first.inner_text(timeout=5000)
            match = re.search(r'of ([0-9,]+)', count_text)
            if match:
                total_products = int(match.group(1).replace(',', ''))
                print(f"✅ Extracted Total Category Products: {total_products}")
            else:
                print(f"❌ Regex failed. String found: {count_text}")
        except:
            pass

        if "category" in api_responses:
            print("\n✅ Successfully Intercepted internal Coles BFF JSON API payload!")
            data = api_responses["category"]
            results = data.get("results", [])
            print(f"-> Page 1 parsed {len(results)} nested products explicitly from backend JSON.")
            
            print("\n3. Sample Products extracted from API JSON:")
            for i, p in enumerate(results[:3]):
                name = p.get("name", "Unknown")
                pricing = p.get("pricing", {})
                price = pricing.get("now", "N/A")
                print(f"  [{i+1}] {name} | ${price}")
        else:
             print("\n❌ Failed to intercept API mapping. Falling back to explicit DOM CSS scraping...")
             cards = page.locator("[data-testid='product-tile']").all()
             print(f"-> Page 1 rendered {len(cards)} items natively across the DOM.")
             print("\n3. Sample Products extracted from DOM Tags:")
             for i, c in enumerate(cards[:3]):
                 try:
                     name = c.locator(".product__title").first.inner_text()
                     price = c.locator(".price__value").first.inner_text().replace('\n', '')
                     print(f"  [{i+1}] {name.strip()} | {price.strip()}")
                 except:
                     pass
                     
        if total_products > 0:
            # Coles renders precisely 48 blocks per JSON execution compared to Woolworths 36
            print(f"\n=> Coles specifically maps 48 items per array! Full extraction needs exactly {total_products//48 + 1} API page loops!")
            print("=> NO Airtable constraints were hit or executed globally.")

        browser.close()

if __name__ == "__main__":
    run()
