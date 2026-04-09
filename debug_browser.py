from playwright.sync_api import sync_playwright
import os

url = f"file:///{os.path.abspath('grocerycompare/index_v2.html').replace('\\', '/')}"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    
    print("--- CONSOLE LOGS ---")
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err.message}"))
    
    print("\n--- NETWORK LOGS ---")
    page.on("request", lambda req: print(f"REQ: {req.method} {req.url}"))
    page.on("response", lambda res: print(f"RES: {res.status} {res.url}"))
    
    print(f"Navigating to {url}")
    page.goto(url)
    
    print("\nTriggering search for 'milk'...")
    try:
        page.evaluate("document.getElementById('searchInput').value = 'milk';")
        page.evaluate("document.getElementById('searchBtn').click();")
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Error interacting with page: {e}")
    
    browser.close()
