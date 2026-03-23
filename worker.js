export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        };

        if (request.method === 'OPTIONS') {
            return new Response(null, { headers: corsHeaders });
        }

        // Hardcode the base ID as a fallback since it's not sensitive
        const BASE_ID = env.AIRTABLE_BASE_ID || "appryWRqjOFw4EajV";
        const TOKEN = env.AIRTABLE_TOKEN;

        // Debug route to check env vars are loaded
        if (url.pathname === '/api/debug') {
            return new Response(JSON.stringify({
                hasToken: !!TOKEN,
                tokenPrefix: TOKEN ? TOKEN.substring(0, 15) + "..." : "MISSING",
                baseId: BASE_ID,
            }), { headers: corsHeaders });
        }

        // /api/search
        if (url.pathname === '/api/search') {
            try {
                const query = url.searchParams.get('q');
                if (!query) {
                    return new Response(JSON.stringify({ error: "Missing query parameter 'q'" }), { status: 400, headers: corsHeaders });
                }

                const SYNONYMS = {
                    'lf': 'lactose free',
                    'fc': 'full cream',
                    'cw': 'chemist warehouse',
                    'ww': 'woolworths'
                };

                let terms = query.toLowerCase().split(' ').filter(t => t.trim().length > 0);
                terms = terms.map(t => SYNONYMS[t] ? SYNONYMS[t] : t);

                const conditions = terms.map(term => {
                    return `OR(FIND("${term}", LOWER({Product name}))>0, FIND("${term}", LOWER({Category}))>0)`;
                });
                const productFormula = conditions.length === 1 ? conditions[0] : `AND(${conditions.join(', ')})`;

                // 1. Fetch Products
                const productsUrl = `https://api.airtable.com/v0/${BASE_ID}/Products?filterByFormula=${encodeURIComponent(productFormula)}&maxRecords=100`;
                const productsRes = await fetch(productsUrl, {
                    headers: { 'Authorization': `Bearer ${TOKEN}` }
                });

                if (!productsRes.ok) {
                    const errText = await productsRes.text();
                    return new Response(JSON.stringify({ error: `Airtable Products error: ${productsRes.status}`, detail: errText }), { headers: corsHeaders });
                }

                const productsData = await productsRes.json();
                const products = productsData.records;

                if (!products || products.length === 0) {
                    return new Response(JSON.stringify({ products: [], debug: { formula: productFormula, baseId: BASE_ID } }), { headers: corsHeaders });
                }

                // 2. Fetch linked Listings
                const productIds = products.map(p => p.id);
                const chunkSize = 20;
                const listingPromises = [];

                for (let i = 0; i < productIds.length; i += chunkSize) {
                    const chunk = productIds.slice(i, i + chunkSize);
                    const targetStr = chunk.map(id => `FIND("${id}", ARRAYJOIN({Product}))>0`).join(', ');
                    const listFormula = `OR(${targetStr})`;
                    const req = fetch(`https://api.airtable.com/v0/${BASE_ID}/Listings?fields%5B%5D=Store&fields%5B%5D=Price&fields%5B%5D=Product&filterByFormula=${encodeURIComponent(listFormula)}`, {
                        headers: { 'Authorization': `Bearer ${TOKEN}` }
                    });
                    listingPromises.push(req);
                }

                const listResponses = await Promise.all(listingPromises);
                let allListings = [];
                for (const res of listResponses) {
                    const data = await res.json();
                    if (data.records) allListings = allListings.concat(data.records);
                }

                // 3. Map Listings to Products
                const productListingsMap = {};
                allListings.forEach(listRecord => {
                    const fields = listRecord.fields;
                    if (fields.Product && fields.Product.length > 0) {
                        fields.Product.forEach(pid => {
                            if (!productListingsMap[pid]) productListingsMap[pid] = [];
                            if (!productListingsMap[pid].find(l => l.store === fields.Store)) {
                                productListingsMap[pid].push({
                                    store: fields.Store,
                                    price: parseFloat(fields.Price)
                                });
                            }
                        });
                    }
                });

                // 4. Build response
                const finalProducts = products.map(p => ({
                    id: p.id,
                    name: p.fields['Product name'] || 'Unknown Product',
                    size: p.fields['Weight / volume'] || '',
                    image: p.fields['Primary_Image'] || '',
                    prices: productListingsMap[p.id] || []
                })).filter(p => p.prices.length > 0);

                return new Response(JSON.stringify({ products: finalProducts }), { headers: corsHeaders });

            } catch (err) {
                return new Response(JSON.stringify({ error: err.message, stack: err.stack }), { status: 500, headers: corsHeaders });
            }
        }

        // Existing proxy route
        if (url.pathname.startsWith('/api/airtable/')) {
            const path = url.pathname.replace('/api/airtable/', '');
            const airtableUrl = `https://api.airtable.com/v0/${BASE_ID}/${path}${url.search}`;
            const response = await fetch(airtableUrl, {
                headers: { 'Authorization': `Bearer ${TOKEN}` }
            });
            const data = await response.json();
            return new Response(JSON.stringify(data), { headers: corsHeaders });
        }

        return new Response(JSON.stringify({ error: "Endpoint not found" }), { status: 404, headers: corsHeaders });
    }
};
