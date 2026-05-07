import subprocess
import requests
import json
import os
import sheets_helper

# CONFIGURATION
WORKER_SYNC_URL = "https://grocerycompare-api.lukeamccullough.workers.dev/api/sync"
API_KEY = "your_secret_auth_key" # Matches the placeholder in worker.js

def run_scraper(script_name):
    """Executes a scraper script and captures its health."""
    print(f"\n--- Starting {script_name} ---")
    try:
        # We run with minimal pages to avoid long hangs in local dev, 
        # but in production you'd remove the --max-pages 2
        result = subprocess.run(["python", script_name, "--max-pages", "2"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Successfully ran {script_name}")
            return True
        else:
            print(f"Error in {script_name}: {result.stderr}")
            return False
    except Exception as e:
        print(f"Failed to execute {script_name}: {e}")
        return False

def push_to_cloud():
    """Fetches the latest data from Google Sheets and pushes to Cloudflare KV."""
    print(f"\n--- Aggregating Market Data from Google Sheets ---")
    
    try:
        worksheet = sheets_helper.get_listings_worksheet()
        raw_data = sheets_helper.load_existing_listings(worksheet)
        
        products = []
        for (name, store), details in raw_data.items():
            products.append({
                "Product_name": name,
                "Grouping_Tag": details.get("category") or details.get("tag") or "Uncategorized",
                "Store": store,
                "Price": details.get("price"),
                "Image_URL": details.get("image")
            })

        print(f"Prepared {len(products)} products for sync.")
        
        # Save local backup
        with open("latest_market_data.json", "w") as f:
            json.dump({"products": products}, f, indent=2)
        print("Generated local backup: latest_market_data.json")

        # Push to Cloudflare
        print(f"Pushing to Cloudflare Worker...")
        response = requests.put(
            WORKER_SYNC_URL, 
            json={"products": products}, 
            headers={"Authorization": API_KEY}
        )
        
        if response.status_code == 200:
            print("SUCCESS: Cloudflare Worker KV updated.")
        else:
            print(f"FAILED: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    print("🚀 INITIALIZING MARKET SYNC PIPELINE")
    
    # 1. Run Scrapers (Coles and Aldi as requested)
    coles_success = run_scraper("coles_full_catalog.py")
    aldi_success = run_scraper("aldi_full_catalog.py")
    
    # 2. Sync the resulting Google Sheets state to Cloudflare KV
    # We sync even if one fails to keep the other's data fresh
    if coles_success or aldi_success:
        push_to_cloud()
    else:
        print("Scrapers failed. Skipping cloud sync to prevent data corruption.")
    
    print("\n--- Market Sync Complete ---")
