import os, re
from dotenv import load_dotenv
from pyairtable import Api

def get_keywords(name):
    return set(re.findall(r'\b\w+\b', name.lower()))

load_dotenv()
api = Api(os.environ.get("AIRTABLE_TOKEN"))
records = api.table(os.environ.get("AIRTABLE_BASE_ID"), "Listings").all()

woolies = [r["fields"]["Listing name"] for r in records if r["fields"].get("Store") == "Woolworths"]
coles = [r["fields"]["Listing name"] for r in records if r["fields"].get("Store") == "Coles"]

keywords = ["milk", "bread", "eggs", "butter", "cheese", "yoghurt", "chicken", "beef", "rice", "pasta", "cereal", "juice", "chips", "chocolate", "coffee", "tea", "toilet paper", "dishwashing"]

with open("counts.txt", "w", encoding="utf-8") as f:
    f.write("--- Smart Filtering Phase ---\n")
    total_raw = 0
    total_short = 0

    for k in keywords:
        w_list = [n for n in woolies if k in n.lower()]
        c_list = [n for n in coles if k in n.lower()]
        raw = len(w_list) * len(c_list)
        short = 0
        for w in w_list:
            for c in c_list:
                if len(get_keywords(w).intersection(get_keywords(c))) >= 2:
                    short += 1
        f.write(f"Bucket '{k}': {raw} raw comparisons -> {short} shortlisted pairs\n")
        total_raw += raw
        total_short += short

    f.write(f"\nTotal raw comparisons eliminated: {total_raw} -> {total_short}\n")
