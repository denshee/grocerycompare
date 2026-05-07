export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Standard CORS Headers for all responses
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    };

    // 1. Handle CORS Preflight (OPTIONS)
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // Comprehensive Helper for JSON responses with CORS
    const jsonResponse = (data, status = 200) => {
      return new Response(JSON.stringify(data), {
        status,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    };

    // Google Apps Script Proxy Endpoint
    const DB_URL = "https://script.google.com/macros/s/AKfycbyO_7q8o_1o-6n-8x2x7m7o-8q-8q-8q-8q/exec";

    try {
      // PRESERVED SEARCH LOGIC (UPGRADED TO KV)
      if (url.pathname === '/api/search') {
        const query = url.searchParams.get('q')?.toLowerCase() || "";
        if (!query) return jsonResponse({ error: "Missing query parameter 'q'" }, 400);

        try {
          // Fetch raw rows from Listings including Column H (index 7)
          const rows = await fetchSheetRange('Listings!A:H');
          const allListings = parseListings(rows);
          
          const exclusions = {
            'eggs': ['chocolate', 'easter', 'bunny', 'hollow', 'cadbury'],
            'meat': ['dog', 'cat', 'pet', 'puppy', 'kitten', 'pedigree', 'optimum', 'dine'],
            'seafood': ['cat', 'pet', 'dine', 'felix'],
            'milk': ['chocolate', 'strawberry', 'powder', 'dog', 'cat'],
            'oat': ['goat', 'soap', 'body', 'wash', 'cheese']
          };
          const terms = query.split(/\s+/).filter(Boolean);

          let activeExclusions = [];
          for (const [key, words] of Object.entries(exclusions)) {
              if (terms.includes(key)) activeExclusions.push(...words);
          }

          const matched = allListings.filter(listing => {
              const haystack = listing.product_name.toLowerCase();
              if (!terms.every(term => haystack.includes(term))) return false;

              for (const ex of activeExclusions) {
                  // Only exclude if the search term itself wasn't the exclusion word
                  if (haystack.includes(ex) && !terms.includes(ex)) return false;
              }
              return true;
          });

          // Group products using Comparison_Key priority
          const grouped = groupByProduct(matched).sort((a, b) => Object.keys(b.prices).length - Object.keys(a.prices).length);
          
          return jsonResponse({ products: grouped });
        } catch (err) {
          return jsonResponse({ error: `Search Failure: ${err.message}` }, 500);
        }
      }

      // PRESERVED PRICE HISTORY LOGIC (PHASE 2 UPGRADE)
      if (url.pathname === '/api/price-history') {
        const productQuery = url.searchParams.get('product');
        if (!productQuery) return jsonResponse({ error: "Missing 'product' parameter" }, 400);

        // Fetch from Google Sheets via public visualization API
        const SHEET_ID = "14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k";
        const historyUrl = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:json&sheet=Price_History&range=A:E`;
        
        try {
          const response = await fetch(historyUrl);
          const text = await response.text();
          // Extract JSON from Google's response wrapper
          const startIdx = text.indexOf('{');
          const endIdx = text.lastIndexOf('}') + 1;
          const data = JSON.parse(text.substring(startIdx, endIdx));

          const allRows = data.table.rows.map(r => ({
            timestamp: r.c[0]?.v,
            product_name: r.c[1]?.v,
            store: r.c[2]?.v,
            price: r.c[3]?.v,
            was_price: r.c[4]?.v
          }));

          // Filter by product name (case-insensitive)
          const filtered = allRows.filter(r => 
            r.product_name && r.product_name.toLowerCase().includes(productQuery.toLowerCase())
          );

          if (filtered.length === 0) {
            return jsonResponse({ history: [], stats: { min_price: null, avg_price: null, trend: 0 } });
          }

          // Calculate Stats
          const validPrices = filtered.map(r => r.price).filter(p => typeof p === 'number' && p > 0);
          const min_price = validPrices.length ? Math.min(...validPrices) : null;
          const avg_price = validPrices.length ? (validPrices.reduce((a, b) => a + b, 0) / validPrices.length) : null;
          
          let trend = 0;
          if (validPrices.length >= 2) {
            const last = validPrices[validPrices.length - 1];
            const prev = validPrices[validPrices.length - 2];
            trend = ((last - prev) / prev) * 100;
          }

          return jsonResponse({
            history: filtered,
            stats: {
              min_price: min_price ? parseFloat(min_price.toFixed(2)) : null,
              avg_price: avg_price ? parseFloat(avg_price.toFixed(2)) : null,
              trend: parseFloat(trend.toFixed(1))
            }
          });
        } catch (fetchErr) {
          return jsonResponse({ error: `Failed to fetch history: ${fetchErr.message}` }, 500);
        }
      }

      // NEW: SAVE LIST ENDPOINT (KV Persistent Storage)
      if (url.pathname === '/api/save-list' && request.method === 'POST') {
        try {
          const listData = await request.json();
          const listID = Math.random().toString(36).substring(2, 8).toUpperCase();

          if (!env.GROCERY_LISTS) {
            return jsonResponse({ success: false, error: "KV Namespace GROCERY_LISTS not bound" }, 500);
          }

          // Persist to KV with 7-day TTL
          await env.GROCERY_LISTS.put(listID, JSON.stringify(listData), { expirationTtl: 604800 });
          return jsonResponse({ success: true, listID });
        } catch (kvErr) {
          return jsonResponse({ success: false, error: `Cloud Storage Failure: ${kvErr.message}` }, 500);
        }
      }

      // NEW: RETRIEVE LIST ENDPOINT
      if (url.pathname.startsWith('/api/list/')) {
        const listID = url.pathname.split('/').pop().toUpperCase();

        if (!env.GROCERY_LISTS) {
          return jsonResponse({ success: false, error: "KV Namespace GROCERY_LISTS not bound" }, 500);
        }

        const stored = await env.GROCERY_LISTS.get(listID);
        if (!stored) {
          return jsonResponse({ success: false, error: "Shared list not found" }, 404);
        }

        return jsonResponse({ success: true, items: JSON.parse(stored) });
      }

      // NEW: MARKET SYNC ENDPOINT (Automated Data Pipeline)
      if (url.pathname === '/api/sync' && request.method === 'PUT') {
        const auth = request.headers.get("Authorization");
        if (auth !== "your_secret_auth_key") { // Placeholder Auth
          return jsonResponse({ success: false, error: "Unauthorized" }, 401);
        }

        try {
          const marketData = await request.json();
          if (!env.MARKET_DATA) {
            return jsonResponse({ success: false, error: "KV Namespace MARKET_DATA not bound" }, 500);
          }

          // Persist the full market snapshot to KV
          await env.MARKET_DATA.put("latest_snapshot", JSON.stringify(marketData));
          return jsonResponse({ success: true, message: "Market data synchronized" });
        } catch (syncErr) {
          return jsonResponse({ success: false, error: `Sync Failure: ${syncErr.message}` }, 500);
        }
      }

      // NEW: CATALOG ENDPOINT (For Auto-Suggest)
      if (url.pathname === '/api/catalog') {
        try {
          const rawData = await fetchSheetRange('Products!B:B');
          const catalog = [...new Set(
            rawData.flat()
              .slice(1) 
              .map(item => String(item || "").trim())
              .filter(item => item.length > 0)
          )].sort();
          return jsonResponse({ catalog });
        } catch (catErr) {
          return jsonResponse({ error: `Catalog Fetch Failure: ${catErr.message}` }, 500);
        }
      }

      // Default route
      return new Response("Not Found", { status: 404, headers: corsHeaders });

    } catch (err) {
      // Global error handler with CORS support
      return jsonResponse({ success: false, error: `Internal Server Error: ${err.message}` }, 500);
    }
  },
};

async function fetchSheetRange(rangeString) {
  const SHEET_ID = "14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k";
  
  // 1. Explicitly separate Sheet Name and Range for accurate routing
  const parts = rangeString.split('!');
  const sheet = parts.length > 1 ? parts[0] : '';
  const range = parts.length > 1 ? parts[1] : rangeString;
  
  let url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:json&range=${encodeURIComponent(range)}`;
  if (sheet) {
    url += `&sheet=${encodeURIComponent(sheet)}`;
  }

  const response = await fetch(url);
  const text = await response.text();
  
  // Extract JSON from Google's response wrapper
  const startIdx = text.indexOf('{');
  const endIdx = text.lastIndexOf('}') + 1;
  const data = JSON.parse(text.substring(startIdx, endIdx));
  
  // 2. Fix the Mixed-Datatype Bug: Fallback to cell.f (formatted text) if cell.v is null
  return data.table.rows.map(r => r.c.map(cell => {
    if (!cell) return null;
    return cell.v !== null ? cell.v : cell.f;
  }));
}

/**
 * Fuzzy Identity Engine
 * Strips brands and weights to create a "Canonical ID" for grouping.
 */
function getCanonicalId(name) {
  if (!name) return "unknown";
  let n = name.toLowerCase();

  // 1. Commodity Override (Forces identical commodities together regardless of brand)
  if (n.includes('eggs')) {
      let type = n.includes('free range') ? 'freerange' : (n.includes('cage free') ? 'cagefree' : 'standard');
      let count = n.match(/\b(6|10|12|18|24|30)\b/) ? n.match(/\b(6|10|12|18|24|30)\b/)[0] + 'pk' : 'std';
      let weight = n.match(/\b\d+g\b/) ? n.match(/\b\d+g\b/)[0] : '';
      return `eggs-${type}-${count}-${weight}`.replace(/-+/g, '-').replace(/-$/, '');
  }

  // 2. Standard Fuzzy Logic
  const brands = ['coles', 'woolworths', 'aldi', 'select', 'paddock', 'market', 'brand', 'australian', 'essentials', 'macro', 'sunny queen', 'pace farm', 'manning valley'];
  brands.forEach(b => n = n.replace(new RegExp(`\\b${b}\\b`, 'g'), ''));
  
  const sizeMatch = n.match(/\d+(\.\d+)?\s*(l|ml|g|kg|pk|pack|ea|s|tabs|capsules)/i);
  const size = sizeMatch ? sizeMatch[0].toLowerCase().replace(/\s/g, '') : "std";
  
  const clean = n.replace(/[^a-z0-9 ]/g, ' ').trim();
  const words = clean.split(/\s+/).filter(w => w.length > 1);
  const core = words.slice(0, 3).join('-');
  
  return `${core}-${size}`.replace(/-+/g, '-');
}

function parseListings(rows) {
  if (rows.length < 2) return [];
  return rows.slice(1).map(row => ({
    listing_id: row[0] || "",
    product_name: row[1] || "",
    store: row[2] || "",
    current_price: parseFloat(String(row[3]).replace(/[^\d.]/g, '')) || 0,
    regular_price: parseFloat(String(row[4]).replace(/[^\d.]/g, '')) || 0,
    in_stock: (row[5] || "").toString().toLowerCase() !== "false",
    image_url: row[6] || "",
    comparison_key: row[7] ? row[7].toString().trim() : '',
  })).filter(r => r.product_name);
}

function groupByProduct(listings) {
  const map = new Map();
  for (const listing of listings) {
    // Priority: Comparison_Key (H) > fuzzy getCanonicalId
    let canonId = listing.comparison_key || getCanonicalId(listing.product_name);
    
    // SUPREME COMMODITY OVERRIDE: Ignore database tags for eggs and force functional grouping
    const n = listing.product_name.toLowerCase();
    if (n.includes('eggs')) {
      let type = n.includes('free range') ? 'freerange' : (n.includes('cage free') ? 'cagefree' : 'standard');
      let count = n.match(/\b(6|10|12|18|24|30)\b/) ? n.match(/\b(6|10|12|18|24|30)\b/)[0] + 'pk' : 'std';
      let weight = n.match(/\b\d+g\b/) ? n.match(/\b\d+g\b/)[0] : '';
      canonId = `eggs-${type}-${count}-${weight}`.replace(/-+/g, '-').replace(/-$/, '');
    } else if (n.includes('milk') && !n.includes('chocolate')) {
        let base = n.includes('oat') ? 'oat' : (n.includes('almond') ? 'almond' : (n.includes('soy') ? 'soy' : 'dairy'));
        let trait = 'std';
        if (n.includes('unsweetened') || n.includes('no added sugar') || n.includes('no sugar')) trait = 'unsweetened';
        else if (n.includes('barista')) trait = 'barista';
        else if (n.includes('uht') || n.includes('long life')) trait = 'uht';
        else if (n.includes('full cream')) trait = 'fullcream';
        else if (n.includes('skim') || n.includes('lite') || n.includes('light')) trait = 'light';
        
        let sizeMatch = n.match(/\b\d+(\.\d+)?\s*(l|ml)\b/);
        let size = sizeMatch ? sizeMatch[0].replace(/\s/g, '') : '1l'; // Smart default to 1L for unlisted alt-milks
        
        canonId = `milk-${base}-${trait}-${size}`.replace(/-+/g, '-');
    }
    if (!map.has(canonId)) {
      map.set(canonId, {
        id: canonId,
        name: listing.product_name,
        image: listing.image_url,
        prices: {}
      });
    }
    
    const product = map.get(canonId);
    
    // Store price using store name as key
    product.prices[listing.store] = {
      store_name: listing.store,
      original_name: listing.product_name,
      price: listing.current_price,
      regular_price: listing.regular_price,
      in_stock: listing.in_stock
    };
  }
  return [...map.values()];
}