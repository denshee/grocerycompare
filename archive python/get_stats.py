import sheets_helper
ws = sheets_helper.get_listings_worksheet()
rows = ws.get_all_values()
print(f'Total Listings: {len(rows)-1}')
stores = {}
for r in rows[1:]:
    store = r[2] if len(r) > 2 else 'Unknown'
    stores[store] = stores.get(store, 0) + 1
print('By Store:')
for k, v in sorted(stores.items()):
    print(f'  {k}: {v}')
