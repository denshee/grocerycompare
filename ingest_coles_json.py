"""
ingest_coles_json.py
---------------------
Utility to ingest Coles JSON data from subagent extraction.
"""

import json
import os
from datetime import datetime
import sheets_helper

STORE_NAME = "Coles"

def ingest(json_path):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    print(f"Ingesting {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    worksheet = sheets_helper.get_listings_worksheet()
    existing  = sheets_helper.load_existing_listings(worksheet)
    written_names = set()

    new_rows      = []
    price_updates = []
    history_rows  = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for p in products:
        name = p["name"]
        if name in written_names: continue
        
        # Clean price if string (e.g. "$15.40")
        price = p["price"]
        if isinstance(price, str):
            price = float(price.replace("$", "").replace(",", "")) if price else None
        
        was_price = p.get("was_price")
        if isinstance(was_price, str):
            was_price = float(was_price.replace("$", "").replace(",", "")) if was_price else None

        key = (name, STORE_NAME)
        if key in existing:
            old_data = existing[key]
            price_changed = (price is not None and price != old_data['price'])
            reg_price_changed = (was_price is not None and was_price != old_data['reg_price'])
            image_missing = not old_data.get('image') or "/placeholder" in old_data.get('image', '').lower()
            
            if price_changed or reg_price_changed or image_missing:
                img_to_update = p["image"] if image_missing else None
                price_updates.append((old_data['row'], price, was_price, img_to_update))
                if price_changed or reg_price_changed:
                    history_rows.append([now_str, name, STORE_NAME, price, was_price or ""])
        else:
            new_rows.append([
                "", name, STORE_NAME,
                price if price is not None else "",
                was_price if was_price is not None else "",
                "TRUE", p["image"],
            ])
            history_rows.append([now_str, name, STORE_NAME, price if price is not None else "", was_price or ""])
            existing[key] = {'row': -1, 'price': price, 'reg_price': was_price, 'image': p["image"]}

        written_names.add(name)

    created, updated = sheets_helper.batch_upsert(
        worksheet, STORE_NAME, new_rows, price_updates, history_rows
    )
    print(f"DONE. Created: {created} | Updated: {updated}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ingest(sys.argv[1])
    else:
        print("Usage: python ingest_coles_json.py <path_to_json>")
