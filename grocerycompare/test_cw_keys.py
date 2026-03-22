import requests, json

headers = {
    'x-algolia-api-key': '3ce54af79eae81a18144a7aa7ee10ec2', 
    'x-algolia-application-id': '42NP1V2I98', 
    'Content-Type': 'application/json'
}
payload = {
    'requests':[{'indexName':'prod_cwr-cw-au_products_en', 'params':'query=milk&page=0&hitsPerPage=1'}]
}
res = requests.post('https://42np1v2i98-dsn.algolia.net/1/indexes/*/queries', json=payload, headers=headers)
hit = res.json()['results'][0]['hits'][0]

for k in hit.keys():
    if "image" in k.lower() or "pic" in k.lower() or "url" in k.lower():
        print(f"IMAGE KEY: {k} -> {hit[k]}")

cats = hit.get('categories', {})
print("CATS:", json.dumps(cats, indent=2))
