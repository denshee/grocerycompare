from playwright.sync_api import sync_playwright

def run():
    print("Verifying Aldi Product Selectors...")
    # Using a specific category URL found in the sitemap
    test_url = "https://www.aldi.com.au/products/dairy-eggs-fridge/milk/k/1111111160"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print(f"Navigating to {test_url}...")
        page.goto(test_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Taking a screenshot for manual check if needed, but let's try finding selectors
        # Based on previous research: .m-product-tile, .m-base-product
        tiles = page.locator(".m-product-tile, .m-base-product, .m-product-listing-item").all()
        print(f"Found {len(tiles)} product tiles")
        
        # If no tiles found, search more broadly
        if not tiles:
             print("Falling back to scanning all divs for price-like content...")
             tiles = page.locator("div:has(span[class*='price'])").all()
             print(f"Broad search found {len(tiles)} tiles")

        for i, tile in enumerate(tiles[:5]):
            print(f"\nProduct {i+1}:")
            try:
                # Common Aldi class names (they use OOCSS/BEM)
                name = tile.locator("[class*='title'], [class*='name']").first.inner_text().strip()
                price = tile.locator("[class*='price']").first.inner_text().strip()
                img = tile.locator("img").first.get_attribute("src")
                print(f"  Name: {name}")
                print(f"  Price: {price}")
                print(f"  Img: {img}")
            except Exception as e:
                print(f"  Error extracting from tile {i+1}: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
