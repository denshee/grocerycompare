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

        const BASE_ID = env.AIRTABLE_BASE_ID || "appryWRqjOFw4EajV";
        const TOKEN = env.AIRTABLE_TOKEN;

        // Debug endpoint
        if (url.pathname === '/api/debug') {
            return new Response(JSON.stringify({
                hasToken: !!TOKEN,
                tokenPrefix: TOKEN ? TOKEN.substring(0, 15) + "..." : "MISSING",
                baseId: BASE_ID,
            }), { headers: corsHeaders });
        }

        // Test endpoint — returns raw Airtable response for hardcoded "milk" search
        if (url.pathname === '/api/test') {
            const formula = 'OR(SEARCH("milk",LOWER({Product name})),SEARCH("milk",LOWER({Category})))';
            const testUrl = new URL('https://api.airtable.com/v0/' + BASE_ID + '/Products');
            testUrl.searchParams.set('filterByFormula', formula);
            testUrl.searchParams.set('maxRecords', '3');
            const res = await fetch(testUrl.toString(), { headers: { 'Authorization': 'Bearer ' + TOKEN } });
            const raw = await res.text();
            return new Response(JSON.stringify({
                status: res.status,
                formula: formula,
                encodedUrl: testUrl.toString(),
                raw: raw.substring(0, 2000)
            }), { headers: corsHeaders });
        }

        // /api/search?q=milk
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

                // Build formula using SEARCH() which doesn't require field name quoting issues
                // Use string concatenation instead of template literals to avoid encoding problems
                const conditions = terms.map(term => {
                    return 'SEARCH("' + term + '", LOWER({Product name})) > 0';
                });
                const productFormula = conditions.length === 1
                    ? conditions[0]
                    : 'AND(' + conditions.join(',') + ')';

                // Build URL manually to control encoding precisely
                // Airtable needs the formula URL-encoded but NOT double-encoded
                const productsUrl = new URL('https://api.airtable.com/v0/' + BASE_ID + '/Products');
                productsUrl.searchParams.set('filterByFormula', productFormula);
                productsUrl.searchParams.set('maxRecords', '100');

                const productsRes = await fetch(productsUrl.toString(), {
                    headers: { 'Authorization': 'Bearer ' + TOKEN }
                });

                if (!productsRes.ok) {
                    const errText = await productsRes.text();
                    return new Response(JSON.stringify({
                        error: 'Airtable Products error: ' + productsRes.status,
                        detail: errText,
                        formula: productFormula
                    }), { headers: corsHeaders });
                }

                const productsData = await productsRes.json();
                const products = productsData.records;

                if (!products || products.length === 0) {
                    return new Response(JSON.stringify({
                        products: [],
                        debug: { formula: productFormula, baseId: BASE_ID }
                    }), { headers: corsHeaders });
                }

                // Fetch linked Listings in parallel chunks
                const productIds = products.map(p => p.id);
                const chunkSize = 20;
                const listingPromises = [];

                for (let i = 0; i < productIds.length; i += chunkSize) {
                    const chunk = products.slice(i, i + chunkSize);
                    const targetStr = chunk.map(p => 'FIND("' + p.fields['Product name'] + '",ARRAYJOIN({Product}))>0').join(',');
                    const listFormula = 'OR(' + targetStr + ')';

                    const listUrl = new URL('https://api.airtable.com/v0/' + BASE_ID + '/Listings');
                    listUrl.searchParams.set('filterByFormula', listFormula);
                    listUrl.searchParams.set('fields[]', 'Store');
                    listUrl.searchParams.append('fields[]', 'Current price');
                    listUrl.searchParams.append('fields[]', 'Product');

                    listingPromises.push(
                        fetch(listUrl.toString(), { headers: { 'Authorization': 'Bearer ' + TOKEN } })
                    );
                }

                const listResponses = await Promise.all(listingPromises);
                let allListings = [];
                for (const res of listResponses) {
                    const data = await res.json();
                    if (data.records) allListings = allListings.concat(data.records);
                }

                // Map listings to products
                const productListingsMap = {};
                allListings.forEach(listRecord => {
                    const fields = listRecord.fields;
                    if (fields.Product && fields.Product.length > 0) {
                        fields.Product.forEach(pid => {
                            if (!productListingsMap[pid]) productListingsMap[pid] = [];
                            if (!productListingsMap[pid].find(l => l.store === fields.Store)) {
                                productListingsMap[pid].push({
                                    store: fields.Store,
                                    price: parseFloat(fields['Current price'])
                                });
                            }
                        });
                    }
                });

                const finalProducts = products.map(p => ({
                    id: p.id,
                    name: p.fields['Product name'] || 'Unknown Product',
                    size: p.fields['Weight / volume'] || '',
                    image: p.fields['Primary_Image'] || '',
                    prices: productListingsMap[p.id] || []
                })).filter(p => p.prices.length > 0);

                return new Response(JSON.stringify({ products: finalProducts, debug: { formula: productFormula, baseId: BASE_ID } }), { headers: corsHeaders });

            } catch (err) {
                return new Response(JSON.stringify({ error: err.message, stack: err.stack }), { status: 500, headers: corsHeaders });
            }
        }

        // Legacy proxy: /api/airtable/*
        if (url.pathname.startsWith('/api/airtable/')) {
            const path = url.pathname.replace('/api/airtable/', '');
            const airtableUrl = 'https://api.airtable.com/v0/' + BASE_ID + '/' + path + url.search;
            const response = await fetch(airtableUrl, {
                headers: { 'Authorization': 'Bearer ' + TOKEN }
            });
            const data = await response.json();
            return new Response(JSON.stringify(data), { headers: corsHeaders });
        }

        return new Response(JSON.stringify({ error: "Endpoint not found" }), { status: 404, headers: corsHeaders });
    }
};
