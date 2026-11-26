/* HK owns its DOM, requests, chart instances and polling. US globals stay intact. */
(() => {
  "use strict";
  const snapshot = document.body.dataset.hkSnapshot === "true";
  const root = document.getElementById("hk-dashboard");
  const context = document.getElementById("hk-context");
  const views = ["home", "now", "stock", "spikes", "strategies", "data"];
  const state = { active: new URLSearchParams(location.search).get("market") === "hk", generation: 0,
    requests: new Set(), charts: [], timer: null, polling: false, now: null, usHash: "#home", view: "home", ticker: null };
  const $ = id => root.querySelector(`#${id}`);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = (value, digits = 0) => value == null ? "Unavailable" : Number(value).toLocaleString("en-US", {maximumFractionDigits:digits, minimumFractionDigits:digits});
  const date = value => value ? String(value).slice(0,10) : "Unavailable";
  const time = value => value ? new Date(value).toLocaleString("en-GB", {timeZone:"Asia/Hong_Kong", hour12:false}) + " HKT" : "Unavailable";
  const ratio = value => value == null ? "—" : number(value,2) + "×";
  const head = (title, text) => `<div class="page-head"><div><h1>${title}</h1><p class="lede">${text}</p></div><button type="button" id="hk-refresh">Refresh display</button></div>`;
  const note = `<p class="hk-note">Wikipedia views and edits measure article attention. HK Reddit mentions are unavailable. Missing observations and sentiment stay unavailable; no values are filled with zero.</p>`;
  const table = (headers, rows) => `<div class="hk-scroll"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${headers.length}" class="hk-empty">No observations available for this selection.</td></tr>`}</tbody></table></div>`;
  const facts = pairs => `<dl class="hk-facts">${pairs.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>`;
  const stockLink = (code, name, week) => `<a href="#stock/${encodeURIComponent(code)}${week?'/'+encodeURIComponent(week):''}"><b>${esc(name || code)}</b><span class="sub">${esc(code)}</span></a>`;
  const stat = (value, label, attributes="") => `<div class="hk-stat"><strong ${attributes}>${esc(value)}</strong><span>${esc(label)}</span></div>`;
  const metric = m => !m?.available ? `<span class="muted">Unavailable</span>` : `<span class="${m.spike?'hk-flag':''}">${number(m.count)} <span class="sub">${ratio(m.ratio)} baseline${m.partial?' · partial week':''}${m.spike?' · SPIKE':''}</span></span>`;
  async function api(endpoint, params = {}) {
    const controller = new AbortController();
    state.requests.add(controller);
    const timeout = setTimeout(()=>controller.abort(), 15000);
    try {
      const query = new URLSearchParams({...params, market:"hk"});
      let target = `/api/${endpoint}?${query}`;
      if (snapshot) {
        if(endpoint === "order_estimate") throw new Error("USD estimates require a running cost service; unavailable in this hosted snapshot.");
        const allowed = ["now","live","status","spike_weeks","strategy_log","stock"];
        if(!allowed.includes(endpoint)) throw new Error("Unknown snapshot endpoint");
        if(endpoint === "stock") {
          const match = /^(?:HK:|HKEX:)?([0-9]{1,5})(?:\.HK)?$/i.exec(params.ticker || "0700.HK");
          if(!match || !Number(match[1])) throw new Error("Choose a configured HK stock");
          target = `api/hk/stock/${String(Number(match[1])).padStart(4,"0")}.HK.json`;
        } else target = `api/hk/${endpoint}.json`;
      }
      const response = await fetch(target, {cache:"no-store", signal:controller.signal});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || `HK service returned ${response.status}`);
      return body;
    } finally { clearTimeout(timeout); state.requests.delete(controller); }
  }
  function cancel() {
    state.generation++;
    state.requests.forEach(c=>c.abort()); state.requests.clear();
    clearInterval(state.timer); state.timer=null;
    state.charts.forEach(c=>c.destroy()); state.charts=[];
  }
  function chrome() {
    document.body.dataset.market = state.active ? "hk" : "us";
    document.getElementById("market-us").setAttribute("aria-pressed", String(!state.active));
    document.getElementById("market-hk").setAttribute("aria-pressed", String(state.active));
    root.hidden = !state.active; context.hidden = !state.active;
  }
  function select(active) {
    if (active === state.active) return;
    if (active) state.usHash = location.hash || "#home";
    cancel(); state.active=active; chrome();
    const url=new URL(location.href);
    if (active) { url.searchParams.set("market","hk"); url.hash="#home"; }
    else { url.searchParams.delete("market"); url.hash=state.usHash; }
    history.pushState(null,"",url);
    window.route();
  }
  function draw(id, labels, series, {bar=false,zero=false}={}) {
    const canvas=$(id);
    if (!canvas) return;
    if(!series.some(item=>item.values.some(value=>value!=null))) {
      canvas.replaceWith(Object.assign(document.createElement("p"),{className:"hk-empty",textContent:"Historical observations have not been published for this chart."}));
      return;
    }
    if (!window.Chart) { canvas.replaceWith(Object.assign(document.createElement("p"),{textContent:"Chart library unavailable. The source tables remain available below."})); return; }
    const palette=["#ff964d","#70b5d5","#9aa879"];
    state.charts.push(new Chart(canvas,{type:bar?"bar":"line",data:{labels,datasets:series.map((s,i)=>({
      label:s.label,data:s.values,borderColor:palette[i%3],backgroundColor:palette[i%3]+"70",borderWidth:1.7,pointRadius:0,spanGaps:false
    }))},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{labels:{color:"#aaa",boxWidth:14}}},scales:{x:{ticks:{color:"#999",maxTicksLimit:8},grid:{display:false}},
        y:{beginAtZero:zero,ticks:{color:"#999"},grid:{color:"#ffffff0c"}}}}}));
  }
  function setLive(live) {
    if(snapshot) {
      const label = `Hosted snapshot · built ${time(live.built_at)} · ${live.received_count}/${live.requested_count} saved quotes · last receipt ${time(live.as_of)}`;
      context.textContent = label;
      root.querySelectorAll("[data-hk-feed]").forEach(el=>{el.textContent=label+". Refresh requires rebuilding the site from shared S3 data.";});
      root.querySelectorAll("[data-hk-age]").forEach(el=>{
        const quote=live.quotes.find(q=>q.symbol===el.dataset.hkAge);
        el.textContent=quote?`Snapshot · trade ${time(quote.ts_exchange)}`:"Quote not published in the shared snapshot";
      });
      return;
    }
    context.textContent=`Hong Kong · ${live.received_count}/${live.requested_count} quotes · ${live.market_state} · received ${time(live.as_of)}`;
    root.querySelectorAll("[data-hk-feed]").forEach(el=>{
      el.textContent = !live.received_count ? "Quote feed unavailable — retained prices may be out of date."
        : `${live.received_count}/${live.requested_count} quotes · ${live.market_state === 'closed' ? 'Market closed — showing last trades' : live.market_state === 'lunch' ? 'Lunch break — showing last trades' : live.is_stale ? 'Feed stale — showing retained prices' : 'Quote feed connected'} · received ${time(live.as_of)}`;
    });
    const quotes=new Map(live.quotes.map(q=>[q.symbol,q]));
    root.querySelectorAll("[data-hk-price]").forEach(el=>{
      const q=quotes.get(el.dataset.hkPrice); if(q) el.textContent=`HK$ ${number(q.price,2)}`;
    });
    root.querySelectorAll("[data-hk-change]").forEach(el=>{
      const q=quotes.get(el.dataset.hkChange); if(q) {el.textContent=number(q.change_pct,2)+"%";el.className=q.change_pct>=0?"up":"down";}
    });
    root.querySelectorAll("[data-hk-age]").forEach(el=>{
      const q=quotes.get(el.dataset.hkAge); el.textContent=q?`${q.label} · trade ${time(q.ts_exchange)}`:'Quote unavailable · last displayed price retained';
    });
  }
  async function poll(generation) {
    if (snapshot || !state.active || generation!==state.generation || state.polling) return;
    state.polling=true;
    try { const data=await api("live"); if(state.active && generation===state.generation) setLive(data); }
    catch(error) { if(state.active && generation===state.generation && error.name!=="AbortError") {
      context.textContent="HK quote connection unavailable — retrying";
      root.querySelectorAll("[data-hk-feed]").forEach(el=>{el.textContent="Quote connection unavailable. Last displayed prices retained; retrying every 5 seconds.";});
    }} finally {state.polling=false;}
  }
  function quoteRows(rows) {
    return rows.map(row=>`<tr data-hk-search="${esc([row.ticker,row.name,row.name_zh].join(' ').toLowerCase())}">
      <td>${stockLink(row.ticker,row.name)}<span class="sub">${esc(row.name_zh)}</span></td>
      <td class="num" data-hk-price="${row.ticker}">${row.quote?'HK$ '+number(row.quote.price,2):'Unavailable'}</td>
      <td class="num" data-hk-change="${row.ticker}">${row.quote?number(row.quote.change_pct,2)+'%':'—'}</td>
      <td>${metric(row.metrics.views)}</td><td>${metric(row.metrics.edits)}</td>
      <td class="hk-note" data-hk-age="${row.ticker}">${esc(row.quote?.label || 'No quote')}</td></tr>`);
  }
  function home(d) {
    const spikes=d.rows.filter(r=>r.metrics.views.spike||r.metrics.edits.spike).length;
    return `<div class="hk-hero"><span class="hk-chip">HONG KONG · HANG SENG UNIVERSE</span><h1>A closer look at<br>Hong Kong stocks.</h1>
      <p>Follow HKD prices, see when Wikipedia attention rises, and explore the evidence behind each signal.</p>
      <div class="controls"><a class="button primary" href="#now">Explore this week →</a><a class="button" href="#stock/0700.HK">Open a stock</a></div></div>
      <div class="hk-stats">${stat(d.rows.length,'Stocks in the dated HSI roster')}${stat(d.live.received_count,'Quotes available')}${stat(d.attention_stocks,'Stocks with attention records')}${stat(spikes,'Stocks with a latest-week spike')}</div>
      <div class="hk-banner" data-hk-feed></div><div class="hk-method">
      <div class="panel"><h2>Follow the market</h2><p>${snapshot ? "Saved quotes come from the shared S3 snapshot. Rebuilding the hosted site refreshes them." : "HKD quotes refresh every five seconds. Each price retains its exchange timestamp and session status."}</p></div>
      <div class="panel"><h2>Read the attention</h2><p>Daily Wikipedia observations become weekly view and edit counts, compared with the same past-only spike rule used on the US site.</p></div>
      <div class="panel"><h2>Inspect the research</h2><p>Browse saved IC, Sharpe and keep/drop decisions. The five-stock research cohort stays separate from the 95-stock display.</p></div></div>
      <section class="panel"><div class="panel-head"><h2>On the Hong Kong board</h2><a href="#now">All 95 stocks →</a></div>${table(['Company','HKD price','Change','Wikipedia views','Wikipedia edits','Quote status'],quoteRows(d.rows.filter(r=>['0005.HK','0700.HK','1810.HK','3690.HK','9988.HK'].includes(r.ticker))))}</section>${note}`;
  }
  function now(d) {
    return head("This week · Hong Kong",d.attention_window || `Wikipedia views: week of ${date(d.latest_weeks.views)} · edits: week of ${date(d.latest_weeks.edits)}. Each source uses its latest week observed for at least half the covered stocks.`)+
      `<div class="hk-banner" data-hk-feed></div><section class="panel"><div class="toolbar"><h2>Hang Seng stocks <span class="hk-chip">${d.rows.length}</span></h2>
      <label class="controls">Find a stock <input id="hk-search" type="search" placeholder="Name, Chinese name or stock code"></label></div>
      ${table(['Company','HKD price','Change','Wikipedia views','Wikipedia edits','Quote status'],quoteRows(d.rows))}</section>${note}`;
  }
  function stock(d,week) {
    const recent=d.weeks.slice(-104);
    const chosen=d.weeks.find(w=>w.week===week);
    const revisions=d.revisions.filter(r=>!week||r.week===week).slice(0,100);
    const price=d.price_metadata;
    const feeFields=[['shares','Shares requested','100'],['commission_hkd','Commission (HKD)',''],['platform_fee_hkd','Platform fee (HKD)',''],['fx_spread_bps','FX spread (basis points)',''],['fx_fee_usd','FX fee (USD)',''],['transfer_fee_usd','Transfer fee (USD)',''],['hkd_per_usd','HKD per USD override','']];
    return head(`${esc(d.name)} <span class="sub">${esc(d.ticker)} · ${esc(d.name_zh)}</span>`,`HKD prices · Wikipedia ${esc(d.wiki.lang || 'unknown language')} article attention. Choose another stock below.`)+
      `<div class="toolbar"><label class="controls">Stock <select id="hk-stock-select" aria-label="Hong Kong stock">${state.now.rows.map(r=>`<option value="${r.ticker}"${r.ticker===d.ticker?' selected':''}>${esc(r.name)} · ${r.ticker}</option>`).join('')}</select></label><a href="#now">All Hong Kong stocks →</a></div>
      <div class="hk-banner" data-hk-feed></div><div class="hk-stats">${stat(d.quote?'HK$ '+number(d.quote.price,2):'Unavailable','Last trade · nominal HKD',`data-hk-price="${d.ticker}"`)}${stat(d.quote?number(d.quote.change_pct,2)+'%':'—','Daily price change',`data-hk-change="${d.ticker}"`)}${stat(d.sentiment_weeks,'Saved FinBERT weeks with matching evidence')}${stat(date(price?.last_date),'Daily price history through')}</div>
      <p class="hk-note" data-hk-age="${d.ticker}">${esc(d.quote?.label || 'Quote unavailable')}</p>
      ${d.current_attention?`<section class="panel"><div class="panel-head"><h2>Current Wikipedia attention</h2></div><p class="hk-note">Trailing seven published days through ${esc(d.current_attention.as_of)}.</p>${table(['Wikipedia views','Wikipedia edits'],[`<tr><td>${metric(d.current_attention.metrics.views)}</td><td>${metric(d.current_attention.metrics.edits)}</td></tr>`])}</section>`:''}
      <div class="two-col"><section class="panel"><div class="panel-head"><h2>${esc(d.price_label || "Adjusted weekly price · HKD")}</h2></div><div class="hk-plot"><canvas id="hk-price-chart" aria-label="Adjusted HKD price history"></canvas></div>
      <p class="hk-note">${esc(price?.price_basis || 'No price history available')} · ${esc(price?.source || '')}. Charts use one coherent vendor vintage; live nominal prices appear separately.</p></section>
      <section class="panel"><div class="panel-head"><h2>Wikipedia attention against baseline</h2></div><div class="hk-plot"><canvas id="hk-attention-chart" aria-label="Weekly Wikipedia attention ratios"></canvas></div>
      <p class="hk-note">${esc(d.wiki.title || 'No mapped article')} · ${esc(d.wiki.lang || '')} · counts through ${date(d.wiki.end)}. A current partial week uses its daily rate × 7 for the ratio only; missing weeks stay gaps.</p></section></div>
      <section class="panel"><div class="panel-head"><h2>Weekly observations${week?' · selected '+esc(week):''}</h2></div>${table(['Week','Weekly close (HKD)','Wikipedia views','Wikipedia edits','Saved FinBERT tone'],(chosen?[chosen]:recent.slice(-16).reverse()).map(r=>`<tr><td><a href="#stock/${d.ticker}/${r.week}">${r.week}</a></td><td>${number(r.close,2)}</td><td>${metric(r.metrics.views)}</td><td>${metric(r.metrics.edits)}</td><td>${r.tone==null?'Unavailable':number(r.tone,3)}<span class="sub">${esc(r.tone_source || '')}</span></td></tr>`))}
      <p class="hk-note">${esc(d.sentiment_note || "FinBERT scores exist only for saved, revision-matched Wikipedia additions from the original five-stock cohort. Current counts do not imply new sentiment scores.")}</p>${week?`<a href="#stock/${d.ticker}">Clear selected week</a>`:''}</section>
      <section class="panel"><div class="panel-head"><h2>USD purchase estimate</h2><span class="hk-chip">EDITABLE BROKER FEES</span></div><p class="hk-note">Uses the existing HK cost service for dated HK levies, board lots and FX provenance. Blank fees mean unknown. Results with unknown fees are a known-cost subtotal, not an all-in quote.</p>
      <form id="hk-cost-form"><div class="hk-fees">${feeFields.map(([key,label,value])=>`<label>${label}<input name="${key}" type="number" min="${key==='shares'?1:0}" step="${key==='shares'?1:'any'}" value="${value}" ${key==='shares'?'required':''}></label>`).join('')}
      <label>Settlement fees<select name="settlement_pass_through" aria-label="Settlement fee handling"><option value="">Unknown</option><option value="true">Passed through</option><option value="false">Included by broker</option></select></label></div><button class="primary" type="submit">Estimate USD needed</button></form><div id="hk-cost-result" role="status" aria-live="polite"></div></section>
      <section class="panel"><div class="panel-head"><h2>Wikipedia revision evidence</h2>${d.wiki.article_url?`<a href="${esc(d.wiki.article_url)}" target="_blank" rel="noopener noreferrer">Open source article ↗</a>`:''}</div>
      <p class="hk-note">${esc(d.wiki.source_note || 'Article-level activity may include wider parent-company topics; it is not a count of stock-specific news.')} ${week?'Filtered to the selected week.':'Latest 100 revisions shown.'}</p>
      <div class="hk-revisions">${table(['Revision (UTC)','ID','Edit summary'],revisions.map(r=>`<tr><td>${esc(r.timestamp)}</td><td>${r.url?`<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.revid)} ↗</a>`:'Not published'}</td><td>${esc(r.comment || 'No summary')}</td></tr>`))}</div></section>${note}`;
  }
  function spikes(d) {
    return head("Spikes · Hong Kong","Weeks when Wikipedia attention rose beyond its prior baseline. This is an attention signal, not a price-momentum strategy.")+
      `<section class="panel"><div class="toolbar"><h2>${number(d.rows.length)} recorded source-week spikes</h2><label class="controls">Source <select id="hk-spike-source"><option value="all">All Wikipedia sources</option><option value="views">Wikipedia views</option><option value="edits">Wikipedia edits</option></select></label></div>
      <p class="hk-note">Shared rule: prior ${d.rule.baseline_weeks} weeks, median baseline; ratio and robust-z gates. Incomplete historical weeks are excluded from comparison. Click a stock to inspect that week.</p>
      ${table(['Company','Week','Source','Observed count','Ratio','Robust z'],d.rows.map(r=>`<tr data-hk-source="${r.source}"><td>${stockLink(r.ticker,r.name,r.week)}</td><td>${r.week}${r.partial?' · partial':''}</td><td>${esc(r.source_label)} · ${esc(r.language)}</td><td>${number(r.count)}</td><td class="hk-flag">${ratio(r.ratio)}</td><td>${number(r.rz,2)}</td></tr>`))}</section>${note}`;
  }
  function strategies(d) {
    return head("Strategies · Hong Kong","Saved out-of-sample research results, displayed without running or changing any strategy.")+
      `<div class="hk-banner">${esc(d.note)} ${esc(d.native_confirmation)}.</div><section class="panel"><div class="panel-head"><h2>Archived strategy results</h2><span class="hk-chip">FIVE-STOCK COHORT</span></div>
      ${table(['Strategy and behavior','Test IC','Test Sharpe','Keep / drop','Why'],d.rows.map(r=>`<tr><td><b>${esc(r.strategy.replaceAll('_',' '))}</b><span class="sub">${esc(r.what_it_does)}</span></td><td>${number(r.ic_test,4)}</td><td>${number(r.sharpe_test,3)}</td><td class="hk-flag">${esc(r.decision)}</td><td>${esc(r.reason)}</td></tr>`))}
      <p class="hk-note">Train ${d.train.join(' to ')} · test ${d.test.join(' to ')}. These saved research statistics do not evaluate the full 95-stock display or the refreshed holdout data.</p></section>
      <section class="panel"><div class="panel-head"><h2>Saved test equity curves</h2></div><div class="hk-plot"><canvas id="hk-strategy-chart" aria-label="Saved HK strategy growth curves"></canvas></div><p class="hk-note">Growth of HK$1 from the original saved net daily returns. No backtest or FX conversion is rerun.</p></section>`;
  }
  function status(d) {
    return head("Data status · Hong Kong","Coverage, source boundaries and freshness for the Hong Kong pages only.")+
      `<div class="hk-banner" data-hk-feed></div><div class="hk-stats">${stat(d.roster_count,'Stocks in the dated roster')}${stat(d.historical_price_stocks,'Historical price histories')}${stat(d.attention_stocks,'Stocks with attention records')}${stat(d.refreshed_attention_stocks,'Refreshed display caches')}</div>
      <section class="panel"><div class="panel-head"><h2>What is available</h2></div>${facts([['HSI roster snapshot',d.roster_as_of+' · current snapshot, not historical membership'],['Quote delivery',snapshot?'Build-time snapshot from shared S3; no browser polling':'5 seconds · exchange and receipt timestamps retained'],['Calendar','XHKG · Hong Kong time · lunch, half-days and holidays'],['Quote currency','HKD · USD conversion is a separate cost estimate'],['Wikipedia languages',d.wiki_languages_label || `${d.wiki_english} English / ${d.wiki_chinese} Chinese`],['Reddit corpus','Unavailable for HK; no alias counts substituted'],['Saved FinBERT cohort',d.saved_finbert_cohort_stocks+' stocks · published scores only'],['Research holdout begins',d.research_cutoff+' · new display data is not backtest input']])}</section>
      <section class="panel"><div class="panel-head"><h2>Source checks</h2></div><ul>${d.source_notes.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>
      ${Object.keys(d.attention_errors).length?table(['Stock','Source gap'],Object.entries(d.attention_errors).map(([code,errors])=>`<tr><td>${stockLink(code)}</td><td>${esc(Object.entries(errors).map(([k,v])=>k+': '+v).join('; '))}</td></tr>`)):'<p>No source errors recorded in the display cache.</p>'}
      <p class="hk-note">${snapshot ? "This hosted copy is refreshed by rebuilding from shared S3 tables and publishing the generated files. Opening the page does not collect data or rebuild research." : "Quote refresh happens automatically while Hong Kong is selected. Opening a page never rebuilds research."}</p></section>`;
  }
  async function costs(event,generation,ticker) {
    event.preventDefault(); const target=$("hk-cost-result"); target.textContent="Calculating…";
    const params=Object.fromEntries(new FormData(event.target));params.ticker=ticker;
    try { const d=await api("order_estimate",params); if(generation!==state.generation)return;
      const e=d.estimate;
      target.className='';
      target.innerHTML=`<h3>${esc(e.label)}: US$ ${number(e.cash_usd,2)}</h3>`+
        facts([['Shares priced',`${e.executed_shares} of ${e.requested_shares} requested · board lot ${e.board_lot}`],['Purchase value','HK$ '+number(e.gross_hkd,2)],['Known HKD fees','HK$ '+number(e.total_fees_hkd,2)],['Cash in HKD','HK$ '+number(e.cash_hkd,2)],['FX reference',`${number(e.fx?.hkd_per_usd,4)} HKD per USD · ${date(e.fx?.observed_date)}`],['Fee schedule date',e.trade_date]])+
        (e.fees_hkd?table(['Dated charge','HKD'],Object.entries(e.fees_hkd).map(([key,value])=>`<tr><td>${esc(key.replaceAll('_',' '))}</td><td>${(key==='broker_commission'&&e.assumptions?.commission_hkd==null)||(key==='platform_fee'&&e.assumptions?.platform_fee_hkd==null)?'Unknown':number(value,2)}</td></tr>`)):'')+
        `<p class="hk-note">${e.complete?'All editable fee assumptions supplied.':'Unknown charges: '+esc((e.unknown_charges||[]).map(key=>key.replaceAll('_',' ')).join(', '))+'.'} Excludes ${esc((e.excluded||[]).join(', '))}.</p>`+
        (e.fx?.source?.startsWith('https://')?`<p class="hk-note"><a href="${esc(e.fx.source)}" target="_blank" rel="noopener noreferrer">FX reference source ↗</a></p>`:'');
    } catch(error) { if(generation===state.generation) {target.className="hk-error";target.textContent=error.message;} }
  }
  async function route() {
    if(!state.active)return;
    cancel();const generation=state.generation;
    const [requested,ticker,week]=location.hash.replace(/^#/,"").split('/');
    const view=views.includes(requested)?requested:'home';state.view=view;state.ticker=ticker;
    chrome();document.body.dataset.view=view;
    document.querySelectorAll('.topnav a').forEach(a=>a.dataset.view===view?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current'));
    root.innerHTML='<p class="hk-empty" role="status">Loading Hong Kong data…</p>';
    try {
      if(!state.now)state.now=await api('now');
      if(generation!==state.generation)return;
      let data=state.now;
      if(view==='stock')data=await api('stock',{ticker:ticker||'0700.HK'});
      if(view==='spikes')data=await api('spike_weeks');
      if(view==='strategies')data=await api('strategy_log');
      if(view==='data')data=await api('status');
      if(generation!==state.generation)return;
      root.innerHTML=({home,now,stock:d=>stock(d,week),spikes,strategies,data:status}[view])(data);
      const refresh=$("hk-refresh");if(refresh)refresh.onclick=()=>{state.now=null;route();};
      const search=$("hk-search");if(search)search.oninput=()=>root.querySelectorAll('[data-hk-search]').forEach(row=>{row.hidden=!row.dataset.hkSearch.includes(search.value.toLowerCase().trim());});
      const selector=$("hk-stock-select");if(selector)selector.onchange=()=>{location.hash='#stock/'+selector.value;};
      const source=$("hk-spike-source");if(source)source.onchange=()=>root.querySelectorAll('[data-hk-source]').forEach(row=>{row.hidden=source.value!=='all'&&row.dataset.hkSource!==source.value;});
      const form=$("hk-cost-form");if(form)form.onsubmit=event=>costs(event,generation,data.ticker);
      if(view==='stock') {
        const rows=data.weeks.slice(-104);
        draw('hk-price-chart',rows.map(r=>r.week),[{label:'Adjusted HKD close',values:rows.map(r=>r.close)}]);
        draw('hk-attention-chart',rows.map(r=>r.week),['views','edits'].map(s=>({label:'Wiki '+s+' / baseline',values:rows.map(r=>r.metrics[s].ratio)})));
      }
      if(view==='strategies') {
        const entries=Object.entries(data.series);
        draw('hk-strategy-chart',entries[0]?.[1].dates||[],entries.map(([name,series])=>({label:name.replaceAll('_',' '),values:series.growth})));
      }
      setLive(data.live?.quotes?data.live:state.now.live);
      if(snapshot && form) {
        form.querySelectorAll("input,select,button").forEach(el=>{el.disabled=true;});
        $("hk-cost-result").textContent="USD estimates require a running quote/cost service. This hosted snapshot does not contact a local server.";
      }
      if(!snapshot) { poll(generation);state.timer=setInterval(()=>poll(generation),5000); }
    } catch(error) { if(generation!==state.generation)return;
      root.innerHTML=`<div class="page-head"><h1>Hong Kong data unavailable</h1></div><p class="hk-banner" role="alert">${esc(error.message)}</p><button type="button" id="hk-retry">Retry</button>`;
      $("hk-retry").onclick=()=>{state.now=null;route();};
    }
  }
  window.HKDashboard={active:()=>state.active,route};
  document.getElementById('market-hk').onclick=()=>select(true);
  document.getElementById('market-us').onclick=()=>select(false);
  window.addEventListener('popstate',()=>{
    const active=new URLSearchParams(location.search).get('market')==='hk';
    if(active!==state.active){cancel();state.active=active;chrome();window.route();}
  });
  chrome();
})();
