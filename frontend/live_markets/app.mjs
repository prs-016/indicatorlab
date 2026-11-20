import { MARKETS, normalisePayload, selectStocks, breadth, money, change, volume, marketTime, sessionLabel, safeWatchlist, readApiResponse, connectionState, connectionNotice } from "./model.mjs";

const $ = id => document.getElementById(id);
const config = window.INDICATORLAB_CONFIG || {};
const interval = Math.max(5000, Number(config.refreshIntervalMs) || 5000);
const base = String(config.apiBaseUrl || "").replace(/\/$/, "");
const snapshots = new Map();
const errors = new Map();
const hot = new Set();
const cards = new Map();
let storage;
try { storage = window.localStorage; } catch { /* Storage may be disabled by browser policy. */ }
const watchlist = storage ? safeWatchlist(storage) : new Set();
let market = "hk", filter = "all", sort = "symbol", page = 0, paused = false;
let loading = false, generation = 0, lastList = "", selectedStock = null, lastAttention = 0;
let activeController = null;
let health = null;
const PAGE_SIZE = 24;

function selectedMarkets() { return market === "all" ? ["hk", "india", "us"] : [market]; }
function loaded() { return selectedMarkets().flatMap(key => snapshots.has(key) ? [snapshots.get(key)] : []); }
function endpoint(path) { return base + path; }
async function json(path, signal) {
  const response = await fetch(endpoint(path), { cache: "no-store", signal, headers: { Accept: "application/json" } });
  return readApiResponse(response);
}

function setConnection() {
  const state = connectionState({ selected: selectedMarkets(), snapshots, errors, paused });
  const node = $("connection");
  node.className = `connection ${state.className}`;
  if (node.lastElementChild.textContent !== state.label) node.lastElementChild.textContent = state.label;
}

function updateSummary() {
  const data = loaded();
  const main = data.find(value => value.market === "hk") || data[0];
  const meta = MARKETS[market] || MARKETS.hk;
  const quotes = data.flatMap(value => value.quotes);
  const total = data.reduce((sum, value) => sum + value.requested_count, 0);
  const changes = breadth(quotes);
  $("market-name").textContent = market === "all" ? "All live markets" : meta.name;
  $("exchange-badge").textContent = market === "all" ? "ALL" : meta.flag;
  $("exchange-name").textContent = market === "all" ? "" : meta.exchange;
  const status = $("session-status");
  status.className = `session-pill ${main?.market_open ? "open" : main?.market_state === "lunch" ? "lunch" : ""}`;
  status.lastElementChild.textContent = sessionLabel(main);
  $("coverage-value").textContent = data.length ? String(quotes.length) : "—";
  $("coverage-total").textContent = data.length ? `/ ${total}` : "";
  $("coverage-detail").textContent = data.length ? `${total - quotes.length ? `${total - quotes.length} awaiting quotes` : "All configured stocks available"}` : "Waiting for the latest quotes";
  $("gainers-value").textContent = data.length ? String(changes.up) : "—";
  $("losers-value").textContent = data.length ? String(changes.down) : "—";
  const n = Math.max(1, quotes.length);
  for (const key of ["up", "flat", "down"]) $("breadth-" + key).style.width = `${100 * changes[key] / n}%`;
  $("breadth-accessible").textContent = `${changes.up} advancing, ${changes.down} declining, ${changes.flat} unchanged`;
  const newest = health?.sources?.[`live_${main?.market}`]?.as_of || quotes.map(row => row.ts_received).sort((a, b) => Date.parse(b) - Date.parse(a))[0];
  $("header-as-of").textContent = newest ? `Data as of ${marketTime(newest, main?.market || "hk", true)}` : "Data as of —";
  $("updated-value").textContent = newest ? marketTime(newest, main?.market || "hk").replace(/ HKT| IST| ET/, "") : "—";
  $("updated-detail").textContent = newest ? `${marketTime(newest, main?.market || "hk", true)} · ${main?.is_stale ? "Updates delayed" : "Latest received snapshot"}` : "Quote times are shown in exchange time";
  $("closed-note").hidden = !main || main.market_open;
  if (main && !main.market_open) {
    const label = main.market_state === "lunch" ? "Lunch break" : "Closed";
    const stamp = newest ? marketTime(newest, main.market, true) : "not available";
    const opening = main.next_open ? ` · ${main.market_state === "lunch" ? "Resumes" : "Next open"} ${marketTime(main.next_open, main.market, true)}` : "";
    $("closed-copy").textContent = `${label} — last update ${stamp}${opening}. Last available prices remain visible.`;
  }
  const notice = connectionNotice({ selected: selectedMarkets(), snapshots, errors, apiBaseUrl: base, pageUrl: location.href });
  $("error-banner").hidden = !notice;
  $("error-banner").className = `error-banner ${notice?.severity || ""}`;
  if (notice) {
    $("error-title").textContent = notice.title;
    $("error-message").textContent = notice.message;
  }
  $("stocks-title").firstChild.textContent = market === "hk" ? "Hang Seng constituents " : market === "india" ? "NIFTY 100 constituents " : "Constituent stocks ";
  $("stocks-description").textContent = market === "all" ? "Latest constituent stock quotes · Prices in each market’s currency" : `Latest constituent stock quotes · Prices in ${meta.currency}`;
  $("stock-count").textContent = data.length ? String(total) : "—";
  const sources = [...new Set(quotes.map(row => row.source))].filter(Boolean).join(", ");
  $("source-note").textContent = `${sources ? sources.replace(/^tencent$/, "Tencent") + " · " : ""}Refreshes every ${interval / 1000}s · Exchange timestamps per stock`;
  $("roster-note").textContent = main?.roster_as_of ? `Constituent snapshot · ${main.roster_as_of}` : "";
  setConnection();
}

