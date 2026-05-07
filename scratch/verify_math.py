import requests
import json

API_BASE = "https://grocerycompare-api.lukeamccullough.workers.dev/api/search"

def get_min_prices(query):
    try:
        response = requests.get(f"{API_BASE}?q={query}")
        data = response.json()
        products = data.get("products", [])
        
        store_min = {"Coles": float('inf'), "Woolworths": float('inf'), "Aldi": float('inf')}
        
        for p in products:
            price_str = str(p.get("Current_price", p.get("current_price", "0")))
            price = float(''.join(c for c in price_str if c.isdigit() or c == '.'))
            store = p.get("Store", p.get("store", "Market"))
            
            if price > 0 and store in store_min:
                if price < store_min[store]:
                    store_min[store] = price
                    
        return store_min
    except Exception as e:
        print(f"Error fetching {query}: {e}")
        return None

items = ["Milk", "Eggs"]
results = {}

print("--- FETCHING LIVE API DATA ---")
for item in items:
    print(f"Searching for {item}...")
    results[item] = get_min_prices(item)

store_totals = {"Coles": 0, "Woolworths": 0, "Aldi": 0}
split_trip = {"Coles": [], "Woolworths": [], "Aldi": [], "splitTotal": 0}

for item, prices in results.items():
    if not prices: continue
    
    best_price = float('inf')
    best_store = None
    
    for store, price in prices.items():
        if price != float('inf'):
            store_totals[store] += price
            if price < best_price:
                best_price = price
                best_store = store
                
    if best_store:
        split_trip[best_store].append({"name": item, "price": best_price})
        split_trip["splitTotal"] += best_price

print("\n--- OPTIMIZATION RESULTS ---")
print(f"Coles Total: ${store_totals['Coles']:.2f}")
print(f"Woolworths Total: ${store_totals['Woolworths']:.2f}")
print(f"Aldi Total: ${store_totals['Aldi']:.2f}")
print(f"\nMAXIMUM SAVINGS SPLIT: ${split_trip['splitTotal']:.2f}")
for store in ["Coles", "Woolworths", "Aldi"]:
    print(f"  {store}: {[f'{i['name']} (${i['price']:.2f})' for i in split_trip[store]]}")
