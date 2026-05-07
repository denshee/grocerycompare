import csv
import re
import os

# Lead Data Engineer - Standalone Tagging Engine
# Mandate: Zero Sheets API connection, safe local file output.

INPUT_FILE = "products_export.csv"
OUTPUT_FILE = "vlookup_tags.csv"

STORE_BRANDS = [
    'coles', 'woolworths', 'aldi', 'macro', 'homebrand', 'essentials', 
    'farmdale', 'paddock', 'hill view', 'community co', 'chemist warehouse',
    'coles kitchen', 'woolworths essentials', 'macro organic', 'hillview'
]

def generate_grouping_tag(name):
    if not name:
        return "unknown"
    
    # 1. Lowercase
    tag = name.lower()
    
    # 2. Strip Store Proprietary Brands (Keep real brands like Milo/Cadbury)
    for brand in STORE_BRANDS:
        # Match brand at start or with space around it to avoid partial word matches
        tag = re.sub(rf'\b{brand}\b', '', tag)
    
    # 3. Standardize/Strip Weights and volumes (e.g. 2L, 1kg, 800g)
    # Matches numbers followed by units
    tag = re.sub(r'\d+(?:\.\d+)?\s*(kg|g|l|ml|pk|pack|ea|s|tabs|capsules|units|serves)', '', tag)
    
    # 4. Remove special characters (keep alphanumeric and spaces for now)
    tag = re.sub(r'[^a-z0-9 ]', ' ', tag)
    
    # 5. Collapse whitespace and trim
    tag = ' '.join(tag.split()).strip()
    
    # 6. Slugify (dash separated)
    tag = tag.replace(' ', '-')
    
    return tag

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found in current directory.")
        return

    print(f"Reading {INPUT_FILE}...")
    
    processed_count = 0
    with open(INPUT_FILE, 'r', encoding='utf-8') as fin, \
         open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as fout:
        
        reader = csv.DictReader(fin)
        fieldnames = ['Product_name', 'Grouping_Tag']
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in reader:
            p_name = row.get('Product_name')
            
            if not p_name:
                continue
            
            tag = generate_grouping_tag(p_name)
            
            writer.writerow({
                'Product_name': p_name,
                'Grouping_Tag': tag
            })
            processed_count += 1
            
    print(f"Success! {processed_count} tags generated and saved to {OUTPUT_FILE}.")
    print("You can now safely VLOOKUP this file into your Google Sheet.")

if __name__ == "__main__":
    main()