function cardFor(row) {
  const key = `${row.market}:${row.symbol}`;
  let node = cards.get(key);
  if (!node) {
    node = $("stock-template").content.firstElementChild.cloneNode(true);
    node.dataset.key = key;
    cards.set(key, node);
  }
  const watched = watchlist.has(key);
  const meta = MARKETS[row.market];
  node.querySelector(".company-name").textContent = row.name;
  node.querySelector(".company-name").title = row.name;
  node.querySelector(".stock-symbol").textContent = row.symbol;
  node.querySelector(".stock-open").setAttribute("aria-label", `View ${row.name}, ${row.symbol}`);
  const star = node.querySelector(".watch-button");
  star.setAttribute("aria-pressed", String(watched));
  star.setAttribute("aria-label", `${watched ? "Remove" : "Add"} ${row.name} ${watched ? "from" : "to"} watchlist`);
  node.querySelector(".stock-price").textContent = money(row.price, meta.currency);
  const pill = node.querySelector(".change-pill");
  pill.className = `change-pill ${row.change_pct > 0 ? "up" : row.change_pct < 0 ? "down" : ""}`;
  node.querySelector(".stock-change").textContent = change(row.change_pct);
  node.querySelector(".change-arrow").textContent = row.change_pct > 0 ? "↗" : row.change_pct < 0 ? "↘" : "";
  node.querySelector(".stock-volume").textContent = volume(row.volume);
  node.querySelector(".attention-badge").hidden = !hot.has(key);
  node.querySelector(".stock-exchange").textContent = `${meta.exchange} · ${meta.currency}`;
  const time = node.querySelector(".stock-time");
  time.textContent = row.ts_exchange ? marketTime(row.ts_exchange, row.market) : "Awaiting quote";
  const snapshot = snapshots.get(row.market);
  time.classList.toggle("delayed", Boolean(snapshot?.market_open && row.last_trade_age_seconds > 60));
  time.title = row.ts_exchange ? `Last trade: ${marketTime(row.ts_exchange, row.market, true)}. Received: ${marketTime(row.ts_received, row.market, true)}.` : "A quote has not been received for this stock.";
  return node;
}

