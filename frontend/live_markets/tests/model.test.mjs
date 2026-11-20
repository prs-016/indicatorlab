import test from "node:test";
import assert from "node:assert/strict";
import { normalisePayload, selectStocks, breadth, money, change, sessionLabel, marketTime, safeWatchlist, apiFailure, readApiResponse, connectionState, connectionNotice, recoveryAdvice } from "../model.mjs";

const quote = (symbol, price, change_pct) => ({ symbol, name: symbol === "0700.HK" ? "Tencent" : "HSBC", price, change_pct, volume: 200,
  ts_exchange: "2026-11-18T07:59:50+00:00", ts_received: "2026-11-18T07:59:55+00:00", source: "tencent" });
const input = () => ({ market: "hk", market_open: false, quotes: [quote("0700.HK", 398.8, -2.64), quote("0005.HK", 120, 1.2)],
  instruments: [{ symbol: "0700.HK", name: "Tencent" }, { symbol: "0005.HK", name: "HSBC" }, { symbol: "9988.HK", name: "Alibaba" }] });

test("bad symbols/numbers/times do not hide good rows or invent missing prices", () => {
  const value = input(); value.quotes.push({ ...quote("9988.HK", null, 1), volume: -1 });
  const result = normalisePayload(value, "hk");
  assert.equal(result.received_count, 2); assert.equal(result.requested_count, 3);
  assert.equal(result.instruments.find(row => row.symbol === "9988.HK").price, undefined);
});
test("invalid API contract and wrong market are rejected", () => {
  assert.throws(() => normalisePayload({}, "hk")); assert.throws(() => normalisePayload(input(), "india"));
});
test("search, positive/negative filters and descending sort use actual values", () => {
  const data = [normalisePayload(input(), "hk")];
  assert.equal(selectStocks(data, { query: "TENCENT" })[0].symbol, "0700.HK");
  assert.equal(selectStocks(data, { filter: "losers" })[0].symbol, "0700.HK");
  assert.equal(selectStocks(data, { filter: "gainers" })[0].symbol, "0005.HK");
  assert.equal(selectStocks(data, { sort: "change" })[0].symbol, "0005.HK");
});
test("watchlists are scoped to market", () => {
  const data = [normalisePayload(input(), "hk")];
  assert.equal(selectStocks(data, { filter: "watchlist", watchlist: new Set(["india:0700.HK"]) }).length, 0);
  assert.equal(selectStocks(data, { filter: "watchlist", watchlist: new Set(["hk:0700.HK"]) }).length, 1);
});
test("breadth includes flat stocks without treating missing data as flat", () => {
  assert.deepEqual(breadth([...input().quotes, quote("1", 1, 0)]), { up: 1, down: 1, flat: 1 });
});
test("prices, signs and absent values remain explicit", () => {
  assert.match(money(398.8), /398\.80/); assert.equal(money(undefined), "—");
  assert.equal(change(-2.64), "-2.64%"); assert.equal(change(1.2), "+1.20%");
});
test("closed and lunch labels retain their distinct meanings", () => {
  assert.equal(sessionLabel({ market_open: false, market_state: "lunch" }), "Lunch break");
  assert.equal(sessionLabel({ market_open: false }), "Market closed");
});
test("exchange clock uses Hong Kong timezone independently of device timezone", () => {
  assert.equal(marketTime("2026-11-18T07:59:50+00:00", "hk"), "15:59:50 HKT");
});
test("blocked or corrupted browser storage falls back to an empty watchlist", () => {
  assert.equal(safeWatchlist({ getItem() { throw new Error("blocked"); } }).size, 0);
  assert.equal(safeWatchlist({ getItem() { return "{bad"; } }).size, 0);
});

