import os
import json
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

# Safely load the Apify token
token = os.getenv("APIFY_TOKEN")
if not token or token == "":
    print("❌ ERROR: APIFY_TOKEN not found in .env file!")
    exit(1)

# Initialize the ApifyClient
client = ApifyClient(token)

def test_aldi_search():
    print("🔍 Calling Apify stealth_mode/aldi-product-search-scraper for 'milk'...")
    
    # Setup the execution structure matching Apify constraints
    run_input = {
        "query": "milk",
        "limit": 2  # Only grab 2 items max to check the output structure quickly
    }
    
    # Run the Actor and wait for it to finish
    run = client.actor("stealth_mode/aldi-product-search-scraper").call(run_input=run_input)
    
    print("✅ Actor execution finished, Fetching Data Payload...")
    
    # Fetch and print the items from the run's dataset
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    
    if not items:
        print("No items returned by the actor.")
        return

    # Dump the first item out beautifully formatted structurally
    print("\n--- ALDI DATA SCHEMA [Item 1] ---")
    print(json.dumps(items[0], indent=2))

if __name__ == "__main__":
    test_aldi_search()
