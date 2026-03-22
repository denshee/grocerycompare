import os
import re
import csv
from dotenv import load_dotenv
from pyairtable import Api

def extract_sizes(name):
    name = name.lower()
    name = re.sub(r'\bpack(?:s)?\b', 'pk', name)
    name = re.sub(r'\bpk\b', 'pk', name)
    name = re.sub(r'(\d+)\s*pk', r'\1pk', name)
    name = re.sub(r'(\d+)\s*(g|kg|ml|l|pk)\b', r'\1\2', name)
    
    sizes = set(re.findall(r'\b\d+(?:\.\d+)?(?:g|kg|ml|l|pk)\b', name))
    x_sizes = set(re.findall(r'\b\d+\s*x\s*\d+(?:\.\d+)?(?:g|kg|ml|l|pk)\b', name))
    
    return sizes.union(x_sizes)

def tokenize(name):
    words = re.findall(r'\b\w+\b', name.lower())
    stop_words = {"the", "and", "with", "woolworths", "coles", "fresh", "australian", "classic", "original", "natural", "for", "of", "in", "a"}
    return set([w for w in words if w not in stop_words])

def contains_variant(name, variant):
    return bool(re.search(r'\b' + re.escape(variant) + r'\b', name.lower()))

def main():
    load_dotenv()
    airtable_token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    print("Initializing Airtable connection...")
    api = Api(airtable_token)
    listings_table = api.table(base_id, "Listings")
    
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

    variants = [
        "lactose free", "skim", "low fat", "reduced fat", "light", 
        "almond", "oat", "soy", "organic", "a2", "long life", 
        "uht", "decaf", "instant", "wholegrain", "wholemeal", "gluten free",
        "zero", "diet", "unsweetened", "extra virgin", "lite", "rice"
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
    
    print("\nApplying Python pre-filter (2+ words, variant exclusions, size/weight match)...")
    for k in keywords:
        w_list = w_buckets[k]
        c_list = c_buckets[k]
        
        for w_item in w_list:
            w_words = tokenize(w_item)
            w_sizes = extract_sizes(w_item)
            
            for c_item in c_list:
                c_words = tokenize(c_item)
                
                # Minimum 2 shared words
                if len(w_words.intersection(c_words)) < 2:
                    continue
                    
                # Variant Exclusions
                rejected = False
                for v in variants:
                    if contains_variant(w_item, v) != contains_variant(c_item, v):
                        rejected = True
                        break
                if rejected:
                    continue
                    
                # Size/Weight match
                c_sizes = extract_sizes(c_item)
                if w_sizes and c_sizes:
                    if not w_sizes.intersection(c_sizes):
                        continue
                        
                candidates.append({
                    "listing_a": w_item,
                    "listing_b": c_item,
                    "category": k,
                    "comparable": "",
                    "confidence": "",
                    "reason": ""
                })

    print(f"Total valid candidate pairs generated: {len(candidates)}")
    
    # Export to CSV
    csv_file = "pairs_to_match.csv"
    with open(csv_file, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["listing_a", "listing_b", "category", "comparable", "confidence", "reason"])
        writer.writeheader()
        writer.writerows(candidates)
        
    print(f"✅ Successfully exported {len(candidates)} pairs to {csv_file}")

if __name__ == "__main__":
    main()
