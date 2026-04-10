import os
import csv
from pyairtable import Api

# Load credentials
AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN')  # Set via environment variable or .env file
BASE_ID = 'appryWRqjOFw4EajV'

api = Api(AIRTABLE_TOKEN)
base = api.base(BASE_ID)

# Export Products
print("Exporting Products...")
products_table = base.table('Products')
products = products_table.all()

with open('products_export.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Product_ID', 'Product_name', 'Category', 'Weight_volume', 'Primary_Image'])
    for record in products:
        fields = record['fields']
        writer.writerow([
            record['id'],
            fields.get('Product name', ''),
            fields.get('Category', ''),
            fields.get('Weight / volume', ''),
            fields.get('Primary_Image', '')
        ])

print(f"Exported {len(products)} products to products_export.csv")

# Export Listings
print("Exporting Listings...")
listings_table = base.table('Listings')
listings = listings_table.all()

with open('listings_export.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Listing_ID', 'Product_name', 'Store', 'Current_price', 'Regular_price', 'In_stock', 'Image_URL'])
    for record in listings:
        fields = record['fields']
        writer.writerow([
            record['id'],
            fields.get('Listing name', ''),
            fields.get('Store', ''),
            fields.get('Current price', ''),
            fields.get('Regular price', ''),
            fields.get('In stock', False),
            fields.get('Image URL', '')
        ])

print(f"Exported {len(listings)} listings to listings_export.csv")
print("Export complete!")