function renderStocks() {
  const data = loaded();
  const rows = selectStocks(data, { query: $("search").value, filter, sort, watchlist });
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  page = Math.min(page, pages - 1);
  const visible = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const key = visible.map(row => `${row.market}:${row.symbol}`).join("|");
  const nodes = visible.map(cardFor);
  if (key !== lastList || $("stock-grid").querySelector(".skeleton")) {
    const focused = document.activeElement.closest?.(".stock-card");
    const focusKey = focused?.dataset.key;
    const action = document.activeElement.dataset?.action;
    $("stock-grid").replaceChildren(...nodes);
    if (focusKey && action) cards.get(focusKey)?.querySelector(`[data-action="${action}"]`)?.focus({ preventScroll: true });
    lastList = key;
  }
  $("stock-grid").setAttribute("aria-busy", String(loading && !data.length));
  $("empty-state").hidden = rows.length > 0 || (loading && !data.length);
  const hasData = data.some(snapshot => snapshot.instruments.length);
  $("empty-title").textContent = hasData ? filter === "watchlist" ? watchlist.size ? "No saved stocks in this market" : "Your watchlist is empty" : "No stocks found" : "Waiting for market data";
  $("empty-copy").textContent = hasData ? filter === "watchlist" ? "Star a stock to keep it close at hand." : "Try another company name, stock code or filter." : "Quotes will appear as soon as the live feed is available.";
  $("clear-filters").hidden = !hasData || filter === "watchlist";
  $("pagination").hidden = !rows.length;
  $("pagination-label").textContent = `Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, rows.length)} of ${rows.length} stocks`;
  $("page-number").textContent = `${page + 1} / ${pages}`;
  $("previous").disabled = page === 0;
  $("next").disabled = page + 1 === pages;
  $("watchlist-count").textContent = String(watchlist.size);
  if (selectedStock && $("stock-dialog").open) updateDialog(selectedStock);
}

function updateDialog(key) {
  const row = [...snapshots.values()].flatMap(value => value.instruments).find(value => `${value.market}:${value.symbol}` === key);
  if (!row) return;
  const meta = MARKETS[row.market];
  $("dialog-title").textContent = row.name;
  $("dialog-symbol").textContent = `${row.symbol} · ${meta.exchange}`;
  $("dialog-price").textContent = money(row.price, meta.currency);
  $("dialog-change").textContent = change(row.change_pct);
  $("dialog-change").className = `change-pill ${row.change_pct > 0 ? "up" : row.change_pct < 0 ? "down" : ""}`;
  const fields = [ ["Currency", meta.currency], ["Volume", row.volume?.toLocaleString("en") ?? "Not available"],
    ["Last trade", marketTime(row.ts_exchange, row.market, true)], ["Last received", marketTime(row.ts_received, row.market, true)],
    ["Quote source", row.source || "Not available"], ["Market", sessionLabel(snapshots.get(row.market))] ];
  $("dialog-details").replaceChildren(...fields.flatMap(([name, value]) => {
    const label = document.createElement("dt"), content = document.createElement("dd");
    label.textContent = name; content.textContent = value;
    return [label, content];
  }));
}

async function attention(signal, selected) {
  if (!config.attentionEnabled) return;
  if (Date.now() - lastAttention < (Number(config.attentionIntervalMs) || 300000)) return;
  lastAttention = Date.now();
  await Promise.all(selected.map(async key => {
    try {
      const payload = await json(`/hot?market=${key}`, signal);
      const rows = Array.isArray(payload) ? payload : payload.rows;
      if (!Array.isArray(rows)) return;
      for (const value of [...hot]) if (value.startsWith(key + ":")) hot.delete(value);
      for (const row of rows) if (typeof row.ticker === "string") hot.add(`${key}:${row.ticker}`);
    } catch { /* Optional team attention endpoint: unavailable is never fabricated as a signal. */ }
  }));
}

async function refresh() {
  if (loading) return;
  loading = true;
  const current = ++generation;
  const selected = selectedMarkets();
  const controller = new AbortController();
  activeController = controller;
  const timer = setTimeout(() => controller.abort(), 8000);
  $("refresh").disabled = true;
  try {
    const healthRequest = json("/health", controller.signal).then(value => { if (current === generation) health = value; }).catch(() => {});
    await Promise.all([...selected.map(async key => {
      try {
        const value = normalisePayload(await json(`/live/${key}`, controller.signal), key);
        if (current !== generation) return;
        snapshots.set(key, value); errors.delete(key);
      } catch (error) { if (current === generation) errors.set(key, error); }
    }), healthRequest]);
    if (current === generation) {
      updateSummary(); renderStocks();
      await attention(controller.signal, selected);
      if (current === generation) renderStocks();
    }
  } finally {
    clearTimeout(timer);
    if (current === generation) {
      loading = false; $("refresh").disabled = false;
      $("stock-grid").setAttribute("aria-busy", "false");
      renderStocks();
    }
  }
}

