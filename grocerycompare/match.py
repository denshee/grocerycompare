import os
import re
import time
import json
import requests
import datetime
from dotenv import load_dotenv
from pyairtable import Api

def get_gemini_json(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a grocery product matching assistant. Reply purely in valid JSON formatting."}]
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
            if attempt < 2:
                time.sleep(5)
            else:
                print(f"  [Gemini Exhausted 3 Retries] Error: {e}")
                
    return None

def tokenize(name):
    words = re.findall(r'\b\w+\b', name.lower())
    stop_words = {"the", "and", "with", "woolworths", "coles", "fresh", "australian", "classic", "original", "natural", "for", "of"}
    return set([w for w in words if w not in stop_words])

def main():
    load_dotenv()
    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not airtable_token or not base_id or not gemini_key:
        print("Missing required environment variables in .env.")
        return

    progress_file = "match_progress.json"
    completed_pairs = set()
    
    if os.path.exists(progress_file):
        print(f"Loading progress from {progress_file}...")
        try:
            with open(progress_file, "r") as f:
                progress_data = json.load(f)
                for item in progress_data:
                    completed_pairs.add(f'{item["w"]}|{item["c"]}')
            print(f"Loaded {len(completed_pairs)} previously evaluated pairs.")
        except json.JSONDecodeError:
            print("Corrupted progress file. Starting fresh.")
    else:
        # Initialize an empty progress JSON list
        with open(progress_file, "w") as f:
            json.dump([], f)

    print("Initializing Airtable connection...")
    api = Api(airtable_token)
    listings_table = api.table(base_id, "Listings")
    match_table = api.table(base_id, "Match Queue")

    if not completed_pairs:
        print("Clearing existing Match Queue records for a fresh run...")
        to_delete = match_table.all()
        if to_delete:
            delete_ids = [r["id"] for r in to_delete]
            for i in range(0, len(delete_ids), 10):
                match_table.batch_delete(delete_ids[i:i+10])
            print(f"Deleted {len(delete_ids)} old match records.")
    
    print("Fetching all listings...")
    records = listings_table.all()

    woolies = []
    coles = []

    for r in records:
        fields = r.get("fields", {})
        store = fields.get("Store")
        name = fields.get("Listing name", "").strip()
        if not name: continue
        
        if store == "Woolworths":
            woolies.append(name)
        elif store == "Coles":
            coles.append(name)

    keywords = [
        "milk", "bread", "eggs", "butter", "cheese", "yoghurt", 
        "chicken", "beef", "rice", "pasta", "cereal", "juice", 
        "chips", "chocolate", "coffee", "tea", "toilet paper", "dishwashing"
    ]

    w_buckets = {k: [] for k in keywords}
    c_buckets = {k: [] for k in keywords}

    def assign_to_bucket(name, buckets):
        low = name.lower()
        for k in keywords:
            if k in low:
                buckets[k].append(name)
                return True
        return False

    for w in woolies: assign_to_bucket(w, w_buckets)
    for c in coles: assign_to_bucket(c, c_buckets)

    candidates = []
    
    print("\nPhase 1: Python pre-filter (no API calls)")
    for k in keywords:
        w_list = w_buckets[k]
        c_list = c_buckets[k]
        
        for w_item in w_list:
            w_words = tokenize(w_item)
            for c_item in c_list:
                c_words = tokenize(c_item)
                shared = len(w_words.intersection(c_words))
                if shared >= 2:
                    candidates.append((w_item, c_item))

    print(f"Found {len(candidates)} total candidate pairs across all categories.")
    
    candidates_to_process = []
    for w_item, c_item in candidates:
        if f'{w_item}|{c_item}' not in completed_pairs:
            candidates_to_process.append((w_item, c_item))
            
    print(f"Remaining pairs to process: {len(candidates_to_process)}")
    print("\nPhase 2 & 3: Gemini 2.0 making every match decision & Routing")
    
    total_queued = 0
    total_evaluated = 0
    total_timeout = 0
    
    start_time = time.time()
    
    def save_progress(w_name, c_name):
        try:
            with open(progress_file, "r") as f:
                data = json.load(f)
        except:
            data = []
        data.append({"w": w_name, "c": c_name})
        with open(progress_file, "w") as f:
            json.dump(data, f)
            
    all_matches_to_push = []

    for idx, (w_name, c_name) in enumerate(candidates_to_process):
        # Calculate ETA
        elapsed = time.time() - start_time
        avg_time_per_pair = elapsed / idx if idx > 0 else 15.0
        pairs_left = len(candidates_to_process) - idx
        eta_seconds = pairs_left * avg_time_per_pair
        eta_str = str(datetime.timedelta(seconds=int(eta_seconds)))
        
        if idx % 10 == 0 or idx < 5:
            print(f"Processing candidate pair {idx + 1} / {len(candidates_to_process)}... (ETA: {eta_str})")
            
        prompt = f'''You are a grocery product matching assistant for a price comparison app. Your job is to determine if two products are genuinely the same product sold at different stores — meaning a customer shopping for one would be equally happy buying the other.
Product A: {w_name}
Product B: {c_name}
Evaluate strictly on these criteria:

Same product type (e.g. both full cream milk, not one lactose free and one regular)
Same variant (e.g. both wholemeal, both skim, both organic — any variant present in one must be present in the other)
Same or comparable size/weight (e.g. 2L vs 2L is fine, 2L vs 1L is not)
Same format (e.g. a 4-finger bar vs a 12-pack multibox are NOT comparable even if same brand)
Would a customer feel deceived if they searched for Product A and were shown Product B's price instead?
Reply ONLY in JSON: {{"comparable": true/false, "confidence": 0-100, "reason": "one sentence explaining your decision"}}'''

        res = get_gemini_json(prompt, gemini_key)
        
        # 15 second delay mandated strictly to bypass free tier
        time.sleep(15)
        save_progress(w_name, c_name)
        
        if not res:
            total_timeout += 1
            print(f"  [Gemini Rate Limit Failed] {w_name} <=> {c_name}")
            continue
            
        total_evaluated += 1
        comparable = bool(res.get("comparable"))
        conf = res.get("confidence", 0)
        reason = res.get("reason", "")
        
        if comparable and conf >= 90:
            status = "Approved"
        elif comparable and 70 <= conf <= 89:
            status = "Pending"
        else:
            continue
            
        match_obj = {
            "Listing A": w_name,
            "Listing B": c_name,
            "AI confidence": conf,
            "Status": status,
            "Notes": reason
        }
        all_matches_to_push.append(match_obj)
        print(f"  [Queued - {status} {conf}%] {w_name} <=> {c_name} | {reason}")
        
        if len(all_matches_to_push) >= 5:
            try:
                match_table.batch_create(all_matches_to_push)
                total_queued += len(all_matches_to_push)
                all_matches_to_push = []
            except Exception as e:
                print(f"Batch push error: {e}")

    if all_matches_to_push:
        try:
            match_table.batch_create(all_matches_to_push)
            total_queued += len(all_matches_to_push)
        except Exception as e:
            print(f"Batch push error: {e}")

    print(f"\n✅ Supreme Pipeline completed. Total trusted matches approved/pending: {total_queued}")
    
    print("\n=== EXECUTION SUMMARY ===")
    print(f"Total API Calls Evaluated: {total_evaluated}")
    print(f"Total API Calls Timed Out: {total_timeout}")
    print(f"Total Matches Queued: {total_queued}")

if __name__ == "__main__":
    main()
