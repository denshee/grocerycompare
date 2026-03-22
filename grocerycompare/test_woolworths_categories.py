from playwright.sync_api import sync_playwright
import time
import re

def run():
    print("1. Fetching Woolworths Category Tree...")
    with sync_playwright() as p:
        # Launching with headless=False prevents Akamai Bot Manager timeouts entirely!
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        print("   -> Navigating to Woolworths dynamically mapping the UI hierarchy...")
        page.goto("https://www.woolworths.com.au/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000) # Hydration Buffer
        
        try:
             # Target native Browse components expanding nested hierarchy nodes
             if page.locator("button:has-text('Browse')").is_visible():
                 page.locator("button:has-text('Browse')").click(timeout=3000)
                 page.wait_for_timeout(2000)
        except Exception:
             pass 

        # Locate exact Category Strings securely bypassing backend token failures
        category_nodes = page.locator("a[href*='/shop/browse/']").all_inner_texts()
        categories = list(dict.fromkeys([c.strip() for c in category_nodes if len(c.strip()) > 2]))
        
        print(f"\n✅ Found {len(categories)} Main Category Hierarchy Nodes:")
        for idx, c in enumerate(categories[:10]):
            print(f"   - {c}")
        if len(categories) > 10:
            print(f"   - ... and {len(categories)-10} more subcategories.")

        print("\n2. Testing Pagination on Category: 'dairy-eggs-fridge'...")
        page.goto("https://www.woolworths.com.au/shop/browse/dairy-eggs-fridge", wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        total_products = 0
        try:
            # Safely trace the actual DOM elements containing integer array boundaries (e.g. '1234 Products')
            count_text = page.locator(".product-count, .search-result-count, h1.page-title, span.total-results").first.inner_text(timeout=5000)
            match = re.search(r'([0-9,]+)', count_text)
            if match:
                total_products = int(match.group(1).replace(',', ''))
                print(f"✅ Extracted Total Category Products: {total_products}")
        except Exception:
            print("❌ Could not directly locate string count node in DOM.")

        # Parse the literal product grids validating dynamic variables natively
        product_cards = page.locator("wow-product-tile, .product-card, .product-container, [data-testid='product-card']").all()
        print(f"-> Page 1 safely rendered {len(product_cards)} native items injected from backend XHR responses.")

        print("\n3. Sample Products from Page 1:")
        for i, card in enumerate(product_cards[:3]):
            try:
                name = card.locator(".title, .product-title-link, .product-title, h3").first.inner_text()
                price = card.locator(".price, .primary-price, .product-price").first.inner_text().replace('\n', '')
                print(f"  [{i+1}] {name.strip()} | {price.strip()}")
            except Exception:
                pass
                
        if total_products > 0 and len(product_cards) > 0:
            total_pages = (total_products + len(product_cards) - 1) // len(product_cards)
            print(f"\n=> Full extraction of this Category would require exactly {total_pages} paginated requests!")
            print("=> NO Airtable modifications were committed natively!")

        browser.close()

if __name__ == "__main__":
    run()
