export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        // Enable CORS for frontend
        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        };

        if (request.method === 'OPTIONS') {
            return new Response(null, { headers: corsHeaders });
        }

        // -----------------------------------------------------
        // NEW ROUTE: /api/search (Combines Products + Listings)
        // -----------------------------------------------------
        if (url.pathname === '/api/search') {
            try {
                const query = url.searchParams.get('q');
                if (!query) {
                    return new Response(JSON.stringify({ error: "Missing query parameter 'q'" }), { status: 400, headers: corsHeaders });
                }

                // Synonyms logic natively inside the worker
                const SYNONYMS = {
                    'lf': 'lactose free',
                    'fc': 'full cream',
                    'cw': 'chemist warehouse',
                    'ww': 'woolworths'
                };

                // Build Airtable formula
                let terms = query.toLowerCase().split(' ').filter(t => t.trim().length > 0);
                terms = terms.map(t => SYNONYMS[t] ? SYNONYMS[t] : t);

                const conditions = terms.map(term => {
                    return `OR(FIND("\"${term}\"", LOWER({Product name}))>0, FIND("\"${term}\"", LOWER({Category}))>0)`;
                });
                const productFormula = conditions.length === 1 ? conditions[0] : `AND(${conditions.join(', ')})`;

                // 1. Query Products
                const productsUrl = `https://api.airtable.com/v0/${env.AIRTABLE_BASE_ID}/Products?filterByFormula=${encodeURIComponent(productFormula)}&maxRecords=100`;
                const productsRes = await fetch(productsUrl, {
                    headers: { 'Authorization': `Bearer ${env.AIRTABLE_TOKEN}` }
                });

                const productsData = await productsRes.json();
                const products = productsData.records;

                if (!products || products.length === 0) {
                    return new Response(JSON.stringify({ products: [] }), { headers: corsHeaders });
                }

                // 2. Fetch linked listings for all matched products
                const productIds = products.map(p => p.id);
                const chunkSize = 20; // Prevent URL too long errors
                const listingPromises = [];

                for (let i = 0; i < productIds.length; i += chunkSize) {
                    const chunk = productIds.slice(i, i + chunkSize);
                    const targetStr = chunk.map(id => `FIND("\"${id}\"", ARRAYJOIN({Product}))>0`).join(', ');
                    const listFormula = `OR(${targetStr})`;
                    const req = fetch(`https://api.airtable.com/v0/${env.AIRTABLE_BASE_ID}/Listings?fields%5B%5D=Store&fields%5B%5D=Price&fields%5B%5D=Product&filterByFormula=${encodeURIComponent(listFormula)}`, {
                        headers: { 'Authorization': `Bearer ${env.AIRTABLE_TOKEN}` }
                    });
                    listingPromises.push(req);
                }

                const listResponses = await Promise.all(listingPromises);
                let allListings = [];
                for (const res of listResponses) {
                    const data = await res.json();
                    if (data.records) allListings = allListings.concat(data.records);
                }

                // 3. Map Listings back to Products efficiently
                const productListingsMap = {};
                allListings.forEach(listRecord => {
                    const fields = listRecord.fields;
                    if (fields.Product && fields.Product.length > 0) {
                        fields.Product.forEach(pid => {
                            if (!productListingsMap[pid]) productListingsMap[pid] = [];
                            // Avoid store duplicates (e.g. if scraped multiple times without cleanup)
                            if (!productListingsMap[pid].find(l => l.store === fields.Store)) {
                                productListingsMap[pid].push({
                                    store: fields.Store,
                                    price: parseFloat(fields.Price)
                                });
                            }
                        });
                    }
                });

                // 4. Construct JSON Response exactly as specified
                const finalProducts = products.map(p => {
                    const fields = p.fields;
                    return {
                        id: p.id,
                        name: fields['Product name'] || 'Unknown Product',
                        size: fields['Weight / volume'] || '',
                        image: fields['Primary_Image'] || '',
                        prices: productListingsMap[p.id] || []
                    };
                }).filter(p => p.prices.length > 0); // Only return items that actually have valid pricing data

                return new Response(JSON.stringify({ products: finalProducts }), { headers: corsHeaders });
            } catch (err) {
                return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
            }
        }

        // -----------------------------------------------------
        // EXISTING ROUTE: Proxy Airtable safely (Backwards Compat)
        // -----------------------------------------------------
        if (url.pathname.startsWith('/api/airtable/')) {
            const path = url.pathname.replace('/api/airtable/', '');
            const airtableUrl = `https://api.airtable.com/v0/${env.AIRTABLE_BASE_ID}/${path}${url.search}`;

            const response = await fetch(airtableUrl, {
                headers: {
                    'Authorization': `Bearer ${env.AIRTABLE_TOKEN}`
                }
            });

            const data = await response.json();
            return new Response(JSON.stringify(data), { headers: corsHeaders });
        }

        // Fallback
        return new Response(JSON.stringify({ error: "Endpoint not found" }), { status: 404, headers: corsHeaders });
    }
};
