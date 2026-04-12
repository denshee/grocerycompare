from playwright.sync_api import sync_playwright

def run():
    print("Intercepting API calls on Coles browse...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        def handle_request(request):
            if "api/bff/products" in request.url:
                print("\n intercepted request:", request.url)
        
        page.on("request", handle_request)
        
        page.goto("https://www.coles.com.au/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.goto("https://www.coles.com.au/browse/dairy-eggs-fridge", wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        browser.close()

run()
