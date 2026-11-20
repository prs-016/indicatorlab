/** Pure quote/view helpers shared by the UI and the dependency-free Node tests. */
export const MARKETS = Object.freeze({
  hk: { name: "Hong Kong", label: "HSI constituent stocks", currency: "HKD", zone: "Asia/Hong_Kong", clock: "HKT", exchange: "HKEX", flag: "HK" },
  india: { name: "India", label: "NIFTY 100 constituent stocks", currency: "INR", zone: "Asia/Kolkata", clock: "IST", exchange: "NSE", flag: "IN" },
  us: { name: "United States", label: "US equities", currency: "USD", zone: "America/New_York", clock: "ET", exchange: "NYSE", flag: "US" },
});

const numeric = value => typeof value === "number" && Number.isFinite(value);
const validTime = value => typeof value === "string" && Number.isFinite(Date.parse(value));

export function normalisePayload(payload, market) {
  if (!payload || !Array.isArray(payload.quotes) || payload.market !== market || typeof payload.market_open !== "boolean") {
    throw apiFailure("invalid_response");
  }
  const quotes = new Map();
  for (const row of payload.quotes) {
    if (!row || typeof row.symbol !== "string" || !numeric(row.price) || row.price <= 0 ||
        !numeric(row.change_pct) || !numeric(row.volume) || row.volume < 0 ||
        !validTime(row.ts_exchange) || !validTime(row.ts_received)) continue;
    const previous = quotes.get(row.symbol);
    if (!previous || Date.parse(previous.ts_exchange) <= Date.parse(row.ts_exchange)) {
      quotes.set(row.symbol, { ...row, name: typeof row.name === "string" ? row.name : row.symbol, market });
    }
  }
  const instruments = new Map((Array.isArray(payload.instruments) ? payload.instruments : [])
    .filter(row => row && typeof row.symbol === "string")
    .map(row => [row.symbol, { symbol: row.symbol, name: typeof row.name === "string" ? row.name : row.symbol, market }]));
  for (const [symbol, quote] of quotes) instruments.set(symbol, quote);
  return { ...payload, quotes: [...quotes.values()], instruments: [...instruments.values()],
    requested_count: Math.max(instruments.size, Number.isInteger(payload.requested_count) ? payload.requested_count : 0),
    received_count: quotes.size, currency: payload.currency || MARKETS[market].currency };
}

export function selectStocks(snapshots, { query = "", filter = "all", sort = "symbol", watchlist = new Set() } = {}) {
  const search = query.trim().toLocaleLowerCase();
  const rows = snapshots.flatMap(snapshot => snapshot.instruments).filter(row => {
    const matches = `${row.name} ${row.symbol}`.toLocaleLowerCase().includes(search);
    return matches && (filter === "all" || (filter === "gainers" && row.change_pct > 0) ||
      (filter === "losers" && row.change_pct < 0) || (filter === "watchlist" && watchlist.has(`${row.market}:${row.symbol}`)));
  });
  const comparison = sort === "change" ? (a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity) :
    sort === "price" ? (a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity) :
    sort === "name" ? (a, b) => a.name.localeCompare(b.name) : (a, b) => a.symbol.localeCompare(b.symbol, undefined, { numeric: true });
  return rows.sort((a, b) => comparison(a, b) || a.symbol.localeCompare(b.symbol));
}

export function breadth(quotes) {
  return quotes.reduce((counts, row) => {
    counts[row.change_pct > 0 ? "up" : row.change_pct < 0 ? "down" : "flat"] += 1;
    return counts;
  }, { up: 0, down: 0, flat: 0 });
}

export function money(value, currency = "HKD") {
  if (!numeric(value)) return "—";
  return new Intl.NumberFormat("en-HK", { style: "currency", currency,
    minimumFractionDigits: 2, maximumFractionDigits: value < 1 ? 3 : 2 }).format(value);
}

