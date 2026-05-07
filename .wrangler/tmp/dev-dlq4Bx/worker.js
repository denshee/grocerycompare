var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// .wrangler/tmp/bundle-dgkqaz/checked-fetch.js
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
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400"
    };
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }
    const jsonResponse = /* @__PURE__ */ __name((data, status = 200) => {
      return new Response(JSON.stringify(data), {
        status,
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }, "jsonResponse");
    const DB_URL = "https://script.google.com/macros/s/AKfycbyO_7q8o_1o-6n-8x2x7m7o-8q-8q-8q-8q/exec";
    try {
      if (url.pathname === "/api/search") {
        const query = url.searchParams.get("q")?.toLowerCase() || "";
        if (!query) return jsonResponse({ error: "Missing query parameter 'q'" }, 400);
        try {
          const rows = await fetchSheetRange("Listings!A:H");
          const allListings = parseListings(rows);
          const terms = query.split(/\s+/).filter(Boolean);
          const matched = allListings.filter((listing) => {
            const haystack = listing.product_name.toLowerCase();
            return terms.every((term) => haystack.includes(term));
          });
          const grouped = groupByProduct(matched).sort((a, b) => Object.keys(b.prices).length - Object.keys(a.prices).length);
          return jsonResponse({ products: grouped });
        } catch (err) {
          return jsonResponse({ error: `Search Failure: ${err.message}` }, 500);
        }
      }
      if (url.pathname === "/api/price-history") {
        const productQuery = url.searchParams.get("product");
        if (!productQuery) return jsonResponse({ error: "Missing 'product' parameter" }, 400);
        const SHEET_ID = "14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k";
        const historyUrl = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:json&sheet=Price_History&range=A:E`;
        try {
          const response = await fetch(historyUrl);
          const text = await response.text();
          const startIdx = text.indexOf("{");
          const endIdx = text.lastIndexOf("}") + 1;
          const data = JSON.parse(text.substring(startIdx, endIdx));
          const allRows = data.table.rows.map((r) => ({
            timestamp: r.c[0]?.v,
            product_name: r.c[1]?.v,
            store: r.c[2]?.v,
            price: r.c[3]?.v,
            was_price: r.c[4]?.v
          }));
          const filtered = allRows.filter(
            (r) => r.product_name && r.product_name.toLowerCase().includes(productQuery.toLowerCase())
          );
          if (filtered.length === 0) {
            return jsonResponse({ history: [], stats: { min_price: null, avg_price: null, trend: 0 } });
          }
          const validPrices = filtered.map((r) => r.price).filter((p) => typeof p === "number" && p > 0);
          const min_price = validPrices.length ? Math.min(...validPrices) : null;
          const avg_price = validPrices.length ? validPrices.reduce((a, b) => a + b, 0) / validPrices.length : null;
          let trend = 0;
          if (validPrices.length >= 2) {
            const last = validPrices[validPrices.length - 1];
            const prev = validPrices[validPrices.length - 2];
            trend = (last - prev) / prev * 100;
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
      if (url.pathname === "/api/save-list" && request.method === "POST") {
        try {
          const listData = await request.json();
          const listID = Math.random().toString(36).substring(2, 8).toUpperCase();
          if (!env.GROCERY_LISTS) {
            return jsonResponse({ success: false, error: "KV Namespace GROCERY_LISTS not bound" }, 500);
          }
          await env.GROCERY_LISTS.put(listID, JSON.stringify(listData), { expirationTtl: 604800 });
          return jsonResponse({ success: true, listID });
        } catch (kvErr) {
          return jsonResponse({ success: false, error: `Cloud Storage Failure: ${kvErr.message}` }, 500);
        }
      }
      if (url.pathname.startsWith("/api/list/")) {
        const listID = url.pathname.split("/").pop().toUpperCase();
        if (!env.GROCERY_LISTS) {
          return jsonResponse({ success: false, error: "KV Namespace GROCERY_LISTS not bound" }, 500);
        }
        const stored = await env.GROCERY_LISTS.get(listID);
        if (!stored) {
          return jsonResponse({ success: false, error: "Shared list not found" }, 404);
        }
        return jsonResponse({ success: true, items: JSON.parse(stored) });
      }
      if (url.pathname === "/api/sync" && request.method === "PUT") {
        const auth = request.headers.get("Authorization");
        if (auth !== "your_secret_auth_key") {
          return jsonResponse({ success: false, error: "Unauthorized" }, 401);
        }
        try {
          const marketData = await request.json();
          if (!env.MARKET_DATA) {
            return jsonResponse({ success: false, error: "KV Namespace MARKET_DATA not bound" }, 500);
          }
          await env.MARKET_DATA.put("latest_snapshot", JSON.stringify(marketData));
          return jsonResponse({ success: true, message: "Market data synchronized" });
        } catch (syncErr) {
          return jsonResponse({ success: false, error: `Sync Failure: ${syncErr.message}` }, 500);
        }
      }
      if (url.pathname === "/api/catalog") {
        try {
          const rawData = await fetchSheetRange("Products!B:B");
          const catalog = [...new Set(
            rawData.flat().slice(1).map((item) => String(item || "").trim()).filter((item) => item.length > 0)
          )].sort();
          return jsonResponse({ catalog });
        } catch (catErr) {
          return jsonResponse({ error: `Catalog Fetch Failure: ${catErr.message}` }, 500);
        }
      }
      return new Response("Not Found", { status: 404, headers: corsHeaders });
    } catch (err) {
      return jsonResponse({ success: false, error: `Internal Server Error: ${err.message}` }, 500);
    }
  }
};
async function fetchSheetRange(range) {
  const SHEET_ID = "14cci7jorS43qBbAW673-jh_394TPHeCcC4lYAOqIk0k";
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:json&range=${encodeURIComponent(range)}`;
  const response = await fetch(url);
  const text = await response.text();
  const startIdx = text.indexOf("{");
  const endIdx = text.lastIndexOf("}") + 1;
  const data = JSON.parse(text.substring(startIdx, endIdx));
  return data.table.rows.map((r) => r.c.map((cell) => cell ? cell.v : null));
}
__name(fetchSheetRange, "fetchSheetRange");
function getCanonicalId(name) {
  if (!name) return "unknown";
  let n = name.toLowerCase();
  const brands = ["coles", "woolworths", "aldi", "select", "paddock", "market", "brand", "australian", "essentials", "macro"];
  brands.forEach((b) => n = n.replace(new RegExp(`\\b${b}\\b`, "g"), ""));
  const sizeMatch = n.match(/\d+(\.\d+)?\s*(l|ml|g|kg|pk|pack|ea|s|tabs|capsules)/i);
  const size = sizeMatch ? sizeMatch[0].toLowerCase().replace(/\s/g, "") : "std";
  const clean = n.replace(/[^a-z0-9 ]/g, " ").trim();
  const words = clean.split(/\s+/).filter((w) => w.length > 1);
  const core = words.slice(0, 3).join("-");
  return `${core}-${size}`.replace(/-+/g, "-");
}
__name(getCanonicalId, "getCanonicalId");
function parseListings(rows) {
  if (rows.length < 2) return [];
  return rows.slice(1).map((row) => ({
    listing_id: row[0] || "",
    product_name: row[1] || "",
    store: row[2] || "",
    current_price: parseFloat(String(row[3]).replace(/[^\d.]/g, "")) || 0,
    regular_price: parseFloat(String(row[4]).replace(/[^\d.]/g, "")) || 0,
    in_stock: (row[5] || "").toString().toLowerCase() !== "false",
    image_url: row[6] || "",
    comparison_key: row[7] ? row[7].toString().trim() : ""
  })).filter((r) => r.product_name);
}
__name(parseListings, "parseListings");
function groupByProduct(listings) {
  const map = /* @__PURE__ */ new Map();
  for (const listing of listings) {
    const canonId = listing.comparison_key || getCanonicalId(listing.product_name);
    if (!map.has(canonId)) {
      map.set(canonId, {
        id: canonId,
        name: listing.product_name,
        image: listing.image_url,
        prices: {}
      });
    }
    const product = map.get(canonId);
    product.prices[listing.store] = {
      store_name: listing.store,
      price: listing.current_price,
      regular_price: listing.regular_price,
      in_stock: listing.in_stock
    };
  }
  return [...map.values()];
}
__name(groupByProduct, "groupByProduct");

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

// .wrangler/tmp/bundle-dgkqaz/middleware-insertion-facade.js
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

// .wrangler/tmp/bundle-dgkqaz/middleware-loader.entry.ts
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