test("valid API JSON is decoded", async () => {
  const value = await readApiResponse(new Response('{"market":"hk"}', { headers: { "Content-Type": "application/json" } }));
  assert.equal(value.market, "hk");
});
test("HTML or broken JSON is reported as an invalid response, not a lost connection", async () => {
  await assert.rejects(readApiResponse(new Response('<html>Wrong server</html>', { headers: { "Content-Type": "text/html" } })), error => error.kind === "invalid_response");
  await assert.rejects(readApiResponse(new Response('{broken', { headers: { "Content-Type": "application/json" } })), error => error.kind === "invalid_response");
});
test("HTTP 503 distinguishes an available API from missing quote data", async () => {
  let failure;
  try { await readApiResponse(new Response('{}', { status: 503, headers: { "Content-Type": "application/json" } })); }
  catch (error) { failure = error; }
  assert.equal(failure.kind, "feed_unavailable");
  const state = { selected: ["hk"], snapshots: new Map(), errors: new Map([["hk", failure]]), pageUrl: "http://127.0.0.1:8765/live-markets/" };
  assert.equal(connectionState(state).label, "Waiting for quotes");
  assert.equal(connectionNotice(state).title, "Quotes unavailable");
  assert.match(connectionNotice(state).message, /API is responding.*Start HK Dashboard.command/);
});
test("All preserves connected HK status when optional market feeds return 404", () => {
  const state = { selected: ["hk", "india", "us"], snapshots: new Map([["hk", normalisePayload(input(), "hk")]]), errors: new Map([["india", apiFailure("unsupported", 404)], ["us", apiFailure("unsupported", 404)]]) };
  assert.equal(connectionState(state).label, "Connected");
  assert.equal(connectionNotice(state).severity, "notice");
  assert.match(connectionNotice(state).message, /Hong Kong remains connected/);
});
test("one unconnected market is not mislabeled as a network outage", () => {
  const state = { selected: ["india"], snapshots: new Map(), errors: new Map([["india", apiFailure("unsupported", 404)]]) };
  assert.equal(connectionState(state).label, "Feed not connected");
  assert.equal(connectionNotice(state).title, "Feed not connected");
});
test("local connection errors explain how to restart while retaining prices", () => {
  const state = { selected: ["hk"], snapshots: new Map([["hk", normalisePayload(input(), "hk")]]), errors: new Map([["hk", new TypeError("Failed to fetch")]]), pageUrl: "http://localhost:8765/live-markets/" };
  const notice = connectionNotice(state);
  assert.equal(connectionState(state).label, "Connection interrupted");
  assert.equal(notice.title, "API unreachable");
  assert.match(notice.message, /Showing the last received prices.*Start HK Dashboard.command/);
});
test("hosted APIs never receive instructions to start a localhost service", () => {
  const advice = recoveryAdvice("https://api.example.org", "https://dashboard.example.org/");
  assert.doesNotMatch(advice, /Start HK|localhost/);
  const state = { selected: ["hk"], snapshots: new Map(), errors: new Map([["hk", apiFailure("feed_unavailable", 503)]]), apiBaseUrl: "https://api.example.org", pageUrl: "https://dashboard.example.org/" };
  assert.match(connectionNotice(state).message, /quote collector/);
  assert.doesNotMatch(connectionNotice(state).message, /Start HK/);
});
test("stale data remains a freshness warning instead of a connection failure", () => {
  const snapshot = { ...normalisePayload(input(), "hk"), is_stale: true };
  const state = { selected: ["hk"], snapshots: new Map([["hk", snapshot]]), errors: new Map() };
  assert.equal(connectionState(state).label, "Updates delayed");
  assert.equal(connectionNotice(state).title, "Updates delayed");
});
test("invalid market payload uses the response-validation category", () => {
  assert.throws(() => normalisePayload({}, "hk"), error => error.kind === "invalid_response");
});
test("access denial and server errors preserve their API-response meaning", async () => {
  await assert.rejects(readApiResponse(new Response('{}', { status: 403 })), error => error.kind === "access_denied");
  await assert.rejects(readApiResponse(new Response('{}', { status: 500 })), error => error.kind === "service_error");
});
test("cached prices do not falsely mark a removed feed as connected", () => {
  const state = { selected: ["hk"], snapshots: new Map([["hk", normalisePayload(input(), "hk")]]), errors: new Map([["hk", apiFailure("unsupported", 404)]]) };
  assert.equal(connectionState(state).label, "Feed not connected");
  assert.match(connectionNotice(state).message, /Showing the last received prices/);
  assert.doesNotMatch(connectionNotice(state).message, /remains connected/);
});


test("a missing HK route on a local static server gives launcher recovery", () => {
  const notice = connectionNotice({ selected: ["hk"], snapshots: new Map(), errors: new Map([["hk", apiFailure("unsupported", 404)]]), pageUrl: "http://localhost:8000/frontend/live_markets/" });
  assert.match(notice.message, /Start HK Dashboard.command/);
});