function route() {
  const selected = location.hash.replace(/^#\//, "") || "live";
  const screen = ["strategies", "comparison"].includes(selected) ? selected : "live";
  const name = screen === "strategies" ? "Strategy results" : screen === "comparison" ? "Cross-market comparison" : "Live markets";
  $("live-page").hidden = screen !== "live";
  $("coming-page").hidden = screen === "live";
  $("breadcrumb").textContent = name;
  $("page-title").textContent = name;
  $("page-description").textContent = screen === "live" ? "A clear view of the stocks moving your market." : "The next chapter of your market research.";
  $("coming-title").textContent = name;
  $("coming-copy").textContent = screen === "strategies" ? "Strategy evaluation will join this workspace on November 22." : "Compare factor performance across the US, India and Hong Kong. Coming November 22.";
  for (const link of document.querySelectorAll("[data-nav]")) {
    link.classList.toggle("active", link.dataset.nav === screen);
    if (link.dataset.nav === screen) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  }
}

$("stock-grid").innerHTML = Array.from({ length: 12 }, () => '<div class="skeleton" aria-hidden="true"></div>').join("");
$("refresh").addEventListener("click", refresh);
$("retry").addEventListener("click", refresh);
$("search").addEventListener("input", () => { page = 0; renderStocks(); });
$("sort").addEventListener("change", event => { sort = event.target.value; page = 0; renderStocks(); });
for (const button of document.querySelectorAll("[data-filter]")) button.addEventListener("click", () => {
  filter = button.dataset.filter; page = 0;
  for (const item of document.querySelectorAll("[data-filter]")) { item.classList.toggle("active", item === button); item.setAttribute("aria-pressed", String(item === button)); }
  renderStocks();
});
$("clear-filters").addEventListener("click", () => { $("search").value = ""; document.querySelector('[data-filter="all"]').click(); });
$("previous").addEventListener("click", () => { page -= 1; renderStocks(); });
$("next").addEventListener("click", () => { page += 1; renderStocks(); });
$("market").addEventListener("change", event => {
  generation += 1; activeController?.abort(); loading = false;
  market = event.target.value; page = 0; lastAttention = 0;
  updateSummary(); renderStocks(); refresh();
});
$("pause").addEventListener("click", () => {
  paused = !paused;
  $("pause").setAttribute("aria-pressed", String(paused));
  $("pause-label").textContent = paused ? "Updates paused" : `Auto-refresh · ${interval / 1000}s`;
  setConnection(); if (!paused) refresh();
});
$("stock-grid").addEventListener("click", event => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const key = button.closest(".stock-card").dataset.key;
  if (button.dataset.action === "watch") {
    if (watchlist.has(key)) watchlist.delete(key); else watchlist.add(key);
    try { storage?.setItem("indicatorlab.watchlist", JSON.stringify([...watchlist])); } catch { /* In-memory watchlists still work in private/restricted browsers. */ }
    renderStocks();
  } else { selectedStock = key; updateDialog(key); $("stock-dialog").showModal(); }
});
$("close-dialog").addEventListener("click", () => $("stock-dialog").close());
$("stock-dialog").addEventListener("click", event => { if (event.target === $("stock-dialog")) { const box = event.target.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close(); } });
document.addEventListener("keydown", event => { if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && !$("stock-dialog").open) { event.preventDefault(); $("search").focus(); } });
document.addEventListener("visibilitychange", () => { if (!document.hidden && !paused) refresh(); });
window.addEventListener("hashchange", route);
window.addEventListener("pagehide", () => activeController?.abort());
setInterval(() => { if (!paused && !document.hidden && !$("live-page").hidden) refresh(); }, interval);
function clock() { $("market-clock").textContent = marketTime(new Date().toISOString(), market === "all" ? "hk" : market, true); }
clock(); setInterval(clock, 1000);
route(); refresh();
