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

        // Google Sheets config
        const SHEET_ID = env.GOOGLE_SHEET_ID || '14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k';
        const API_KEY = env.GOOGLE_API_KEY;   // Public read-only API key for Sheets v4

        /**
         * Fetch a range from Google Sheets v4 REST API.
         * Returns an array of row arrays (first row = headers).
         * Sheet must be publicly readable (Share → Anyone with link → Viewer).
         */
        async function fetchSheetRange(range) {
            const sheetsUrl = new URL(
                `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}/values/${encodeURIComponent(range)}`
            );
            sheetsUrl.searchParams.set('key', API_KEY);
            const res = await fetch(sheetsUrl.toString());
            if (!res.ok) {
                const err = await res.text();
                throw new Error(`Sheets API error ${res.status}: ${err}`);
            }
            const data = await res.json();
            return data.values || [];   // array of row arrays
        }

        /**
         * Parse the Listings sheet into an array of structured objects.
         * Columns: Listing_ID | Product_name | Store | Current_price | Regular_price | In_stock | Image_URL
         */
        function parseListings(rows) {
            if (rows.length < 2) return [];
            // row[0] is the header
            return rows.slice(1).map(row => ({
                listing_id: row[0] || '',
                product_name: row[1] || '',
                store: row[2] || '',
                current_price: parseFloat(row[3]) || null,
                regular_price: parseFloat(row[4]) || null,
                in_stock: (row[5] || '').toString().toLowerCase() !== 'false',
                image_url: row[6] || ''
            })).filter(r => r.product_name);
        }

        /**
         * Group flat listings by product name, building the same JSON shape
         * as the previous Airtable implementation:
         * { id, name, image, prices: [{ store, price, regular_price }] }
         */
        function groupByProduct(listings) {
            const map = new Map();
            for (const listing of listings) {
                const key = listing.product_name;
                if (!map.has(key)) {
                    map.set(key, {
                        id: key.toLowerCase().replace(/\s+/g, '-'),
                        name: listing.product_name,
                        image: listing.image_url,
                        prices: []
                    });
                }
                const product = map.get(key);
                // Keep the best image we have
                if (!product.image && listing.image_url) {
                    product.image = listing.image_url;
                }
                // Avoid duplicate store entries
                if (!product.prices.find(p => p.store === listing.store)) {
                    product.prices.push({
                        store: listing.store,
                        price: listing.current_price,
                        regular_price: listing.regular_price,
                        in_stock: listing.in_stock
                    });
                }
            }
            return [...map.values()];
        }

        // ── Debug endpoint ───────────────────────────────────────────────────────
        if (url.pathname === '/api/debug') {
            return new Response(JSON.stringify({
                sheetId: SHEET_ID,
                hasApiKey: !!API_KEY,
                apiKeyHint: API_KEY ? API_KEY.substring(0, 8) + '...' : 'MISSING'
            }), { headers: corsHeaders });
        }

        // ── Test endpoint — returns first 5 raw listings rows ────────────────────
        if (url.pathname === '/api/test') {
            try {
                const rows = await fetchSheetRange('Listings!A1:G6');
                return new Response(JSON.stringify({ rows }), { headers: corsHeaders });
            } catch (err) {
                return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
            }
        }

        // ── /api/search?q=milk ───────────────────────────────────────────────────
        if (url.pathname === '/api/search') {
            try {
                const query = url.searchParams.get('q');
                if (!query) {
                    return new Response(
                        JSON.stringify({ error: "Missing query parameter 'q'" }),
                        { status: 400, headers: corsHeaders }
                    );
                }

                // Synonym expansion
                const SYNONYMS = {
                    'lf': 'lactose free',
                    'fc': 'full cream',
                    'ww': 'woolworths'
                };
                const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
                    .map(t => SYNONYMS[t] ?? t);

                // Fetch the full Listings sheet (one API call)
                const rows = await fetchSheetRange('Listings!A:G');
                const allListings = parseListings(rows);

                // Filter: every search term must appear somewhere in the product name
                const matched = allListings.filter(listing => {
                    const haystack = listing.product_name.toLowerCase();
                    return terms.every(term => haystack.includes(term));
                });

                // Group into products with price comparisons
                const products = groupByProduct(matched)
                    .map(p => {
                        p.prices = p.prices.filter(pr => pr.store !== "Chemist Warehouse");
                        return p;
                    })
                    .filter(p => p.prices.length > 0)
                    // Sort: most stores (best comparison) first
                    .sort((a, b) => b.prices.length - a.prices.length);

                return new Response(JSON.stringify({
                    products,
                    debug: { query, terms, totalListings: allListings.length, matched: matched.length }
                }), { headers: corsHeaders });

            } catch (err) {
                return new Response(
                    JSON.stringify({ error: err.message, stack: err.stack }),
                    { status: 500, headers: corsHeaders }
                );
            }
        }

        // ── /api/price-history?product=X ─────────────────────────────────────────
        if (url.pathname === '/api/price-history') {
            try {
                const product = url.searchParams.get('product');
                if (!product) {
                    return new Response(
                        JSON.stringify({ error: "Missing 'product' parameter" }),
                        { status: 400, headers: corsHeaders }
                    );
                }

                // Fetch full history (Date | Product_name | Store | Price | Regular_price)
                const rows = await fetchSheetRange('Price_History!A:E');
                if (rows.length < 2) {
                    return new Response(JSON.stringify({ history: [], stats: {} }), { headers: corsHeaders });
                }

                // Filter by exact product name
                const history = rows.slice(1)
                    .filter(row => row[1] === product)
                    .map(row => ({
                        date: row[0],
                        store: row[2],
                        price: parseFloat(row[3]) || 0,
                        regular_price: parseFloat(row[4]) || null
                    }))
                    .sort((a, b) => new Date(a.date) - new Date(b.date));

                if (history.length === 0) {
                    return new Response(JSON.stringify({ history: [], stats: {} }), { headers: corsHeaders });
                }

                // Calculate stats per store
                const statsByStore = {};
                const stores = [...new Set(history.map(h => h.store))];

                for (const store of stores) {
                    const storeHistory = history.filter(h => h.store === store);
                    const prices = storeHistory.map(h => h.price).filter(p => p > 0);

                    const minPrice = Math.min(...prices);
                    const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;

                    // Trend: Compare last 2 unique points for this store
                    let trend = 'stable';
                    let pctChange = 0;
                    if (storeHistory.length >= 2) {
                        const last = storeHistory[storeHistory.length - 1].price;
                        const prev = storeHistory[storeHistory.length - 2].price;
                        if (last > prev) {
                            trend = 'up';
                            pctChange = ((last - prev) / prev) * 100;
                        } else if (last < prev) {
                            trend = 'down';
                            pctChange = ((prev - last) / prev) * 100;
                        }
                    }

                    statsByStore[store] = {
                        min_price: minPrice,
                        avg_price: parseFloat(avgPrice.toFixed(2)),
                        current_price: storeHistory[storeHistory.length - 1].price,
                        trend,
                        pct_change: parseFloat(pctChange.toFixed(1))
                    };
                }

                return new Response(JSON.stringify({
                    product,
                    history,
                    stats: statsByStore
                }), { headers: corsHeaders });

            } catch (err) {
                return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
            }
        }

        // ── /api/list/compare (POST) ─────────────────────────────────────────────
        if (url.pathname === '/api/list/compare') {
            if (request.method !== 'POST') {
                return new Response(JSON.stringify({ error: 'Method not allowed. Use POST.' }), { status: 405, headers: corsHeaders });
            }

            try {
                const body = await request.json();
                const productQueries = body.products || [];
                if (!Array.isArray(productQueries) || productQueries.length === 0) {
                    return new Response(JSON.stringify({ error: 'Invalid or empty products list' }), { status: 400, headers: corsHeaders });
                }

                // Fetch full Listings
                const rows = await fetchSheetRange('Listings!A:G');
                const allListings = parseListings(rows);
                const grouped = groupByProduct(allListings);

                const stores = [...new Set(allListings.map(l => l.store))].filter(s => s !== "Chemist Warehouse");
                const breakdown = [];
                const totals = {};
                const missingCount = {};

                stores.forEach(s => {
                    totals[s] = 0;
                    missingCount[s] = 0;
                });

                for (const query of productQueries) {
                    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);

                    // Fuzzy Match Scoring System
                    const matches = grouped.map(p => {
                        const name = p.name.toLowerCase();
                        let score = 0;

                        // Every term must be included
                        if (!terms.every(t => name.includes(t))) return null;

                        // Bonus if name starts with first query term
                        if (name.startsWith(terms[0])) score += 10;

                        // Bonus for word boundaries (exact word match vs substring)
                        terms.forEach(t => {
                            if (new RegExp(`\\b${t}\\b`).test(name)) score += 5;
                        });

                        // Penalize length (prefer shorter specific matches)
                        score -= (name.length / 10);

                        return { product: p, score };
                    })
                        .filter(m => m !== null)
                        .sort((a, b) => b.score - a.score);

                    const bestMatch = matches[0]?.product;
                    const pricesObj = {};

                    if (bestMatch) {
                        stores.forEach(store => {
                            const storePrice = bestMatch.prices.find(p => p.store === store);
                            if (storePrice && storePrice.price > 0 && storePrice.in_stock !== false) {
                                pricesObj[store] = storePrice.price;
                                totals[store] += storePrice.price;
                            } else {
                                pricesObj[store] = null;
                                missingCount[store]++;
                            }
                        });

                        // Find cheapest store for this item
                        const validStores = Object.entries(pricesObj).filter(([_, p]) => p !== null);
                        let cheapestStore = null;
                        if (validStores.length > 0) {
                            cheapestStore = validStores.reduce((a, b) => a[1] < b[1] ? a : b)[0];
                        }

                        breakdown.push({
                            query,
                            product: bestMatch.name,
                            prices: pricesObj,
                            cheapest: cheapestStore
                        });
                    } else {
                        // Product not found at all
                        breakdown.push({
                            query,
                            product: null,
                            prices: stores.reduce((acc, s) => ({ ...acc, [s]: null }), {}),
                            cheapest: null
                        });
                        stores.forEach(s => missingCount[s]++);
                    }
                }

                // Nullify totals for stores that have any missing items (to match "Not available" requirement)
                const finalTotals = {};
                const unavailable = [];
                let cheapestOverallStore = null;
                let minTotal = Infinity;

                stores.forEach(s => {
                    if (missingCount[s] > 0) {
                        finalTotals[s] = null;
                        unavailable.push(s);
                    } else {
                        finalTotals[s] = parseFloat(totals[s].toFixed(2));
                        if (finalTotals[s] < minTotal) {
                            minTotal = finalTotals[s];
                            cheapestOverallStore = s;
                        }
                    }
                });

                // Calculate savings (Difference between cheapest and next cheapest or average)
                const validTotals = Object.values(finalTotals).filter(t => t !== null).sort((a, b) => a - b);
                let savings = 0;
                if (validTotals.length >= 2) {
                    savings = parseFloat((validTotals[1] - validTotals[0]).toFixed(2));
                }

                return new Response(JSON.stringify({
                    totals: finalTotals,
                    cheapest_store: cheapestOverallStore,
                    savings: savings,
                    breakdown,
                    unavailable
                }), { headers: corsHeaders });

            } catch (err) {
                return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
            }
        }

        return new Response(JSON.stringify({ error: 'Endpoint not found' }), { status: 404, headers: corsHeaders });
    }
};
