from playwright.sync_api import sync_playwright

def run():
    print("Researching Aldi AU structure...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # 1. Check Homepage for categories
        print("Navigating to aldi.com.au...")
        page.goto("https://www.aldi.com.au/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        
        # 2. Extract Category Links
        # Typical Aldi selectors: .ym-gl, .ym-g25, .m-main-navigation__item
        links = page.locator("a[href*='/groceries/']").all()
        print(f"Found {len(links)} grocery-related links")
        for link in links[:5]:
            print(f"  - {link.get_attribute('href')} | {link.inner_text().strip()}")
            
        # 3. Check a specific category (e.g., Dairy)
        dairy_url = "https://www.aldi.com.au/en/groceries/fresh-produce/dairy-eggs/"
        print(f"\nNavigating to {dairy_url}...")
        page.goto(dairy_url, wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        # Aldi products are usually in .m-product-tile or similar
        tiles = page.locator(".m-product-tile, .m-base-product, .m-product-listing-item").all()
        print(f"Found {len(tiles)} products on Dairy page")
        
        if tiles:
            tile = tiles[0]
            name = tile.locator(".m-base-product__title, .m-product-tile__title").first.inner_text().strip()
            price = tile.locator(".m-base-product__price, .m-product-tile__price").first.inner_text().strip()
            print(f"Sample: {name} | {price}")
        
        browser.close()

if __name__ == "__main__":
    run()
