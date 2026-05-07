var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// .wrangler/tmp/bundle-I62WrH/checked-fetch.js
var urls = /* @__PURE__ */ new Set();
function checkURL(request, init) {
  const url = request instanceof URL ? request : new URL(
    (typeof request === "string" ? new Request(request, init) : request).url
  );
  if (url.port && url.port !== "443" && url.protocol === "https:") {
    if (!urls.has(url.toString())) {
      urls.add(url.toString());
      console.warn(
        `WARNING: known issue with \`fetch()\` requests to custom HTTPS ports in published Workers:
 - ${url.toString()} - the custom port will be ignored when the Worker is published using the \`wrangler deploy\` command.
`
      );
    }
  }
}
__name(checkURL, "checkURL");
globalThis.fetch = new Proxy(globalThis.fetch, {
  apply(target, thisArg, argArray) {
    const [request, init] = argArray;
    checkURL(request, init);
    return Reflect.apply(target, thisArg, argArray);
  }
});

// worker.js
var worker_default = {
  async fetch(request, env) {
    const url = new URL(request.url);
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Content-Type": "application/json"
    };
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }
    const SHEET_ID = env.GOOGLE_SHEET_ID || "14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k";
    const API_KEY = env.GOOGLE_API_KEY;
    async function fetchSheetRange(range) {
      const sheetsUrl = new URL(
        `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}/values/${encodeURIComponent(range)}`
      );
      sheetsUrl.searchParams.set("key", API_KEY);
      const res = await fetch(sheetsUrl.toString());
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`Sheets API error ${res.status}: ${err}`);
      }
      const data = await res.json();
      return data.values || [];
    }
    __name(fetchSheetRange, "fetchSheetRange");
    function parseListings(rows) {
      if (rows.length < 2) return [];
      return rows.slice(1).map((row) => ({
        listing_id: row[0] || "",
        product_name: row[1] || "",
        store: row[2] || "",
        current_price: parseFloat(row[3]) || null,
        regular_price: parseFloat(row[4]) || null,
        in_stock: (row[5] || "").toString().toLowerCase() !== "false",
        image_url: row[6] || ""
      })).filter((r) => r.product_name);
    }
    __name(parseListings, "parseListings");
    function groupByProduct(listings) {
      const map = /* @__PURE__ */ new Map();
      for (const listing of listings) {
        const key = listing.product_name;
        if (!map.has(key)) {
          map.set(key, {
            id: key.toLowerCase().replace(/\s+/g, "-"),
            name: listing.product_name,
            image: listing.image_url,
            prices: []
          });
        }
        const product = map.get(key);
        if (!product.image && listing.image_url) {
          product.image = listing.image_url;
        }
        if (!product.prices.find((p) => p.store === listing.store)) {
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
    __name(groupByProduct, "groupByProduct");
    if (url.pathname === "/api/debug") {
      return new Response(JSON.stringify({
        sheetId: SHEET_ID,
        hasApiKey: !!API_KEY,
        apiKeyHint: API_KEY ? API_KEY.substring(0, 8) + "..." : "MISSING"
      }), { headers: corsHeaders });
    }
    if (url.pathname === "/api/test") {
      try {
        const rows = await fetchSheetRange("Listings!A1:G6");
        return new Response(JSON.stringify({ rows }), { headers: corsHeaders });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
      }
    }
    if (url.pathname === "/api/search") {
      try {
        const query = url.searchParams.get("q");
        if (!query) {
          return new Response(
            JSON.stringify({ error: "Missing query parameter 'q'" }),
            { status: 400, headers: corsHeaders }
          );
        }
        const SYNONYMS = {
          "lf": "lactose free",
          "fc": "full cream",
          "ww": "woolworths"
        };
        const terms = query.toLowerCase().split(/\s+/).filter(Boolean).map((t) => SYNONYMS[t] ?? t);
        const rows = await fetchSheetRange("Listings!A:G");
        const allListings = parseListings(rows);
        const matched = allListings.filter((listing) => {
          const haystack = listing.product_name.toLowerCase();
          return terms.every((term) => haystack.includes(term));
        });
        const products = groupByProduct(matched).map((p) => {
          p.prices = p.prices.filter((pr) => pr.store !== "Chemist Warehouse");
          return p;
        }).filter((p) => p.prices.length > 0).sort((a, b) => b.prices.length - a.prices.length);
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
    if (url.pathname === "/api/price-history") {
      try {
        const product = url.searchParams.get("product");
        if (!product) {
          return new Response(
            JSON.stringify({ error: "Missing 'product' parameter" }),
            { status: 400, headers: corsHeaders }
          );
        }
        const rows = await fetchSheetRange("Price_History!A:E");
        if (rows.length < 2) {
          return new Response(JSON.stringify({ history: [], stats: {} }), { headers: corsHeaders });
        }
        const history = rows.slice(1).filter((row) => row[1] === product).map((row) => ({
          date: row[0],
          store: row[2],
          price: parseFloat(row[3]) || 0,
          regular_price: parseFloat(row[4]) || null
        })).sort((a, b) => new Date(a.date) - new Date(b.date));
        if (history.length === 0) {
          return new Response(JSON.stringify({ history: [], stats: {} }), { headers: corsHeaders });
        }
        const statsByStore = {};
        const stores = [...new Set(history.map((h) => h.store))];
        for (const store of stores) {
          const storeHistory = history.filter((h) => h.store === store);
          const prices = storeHistory.map((h) => h.price).filter((p) => p > 0);
          const minPrice = Math.min(...prices);
          const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
          let trend = "stable";
          let pctChange = 0;
          if (storeHistory.length >= 2) {
            const last = storeHistory[storeHistory.length - 1].price;
            const prev = storeHistory[storeHistory.length - 2].price;
            if (last > prev) {
              trend = "up";
              pctChange = (last - prev) / prev * 100;
            } else if (last < prev) {
              trend = "down";
              pctChange = (prev - last) / prev * 100;
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
    if (url.pathname === "/api/list/compare") {
      if (request.method !== "POST") {
        return new Response(JSON.stringify({ error: "Method not allowed. Use POST." }), { status: 405, headers: corsHeaders });
      }
      try {
        const body = await request.json();
        const productQueries = body.products || [];
        if (!Array.isArray(productQueries) || productQueries.length === 0) {
          return new Response(JSON.stringify({ error: "Invalid or empty products list" }), { status: 400, headers: corsHeaders });
        }
        const rows = await fetchSheetRange("Listings!A:G");
        const allListings = parseListings(rows);
        const grouped = groupByProduct(allListings);
        const stores = [...new Set(allListings.map((l) => l.store))].filter((s) => s !== "Chemist Warehouse");
        const breakdown = [];
        const totals = {};
        const missingCount = {};
        stores.forEach((s) => {
          totals[s] = 0;
          missingCount[s] = 0;
        });
        for (const query of productQueries) {
          const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
          const matches = grouped.map((p) => {
            const name = p.name.toLowerCase();
            let score = 0;
            if (!terms.every((t) => name.includes(t))) return null;
            if (name.startsWith(terms[0])) score += 10;
            terms.forEach((t) => {
              if (new RegExp(`\\b${t}\\b`).test(name)) score += 5;
            });
            score -= name.length / 10;
            return { product: p, score };
          }).filter((m) => m !== null).sort((a, b) => b.score - a.score);
          const bestMatch = matches[0]?.product;
          const pricesObj = {};
          if (bestMatch) {
            stores.forEach((store) => {
              const storePrice = bestMatch.prices.find((p) => p.store === store);
              if (storePrice && storePrice.price > 0 && storePrice.in_stock !== false) {
                pricesObj[store] = storePrice.price;
                totals[store] += storePrice.price;
              } else {
                pricesObj[store] = null;
                missingCount[store]++;
              }
            });
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
            breakdown.push({
              query,
              product: null,
              prices: stores.reduce((acc, s) => ({ ...acc, [s]: null }), {}),
              cheapest: null
            });
            stores.forEach((s) => missingCount[s]++);
          }
        }
        const finalTotals = {};
        const unavailable = [];
        let cheapestOverallStore = null;
        let minTotal = Infinity;
        stores.forEach((s) => {
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
        const validTotals = Object.values(finalTotals).filter((t) => t !== null).sort((a, b) => a - b);
        let savings = 0;
        if (validTotals.length >= 2) {
          savings = parseFloat((validTotals[1] - validTotals[0]).toFixed(2));
        }
        return new Response(JSON.stringify({
          totals: finalTotals,
          cheapest_store: cheapestOverallStore,
          savings,
          breakdown,
          unavailable
        }), { headers: corsHeaders });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
      }
    }
    return new Response(JSON.stringify({ error: "Endpoint not found" }), { status: 404, headers: corsHeaders });
  }
};

// ../../AppData/Roaming/npm/node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// ../../AppData/Roaming/npm/node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-I62WrH/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = worker_default;

// ../../AppData/Roaming/npm/node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-I62WrH/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=worker.js.map