export function change(value) { return numeric(value) ? `${value > 0 ? "+" : ""}${value.toFixed(2)}%` : "—"; }
export function volume(value) { return numeric(value) ? new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(value) : "—"; }
export function marketTime(value, market = "hk", full = false) {
  if (!validTime(value)) return "Not available";
  const options = full ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" } :
    { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" };
  return `${new Intl.DateTimeFormat("en-GB", { ...options, timeZone: MARKETS[market].zone }).format(new Date(value))} ${MARKETS[market].clock}`;
}

export function sessionLabel(snapshot) {
  if (!snapshot) return "Connecting";
  if (snapshot.market_state === "lunch") return "Lunch break";
  return snapshot.market_open ? "Market open" : "Market closed";
}

export function safeWatchlist(storage) {
  try { const list = JSON.parse(storage.getItem("indicatorlab.watchlist") || "[]"); return new Set(Array.isArray(list) ? list.filter(x => typeof x === "string") : []); }
  catch { return new Set(); }
}

/** A stable display category; response bodies and exception details stay private. */
export function apiFailure(kind, status) {
  const error = new Error(kind === "feed_unavailable" ? "Quote feed unavailable" :
    kind === "unsupported" ? "Feed not connected" : kind === "invalid_response" ? "Invalid API response" : "Data service error");
  error.kind = kind;
  if (status !== undefined) error.status = status;
  return error;
}

export async function readApiResponse(response) {
  if (!response.ok) {
    const kind = response.status === 404 ? "unsupported" : response.status === 503 ? "feed_unavailable" :
      [401, 403].includes(response.status) ? "access_denied" : "service_error";
    throw apiFailure(kind, response.status);
  }
  const type = response.headers.get("content-type") || "";
  if (!/\bapplication\/(?:[a-z0-9.+-]+\+)?json\b/i.test(type)) throw apiFailure("invalid_response", response.status);
  try { return await response.json(); }
  catch { throw apiFailure("invalid_response", response.status); }
}

function failureKind(error) {
  if (error?.kind) return error.kind;
  if (error?.status === 404) return "unsupported";
  if (error?.status === 503) return "feed_unavailable";
  if (error?.name === "AbortError") return "timeout";
  return "network";
}

/** A missing optional market does not disconnect a successfully loaded HK feed. */
export function connectionState({ selected, snapshots, errors, paused = false }) {
  const failures = selected.filter(key => errors.has(key));
  const active = failures.filter(key => failureKind(errors.get(key)) !== "unsupported");
  const loaded = selected.filter(key => snapshots.has(key) && !errors.has(key));
  if (active.length) {
    const kinds = active.map(key => failureKind(errors.get(key)));
    if (kinds.every(kind => kind === "feed_unavailable")) return { label: "Waiting for quotes", className: "warning" };
    if (kinds.includes("invalid_response")) return { label: "Invalid API response", className: "error" };
    if (kinds.includes("access_denied")) return { label: "API access denied", className: "error" };
    if (kinds.includes("service_error")) return { label: "Data service error", className: "error" };
    return { label: "Connection interrupted", className: "error" };
  }
  if (paused) return { label: "Updates paused", className: loaded.length ? "connected" : "" };
  if (loaded.some(key => snapshots.get(key).is_stale)) return { label: "Updates delayed", className: "warning" };
  if (loaded.length) return { label: "Connected", className: "connected" };
  if (failures.length) return { label: "Feed not connected", className: "warning" };
  return { label: "Connecting", className: "" };
}

export function recoveryAdvice(apiBaseUrl, pageUrl, feed = false) {
  let local = false;
  try {
    const page = new URL(pageUrl);
    const api = new URL(apiBaseUrl || page.origin, page);
    local = page.protocol === "file:" || ["localhost", "127.0.0.1", "[::1]"].includes(api.hostname);
  } catch { /* An invalid remote configuration still gets useful generic advice. */ }
  return local ? "Reopen Start HK Dashboard.command in the project folder, then retry." :
    feed ? "Check the quote collector and its configured data source." :
      "Check that the data service is running and the dashboard's API address is correct.";
}

export function connectionNotice({ selected, snapshots, errors, apiBaseUrl = "", pageUrl }) {
  const failed = selected.filter(key => errors.has(key));
  const active = failed.filter(key => failureKind(errors.get(key)) !== "unsupported");
  const retained = selected.some(key => snapshots.get(key)?.quotes.length);
  const prefix = retained ? "Showing the last received prices. " : "";
  if (active.length) {
    const kinds = active.map(key => failureKind(errors.get(key)));
    if (kinds.every(kind => kind === "feed_unavailable")) return {
      title: "Quotes unavailable", severity: "warning",
      message: `${prefix}The API is responding, but the quote snapshot is unavailable. ${recoveryAdvice(apiBaseUrl, pageUrl, true)}`,
    };
    if (kinds.includes("invalid_response")) return {
      title: "Invalid API response", severity: "error",
      message: `${prefix}The configured address did not return valid market data. ${recoveryAdvice(apiBaseUrl, pageUrl)}`,
    };
    if (kinds.includes("access_denied")) return {
      title: "API access denied", severity: "error",
      message: `${prefix}The data service refused this request. Check its access settings.`,
    };
    if (kinds.includes("service_error")) return {
      title: "Data service error", severity: "error",
      message: `${prefix}The API responded with an error. ${recoveryAdvice(apiBaseUrl, pageUrl)}`,
    };
    return {
      title: kinds.includes("timeout") ? "Data service timed out" : "API unreachable", severity: "error",
      message: `${prefix}The data service could not be reached. ${recoveryAdvice(apiBaseUrl, pageUrl)}`,
    };
  }
  if (selected.some(key => !errors.has(key) && snapshots.get(key)?.is_stale)) return {
    title: "Updates delayed", severity: "warning",
    message: `The market is open, but some stocks have not refreshed recently. Last available prices remain visible. ${recoveryAdvice(apiBaseUrl, pageUrl, true)}`,
  };
  if (failed.length) {
    const names = failed.map(key => MARKETS[key].name).join(" and ");
    const connected = selected.filter(key => snapshots.has(key) && !errors.has(key)).map(key => MARKETS[key].name).join(" and ");
    return {
      title: connected ? "Other markets not connected" : "Feed not connected", severity: "notice",
      message: `${prefix}${names} quotes will appear when those feeds are connected.${connected ? ` ${connected} remains connected.` : ""}${failed.includes("hk") ? ` ${recoveryAdvice(apiBaseUrl, pageUrl)}` : ""}`,
    };
  }
  return null;
}
