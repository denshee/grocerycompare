import os
import time
import random
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import sheets_helper

STORE_NAME = "Coles"
SEARCH_TERMS = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken", "beef", "apples", "bananas"]

def clean_price(text):
    if not text: return 0.0
    match = re.search(r'(\d+\.?\d*)', text.replace('$', ''))
    return float(match.group(1)) if match else 0.0

def human_delay(min_sec=2, max_sec=5):
    time.sleep(random.uniform(min_sec, max_sec))

def simulate_human_behavior(page):
    scroll_amount = random.randint(300, 800)
    page.mouse.wheel(0, scroll_amount)
    human_delay(1, 3)
    page.mouse.wheel(0, -random.randint(100, scroll_amount))
    
    for _ in range(3):
        x = random.randint(100, 1000)
        y = random.randint(100, 800)
        page.mouse.move(x, y, steps=10)
        time.sleep(random.uniform(0.1, 0.5))

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    all_new_rows, all_updates = [], []

    # Securely grab your IPRoyal credentials from GitHub Secrets
    proxy_server = os.environ.get("PROXY_SERVER")
    proxy_username = os.environ.get("PROXY_USERNAME")
    proxy_password = os.environ.get("PROXY_PASSWORD")

    proxy_settings = None
    if proxy_server and proxy_username and proxy_password:
        proxy_settings = {
            "server": proxy_server,
            "username": proxy_username,
            "password": proxy_password
        }
    else:
        print("  ⚠️ CRITICAL: Proxy credentials missing from environment!")

    with sync_playwright() as p:
        # Launching with the Residential Proxy Active
        browser = p.chromium.launch(
            headless=True, 
            proxy=proxy_settings,
            slow_mo=random.randint(200, 500)
        ) 
        
        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.