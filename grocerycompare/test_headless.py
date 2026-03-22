import time
from playwright.sync_api import sync_playwright

def test_headless():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        page.goto("https://www.woolworths.com.au/shop/browse/dairy-eggs-fridge", wait_until="networkidle")
        time.sleep(3)
        print("Title:", page.title())
        count = page.locator(".product-card, .product-container, wow-product-tile").count()
        print("Products:", count)
        browser.close()

test_headless()
