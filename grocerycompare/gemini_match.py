import os
import time
import requests
import json
import re
from dotenv import load_dotenv
from pyairtable import Api

def get_gemini_json(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a highly precise grocery matching API. Output purely valid JSON format without markdown blocks."}]
        },
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            time.sleep(1)
            
    return None

def get_keywords(name):
    # Convert to lowercase, remove punctuation, split by space into a set of unique words
    return set(re.findall(r'\b\w+\b', name.lower()))

def main():
    load_dotenv()
    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not airtable_token or not base_id or not gemini_key:
        print("Missing required environment variables in .env.")
        return

    print("Initializing Airtable connection...")
    api = Api(airtable_token)
    listings_table = api.table(base_id, "Listings")
    match_table = api.table(base_id, "Match Queue")
    
    print("Fetching all listings from Airtable...")
    try:
        records = listings_table.all()
    except Exception as e:
        print(f"Error fetching from Airtable: {e}")
        return

    woolies = []
    coles = []

    for r in records:
        fields = r.get("fields", {})
        store = fields.get("Store")
        name = fields.get("Listing name", "").strip()
        if not name: continue
            
        item_data = {"id": r["id"], "name": name, "fields": fields}
        if store == "Woolworths":
            woolies.append(item_data["name"])
        elif store == "Coles":
            coles.append(item_data["name"])

    keywords = [
        "milk", "bread", "eggs", "butter", "cheese", "yoghurt", 
        "chicken", "beef", "rice", "pasta", "cereal", "juice", 
        "chips", "chocolate", "coffee", "tea", "toilet paper", "dishwashing"
    ]

    w_buckets = {k: [] for k in keywords}
    c_buckets = {k: [] for k in keywords}

    def assign_to_bucket(item_name, buckets):
        low_name = item_name.lower()
        for k in keywords:
            if k in low_name:
                buckets[k].append(item_name)
                return True
        return False

    for w in woolies:
        assign_to_bucket(w, w_buckets)
    for c in coles:
        assign_to_bucket(c, c_buckets)

    shortlisted_pairs_by_bucket = {k: [] for k in keywords}
    total_shortlisted = 0
    total_raw_comparisons = 0

    print("\n--- Smart Filtering Phase ---")
    for k in keywords:
        w_list = w_buckets[k]
        c_list = c_buckets[k]
        raw_comparisons = len(w_list) * len(c_list)
        total_raw_comparisons += raw_comparisons
        
        for w_item in w_list:
            for c_item in c_list:
                w_words = get_keywords(w_item)
                c_words = get_keywords(c_item)
                
                # Check for at least 2 shared keywords
                shared = w_words.intersection(c_words)
                if len(shared) >= 2:
                    shortlisted_pairs_by_bucket[k].append((w_item, c_item))
                    
        shortlisted_count = len(shortlisted_pairs_by_bucket[k])
        total_shortlisted += shortlisted_count
        print(f"Bucket '{k}': {raw_comparisons} raw comparisons -> {shortlisted_count} shortlisted pairs")

    print(f"\nTotal raw comparisons eliminated: {total_raw_comparisons} -> {total_shortlisted}")
    print("Starting API validation for shortlisted pairs only...\n")
    
    total_queued = 0

    for k in keywords:
        pairs = shortlisted_pairs_by_bucket[k]
        if not pairs:
            continue
            
        print(f"=== Validating Bucket: {k} ({len(pairs)} pairs) ===")
        for w_name, c_name in pairs:
            # We skip Gemini for a test fast output here... No wait, we only call Gemini now!
            prompt = f'''Compare these two grocery products. Product A: "{w_name}" Product B: "{c_name}" 
Reply ONLY in JSON: {{"type_match": true/false, "weight_match": true/false, "variant_match": true/false, "comparable": true/false, "confidence": 0-100, "reason": "one sentence summary"}}'''
            
            res = get_gemini_json(prompt, gemini_key)
            time.sleep(0.2)
            
            if not res:
                continue
                
            conf = res.get("confidence", 0)
            status = ""
            
            if conf >= 85:
                status = "Approved"
            elif 50 <= conf < 85:
                status = "Pending"
            else:
                continue # Skip low confidence
                
            fields = {
                "Listing A": w_name,
                "Listing B": c_name,
                "AI confidence": conf,
                "Status": status,
                "Type match": bool(res.get("type_match")),
                "Weight match": bool(res.get("weight_match")),
                "Notes": res.get("reason", "")
            }
            
            try:
                match_table.create(fields)
                print(f"  [Match Queued] ({status} / {conf}%) '{w_name}' <=> '{c_name}'")
                total_queued += 1
            except Exception as e:
                print(f"  [Airtable Error] Failed: {e}")
            
            time.sleep(0.2)

    print(f"\n✅ Smart Pipeline completed. Total matches queued: {total_queued}")

if __name__ == "__main__":
    main()
