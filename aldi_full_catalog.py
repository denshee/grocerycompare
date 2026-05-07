import time
import random
import re
from datetime import datetime
import sheets_helper
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

STORE_NAME = "Aldi"
ALDI_CATEGORIES = [
    "https://www.aldi.com.au/en/groceries/super-savers/",
    "https://www.aldi.com.au/en/groceries/fresh-produce/",
    "https://www.aldi.com.au/en/groceries/meat-seafood/",
    "https://www.aldi.com.au/en/groceries/bakery/",
    "https://www.aldi.com.au/en/groceries/dairy-eggs-fridge/",
    "https://www.aldi.com.au/en/groceries/pantry/",
    "https://www.aldi.com.au/en/groceries/freezer/",
    "https://www.aldi.com.au/en/groceries/drinks/",
    "https://www.aldi.com.au/en/groceries/laundry-household/",
    "https://www.aldi.com.au/en/groceries/beauty-personal-care/"
]

def clean_price(text):
    if not text: return None
    if 'c' in text.lower():
        digits = re.sub(r'[^\d]', '', text)
        return float(digits) / 100.0 if digits else None
    cleaned = re.sub(r'[^\d.]', '', text)
    try: return float(cleaned) if cleaned else None
    except: return None

def main():
    worksheet = sheets_helper.get_listings_worksheet()
    existing = sheets_helper.load_existing_listings(worksheet)
    buffer, written_names = [], set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        Stealth().use_sync(page)

        for url in ALDI_CATEGORIES:
            cat_name = url.split('/')[-2].replace('-', ' ').title()
            print(f"  Scraping Aldi {cat_name}...")
            page.goto(url, wait_until="networkidle")
            
            tiles = page.locator("div.product-tile").all()
            for tile in tiles:
                name = tile.locator(".product-tile__name").first.inner_text().strip()
                price_text = tile.locator(".base-price__regular").first.inner_text().strip()
                price = clean_price(price_text)
                img_url = tile.locator("img").first.get_attribute("src")
                if img_url and img_url.startswith("//"): img_url = "https:" + img_url

                if name and price:
                    buffer.append({"name": name, "category": cat_name, "price": price, "was_price": None, "in_stock": "TRUE", "image": img_url})

            if len(buffer) >= 100:
                new_r, up_r, hist_r = [], [], [] # Simplified for this script
                # (Normally you'd call build_upsert_data logic here)
                buffer = []

        browser.close()

if __name__ == "__main__":
    main()