// Live dashboard: every number comes from /api/analytics (SQL over the SQLite database).
(function () {
  const CFG = window.ECA_CONFIG;
  const root = document.documentElement;
  const $ = id => document.getElementById(id);
  const cssv = n => getComputedStyle(root).getPropertyValue(n).trim();
  const fmt$ = v => '$' + Math.round(v).toLocaleString();
  const pct = v => (v * 100).toFixed(1) + ' %';
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mlabel = m => MON[+m.slice(5, 7) - 1] + " '" + m.slice(2, 4);

  // ---------------- state ----------------
  const params = new URLSearchParams(location.search);
  let TAB = params.get('tab') === 'customers' ? 'customers' : 'overview';
  let DATA = null, inflight = null, version = CFG.initialVersion;
  const charts = {}, VL = {}, prevK = {};
  ['country', 'segment', 'category'].forEach(k => { const v = params.get(k); if (v) $('f' + k[0].toUpperCase() + k.slice(1)).value = v; });

  // ---------------- palette + Chart.js defaults (re-run on theme change) ----------------
  let P = {};
  function palette() {
    const dark = root.dataset.theme === 'dark';
    P = { navy: cssv('--brandInk'), amber: cssv('--amber'), teal: cssv('--teal'), red: cssv('--red'), blue: cssv('--blue'),
      ice: cssv('--ice'), ink: cssv('--ink'), grid: cssv('--grid'), tick: cssv('--tick'), tip: cssv('--tooltipBg'),
      surface: cssv('--surface'), set: [cssv('--blue'), cssv('--amber'), cssv('--teal'), cssv('--red'), '#A78BFA'],
      mint: dark ? '#0E9F6E' : '#6EE7B7', softG: dark ? '#0B5E45' : '#A7F3D0', softR: dark ? '#7F1D1D' : '#FECACA',
      bubble: dark ? 'rgba(96,165,250,.40)' : 'rgba(37,99,235,.40)' };
    const D = Chart.defaults;
    D.font.family = 'Calibri, "Segoe UI", system-ui, sans-serif'; D.font.size = 13.5; D.color = P.tick;
    D.animation = { duration: 600, easing: 'easeOutQuart' };
    D.plugins.tooltip = { ...D.plugins.tooltip, backgroundColor: P.tip, titleColor: '#fff', bodyColor: '#E5E7EB', padding: 11,
      cornerRadius: 8, displayColors: false, titleFont: { weight: '700', size: 13.5 }, bodyFont: { size: 13 } };
    D.plugins.legend.labels = { ...D.plugins.legend.labels, usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 11, padding: 16, font: { size: 12.5 }, color: P.tick };
    D.scale.title = { display: true, color: P.tick, font: { size: 13, weight: '600' }, padding: { top: 6, bottom: 4 } };
    D.scale.ticks = { ...D.scale.ticks, font: { size: 12.5 }, color: P.tick };
    D.scale.grid = { ...D.scale.grid, color: P.grid };
    D.scale.border = { display: false };
  }
  // value labels drawn above bars
  Chart.register({ id: 'vl', afterDatasetsDraw(c) {
    const f = VL[c.canvas.id]; if (!f) return; const ctx = c.ctx; ctx.save();
    ctx.font = '600 12.5px Calibri, "Segoe UI", sans-serif'; ctx.fillStyle = P.ink;
    c.data.datasets.forEach((ds, i) => { const m = c.getDatasetMeta(i); if (m.hidden || m.type !== 'bar') return;
      m.data.forEach((el, j) => { const v = ds.data[j]; if (v == null) return;
        if (c.options.indexAxis === 'y') { ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(f(v, i), el.x + 6, el.y); }
        else { ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillText(f(v, i), el.x, el.y - 4); } }); });
    ctx.restore(); } });

  function mk(id, cfg, vlFmt) {
    VL[id] = vlFmt || null;
    const ex = charts[id];
    if (ex && ex.config.type === cfg.type) { ex.data = cfg.data; ex.options = cfg.options; ex.update(); return; }
    if (ex) ex.destroy();
    charts[id] = new Chart($(id), cfg);
  }
  const base = (o = {}) => ({ maintainAspectRatio: false, ...o });
  const bar = (labels, data, color, o = {}) => ({ type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: color, borderRadius: 6, maxBarThickness: 56, hoverBackgroundColor: P.amber }] },
    options: base({ plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => o.fmt ? o.fmt(c.raw) : c.raw } } },
      scales: { x: { grid: { display: false }, title: { text: o.xt || '' } },
        y: { beginAtZero: true, grace: '12%', title: { text: o.yt || '' }, ticks: { callback: v => o.tick ? o.tick(v) : v } } }, ...(o.extra || {}) }) });

  // ---------------- KPIs ----------------
  function countUp(el, to, fmt) {
    const key = el.dataset.k, from = prevK[key] ?? 0; prevK[key] = to;
    const t0 = performance.now(), d = 650;
    (function step(t) { const p = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(from + (to - from) * e); if (p < 1) requestAnimationFrame(step); })(t0);
  }
  function kpiRow(el, items, tag, flash) {
    if (el.children.length !== items.length)
      el.innerHTML = items.map((k, i) => `<div class="kpi ${k[3] || ''}"><div class="l">${k[0]}</div><div class="v" data-k="${tag}${i}"></div><div class="s"></div></div>`).join('');
    items.forEach((k, i) => { const c = el.children[i]; const v = c.querySelector('.v');
      if (flash && prevK[v.dataset.k] !== undefined && Math.abs(prevK[v.dataset.k] - k[1]) > 1e-9) { c.classList.remove('bump'); void c.offsetWidth; c.classList.add('bump'); }
      countUp(v, k[1], k[2]); c.querySelector('.s').textContent = k[4]; });
  }

  // ---------------- data loading ----------------
  function filters() { return { country: $('fCountry').value, segment: $('fSegment').value, category: $('fCategory').value }; }
  async function load(opts = {}) {
    const f = filters();
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    const shown = new URLSearchParams(qs); if (TAB !== 'overview') shown.set('tab', TAB);
    history.replaceState(null, '', location.pathname + (shown.toString() ? '?' + shown : ''));
    $('activeChips').innerHTML = Object.values(f).filter(Boolean).map(v => `<span class="chip">${v}</span>`).join('') || '<span class="chip">all orders</span>';
    $('reset').disabled = !Object.values(f).some(Boolean);
    if (inflight) inflight.abort();               // newest request wins — rapid clicks never race
    inflight = new AbortController();
    $('scope').classList.add('loading');
    try {
      const r = await fetch(CFG.api + '?' + qs, { signal: inflight.signal });
      DATA = await r.json();
      paint(opts.flash);
    } catch (e) {
      if (e.name !== 'AbortError') ECA.toast('Could not reach the server — is the app still running?');
    } finally { $('scope').classList.remove('loading'); }
  }

  // ---------------- painting ----------------
  function paint(flash) {
    const d = DATA; if (!d) return;
    $('scopeCount').textContent = d.n === d.total_orders ? `· all ${d.total_orders.toLocaleString()} orders in the database`
      : `· ${d.n.toLocaleString()} of ${d.total_orders.toLocaleString()} orders (${pct(d.n / d.total_orders)})`;
    if (!d.n) {
      $('kpis').innerHTML = $('kpis2').innerHTML = '<div class="kpi wide"><div class="l">No match</div><div class="v">0</div><div class="s">No orders match these filters — widen them or press Reset.</div></div>';
      Object.keys(charts).forEach(k => { charts[k].destroy(); delete charts[k]; });
      document.querySelectorAll('.interp').forEach(i => i.innerHTML = '');
      return;
    }
    if (TAB === 'overview') paintOverview(d, flash); else paintCustomers(d, flash);
  }

  function paintOverview(d, flash) {
    const K = d.kpis;
    kpiRow($('kpis'), [['Orders', K.orders, v => Math.round(v).toLocaleString(), '', 'valid orders in view'],
      ['Net revenue', K.revenue, fmt$, '', 'delivered orders only'],
      ['Avg order value', K.aov, fmt$, '', 'mean of total_amount'],
      ['Median order value', K.median, fmt$, '', 'the typical order']], 'a', flash);

    const cats = d.category;
    mk('cCat', bar(cats.map(c => c.k), cats.map(c => c.rev / 1000), P.navy,
      { fmt: v => '$' + v.toFixed(1) + 'k', tick: v => '$' + v + 'k', xt: 'Product category', yt: 'Net revenue (USD thousands)' }), v => '$' + v.toFixed(1) + 'k');
    let cum = 0, k80 = 0; for (const c of cats) { cum += c.rev; k80++; if (cum / K.revenue >= 0.8) break; }
    $('iCat').innerHTML = `<b>Interpretation</b> ${cats[0].k} leads with ${fmt$(cats[0].rev)} — ${pct(cats[0].rev / (K.revenue || 1))} of net revenue in this view. The top ${k80} categor${k80 > 1 ? 'ies' : 'y'} together account for at least 80 %.`;

    const m = d.monthly;
    mk('cMonth', { type: 'bar', data: { labels: m.map(x => mlabel(x.m)), datasets: [
        { type: 'line', label: 'Net revenue (USD k)', data: m.map(x => x.rev / 1000), borderColor: P.navy, backgroundColor: P.navy, yAxisID: 'y1', tension: .3, pointRadius: 3.5, pointHoverRadius: 6, borderWidth: 2.5 },
        { type: 'bar', label: 'Orders', data: m.map(x => x.n), backgroundColor: P.ice, hoverBackgroundColor: P.amber, yAxisID: 'y', borderRadius: 4 }] },
      options: base({ interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom' },
        tooltip: { displayColors: true, callbacks: { label: c => c.dataset.label + ': ' + (c.datasetIndex === 0 ? '$' + c.raw.toFixed(1) + 'k' : c.raw) } } },
        scales: { x: { grid: { display: false }, title: { text: 'Month' } }, y: { position: 'left', beginAtZero: true, title: { text: 'Orders' } },
          y1: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { text: 'Net revenue (USD k)' }, ticks: { callback: v => '$' + v + 'k' } } } }) });
    const peak = m.reduce((a, b) => (b.rev > a.rev ? b : a), m[0]), last = m[m.length - 1];
    $('iMonth').innerHTML = `<b>Interpretation</b> The strongest month in this view is ${mlabel(peak.m)} with ${fmt$(peak.rev)} from ${peak.n} orders — the year-end peak. The latest month, ${mlabel(last.m)}, has ${last.n} orders; new orders you add appear here immediately.`;

    mk('cHist', bar(d.histogram.labels, d.histogram.counts, P.blue, { fmt: v => v, xt: 'Order value band (USD)', yt: 'Number of orders' }), v => v);
    $('iHist').innerHTML = `<b>Interpretation</b> Right-skewed: the mean (${fmt$(K.aov)}) sits well above the median (${fmt$(K.median)}). Most orders are under $150 and a long tail of large Electronics orders pulls the mean up, so the median is the better "typical order".`;

    const st = d.status;
    mk('cStatus', { type: 'doughnut', data: { labels: st.map(s => `${s.k} · ${pct(s.n / d.n)}`),
        datasets: [{ data: st.map(s => s.n), backgroundColor: [P.teal, P.red, P.amber], borderWidth: 2, borderColor: P.surface, hoverOffset: 8 }] },
      options: base({ cutout: '62%', plugins: { legend: { position: 'right' }, tooltip: { callbacks: { label: c => c.raw.toLocaleString() + ' orders' } } } }) });
    $('iStatus').innerHTML = `<b>Interpretation</b> ${pct(K.return_rate + K.cancel_rate)} of orders end returned or cancelled and generate no net revenue — about ${fmt$(K.refunded)} of refunded value in this view.`;
  }

  function paintCustomers(d, flash) {
    const R = d.retention, C = d.correlation, K = d.kpis;
    kpiRow($('kpis2'), [['Customers', R.customers, v => Math.round(v).toLocaleString(), '', 'with at least one order in view'],
      ['Repeat rate', R.repeat_rate, pct, 'good', 'ordered more than once'],
      ['Dormant > 180 days', R.dormant_share, pct, 'warn', 'win-back target'],
      ['Delivery ↔ rating', C.r, v => v.toFixed(2), '', `Pearson r · ${C.n.toLocaleString()} reviews`]], 'b', flash);

    const S = d.segments;
    mk('cSeg', { type: 'bar', data: { labels: S.map(s => s.k), datasets: [
        { label: 'Orders per customer', data: S.map(s => s.orders_per_customer), backgroundColor: P.amber, yAxisID: 'y', borderRadius: 6, maxBarThickness: 58 },
        { label: 'Average order value (USD)', data: S.map(s => s.aov), backgroundColor: P.navy, yAxisID: 'y1', borderRadius: 6, maxBarThickness: 58 }] },
      options: base({ plugins: { legend: { position: 'bottom' }, tooltip: { displayColors: true, callbacks: { label: c => c.dataset.label + ': ' + (c.datasetIndex ? fmt$(c.raw) : c.raw.toFixed(2)) } } },
        scales: { x: { grid: { display: false }, title: { text: 'Customer segment' } }, y: { beginAtZero: true, grace: '18%', title: { text: 'Orders per customer' } },
          y1: { position: 'right', beginAtZero: true, grace: '18%', grid: { drawOnChartArea: false }, title: { text: 'Average order value (USD)' }, ticks: { callback: v => '$' + v } } } }) },
      (v, i) => i ? '$' + Math.round(v) : v.toFixed(1));
    $('iSeg').innerHTML = S.length > 1
      ? `<b>Interpretation</b> ${S[S.length - 1].k} customers place ${S[S.length - 1].orders_per_customer.toFixed(1)} orders each versus ${S[0].orders_per_customer.toFixed(1)} for ${S[0].k}, while average order value stays flat (${S.map(s => fmt$(s.aov)).join(' / ')}). Lifetime value (${S.map(s => fmt$(s.rev_per_customer)).join(' / ')}) comes from frequency, not bigger baskets.`
      : `<b>Interpretation</b> Single segment in view: ${S[0].orders_per_customer.toFixed(1)} orders per customer, ${fmt$(S[0].aov)} average order value.`;

    const ch = d.churn, cust = R.customers;
    mk('cChurn', { type: 'doughnut', data: { labels: [`High · >180 days · ${pct(ch.high / cust)}`, `Medium · 91–180 days · ${pct(ch.medium / cust)}`, `Low · ≤90 days · ${pct(ch.low / cust)}`],
        datasets: [{ data: [ch.high, ch.medium, ch.low], backgroundColor: [P.red, P.amber, P.teal], borderWidth: 2, borderColor: P.surface, hoverOffset: 8 }] },
      options: base({ cutout: '62%', plugins: { legend: { position: 'right' }, tooltip: { callbacks: { label: c => c.raw.toLocaleString() + ' customers' } } } }) });
    $('iChurn').innerHTML = `<b>Interpretation</b> ${pct(R.repeat_rate)} of these ${cust.toLocaleString()} customers have ordered more than once and the top 20 % account for ${pct(R.top20_share)} of revenue — but ${pct(R.dormant_share)} have not ordered in over 180 days (measured from ${ch.snapshot}, the day after the latest order). That dormant group is the win-back target.`;

    const co = d.country;
    mk('cCountry', bar(co.map(c => c.k), co.map(c => c.rev / 1000), P.navy, { fmt: v => '$' + v.toFixed(1) + 'k',
      extra: { indexAxis: 'y', scales: { x: { beginAtZero: true, grace: '15%', title: { text: 'Net revenue (USD thousands)' }, ticks: { callback: v => '$' + v + 'k' } },
        y: { grid: { display: false }, title: { text: 'Country' } } } } }), v => '$' + v.toFixed(1) + 'k');
    $('iCountry').innerHTML = `<b>Interpretation</b> ${co[0].k} leads with ${pct(co[0].rev / (K.revenue || 1))} of revenue from ${co[0].c} customers — ${fmt$(co[0].rev / co[0].c)} each.`;

    const chs = d.channel, avg = d.rev_per_customer, worst = chs[chs.length - 1];
    mk('cChan', bar(chs.map(c => c.k), chs.map(c => c.rpc), chs.map(c => c.rpc < avg * 0.85 ? P.red : P.amber),
      { fmt: v => fmt$(v), tick: v => '$' + v, xt: 'Acquisition channel', yt: 'Net revenue per customer (USD)' }), v => fmt$(v));
    $('iChan').innerHTML = `<b>Interpretation</b> Average revenue per customer is ${fmt$(avg)}. ${worst.k} is the weakest at ${fmt$(worst.rpc)} (${((worst.rpc / avg - 1) * 100).toFixed(0)} % versus average); ${chs[0].k} is the strongest at ${fmt$(chs[0].rpc)}.`;

    const ages = Object.keys(d.payment_by_age), pays = ['Credit Card', 'E-Wallet', 'Bank Transfer', 'Cash on Delivery', 'PayPal'];
    mk('cPay', { type: 'bar', data: { labels: ages, datasets: pays.map((p, i) => ({ label: p,
        data: ages.map(a => 100 * (d.payment_by_age[a][p] || 0)), backgroundColor: P.set[i], borderRadius: 3, maxBarThickness: 44 })) },
      options: base({ indexAxis: 'y', interaction: { mode: 'index' }, plugins: { legend: { position: 'bottom' },
        tooltip: { displayColors: true, callbacks: { label: c => c.dataset.label + ': ' + c.raw.toFixed(1) + ' %' } } },
        scales: { x: { stacked: true, max: 100, title: { text: 'Share of orders (%)' }, ticks: { callback: v => v + ' %' } },
          y: { stacked: true, grid: { display: false }, title: { text: 'Age group' } } } }) });
    const top = a => Object.entries(d.payment_by_age[a]).sort((x, y) => y[1] - x[1])[0];
    $('iPay').innerHTML = `<b>Interpretation</b> ` + ages.map(a => `${a}: ${top(a)[0]} ${pct(top(a)[1])}`).join(' · ') + ` — the most-used method in each age group. A mobile-first checkout with card and E-Wallet options covers every group.`;

    const B = d.delivery_bands, first = B.find(b => b.rating != null), lastB = [...B].reverse().find(b => b.rating != null);
    mk('cDeliv', { type: 'bar', data: { labels: B.map(b => b.band), datasets: [{ data: B.map(b => b.rating), backgroundColor: [P.teal, P.mint, P.amber, P.red], borderRadius: 6, maxBarThickness: 70 }] },
      options: base({ plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => (c.raw ?? 0).toFixed(2) + ' ★  ·  ' + B[c.dataIndex].n + ' reviews' } } },
        scales: { x: { grid: { display: false }, title: { text: 'Delivery time band' } }, y: { min: 0, max: 5, title: { text: 'Mean review rating (1–5 ★)' } } } }) },
      v => v.toFixed(2) + ' ★');
    $('iDeliv').innerHTML = first && lastB ? `<b>Interpretation</b> Mean rating falls from ${first.rating.toFixed(2)}★ (${first.band}) to ${lastB.rating.toFixed(2)}★ (${lastB.band}). Pearson r = ${C.r.toFixed(2)} across ${C.n.toLocaleString()} reviewed orders — delivery speed is the clearest lever on satisfaction.` : '<b>Interpretation</b> Not enough reviewed orders in this view.';

    mk('cScatter', { type: 'bubble', data: { datasets: [
        { label: 'Reviews', data: d.scatter.map(p => ({ x: p.x, y: p.y, r: Math.sqrt(p.c) * 2.2, c: p.c })), backgroundColor: P.bubble, borderColor: P.blue, borderWidth: 1 },
        { type: 'line', label: 'Trend · r = ' + C.r.toFixed(2), data: [{ x: 1, y: C.intercept + C.slope }, { x: 11, y: C.intercept + C.slope * 11 }], borderColor: P.red, borderWidth: 2.5, borderDash: [6, 4], pointRadius: 0 }] },
      options: base({ plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: c => c.datasetIndex ? '' : `${c.raw.x} days → ${c.raw.y} ★  ·  ${c.raw.c} reviews` } } },
        scales: { x: { min: 0, max: 12, title: { text: 'Delivery time (days)' }, grid: { display: false }, ticks: { stepSize: 1 } },
          y: { min: 0.5, max: 5.5, ticks: { stepSize: 1, callback: v => v + ' ★' }, title: { text: 'Review rating' } } } }) });
    $('iScatter').innerHTML = `<b>Interpretation</b> Bubble size is the number of reviews at each point. The fitted trend falls ${Math.abs(C.slope).toFixed(2)} stars per extra day of delivery (r = ${C.r.toFixed(2)}).`;

    const rc = d.returns_by_category;
    mk('cRet', bar(rc.map(c => c.k), rc.map(c => c.rate * 100), rc.map((c, i) => i === 0 ? P.red : P.navy),
      { fmt: v => v.toFixed(1) + ' %', tick: v => v + ' %', xt: 'Product category', yt: 'Return rate (% of orders)' }), v => v.toFixed(1) + ' %');
    $('iRet').innerHTML = `<b>Interpretation</b> ${rc[0].k} is returned most often (${pct(rc[0].rate)}), ${rc[rc.length - 1].k} least (${pct(rc[rc.length - 1].rate)}). In the notebook the chi-square test across categories was not significant (p = 0.23), so treat the ranking as indicative.`;

    const rs = d.rating_by_status;
    mk('cRateStatus', { type: 'bar', data: { labels: rs.map(r => r.s), datasets: [
        { label: 'Mean rating (★)', data: rs.map(r => r.rating), backgroundColor: [P.teal, P.red], borderRadius: 6, maxBarThickness: 80, yAxisID: 'y' },
        { label: 'Share of 1–2 ★ reviews (%)', data: rs.map(r => r.low == null ? null : r.low * 100), backgroundColor: [P.softG, P.softR], borderRadius: 6, maxBarThickness: 80, yAxisID: 'y1' }] },
      options: base({ plugins: { legend: { position: 'bottom' }, tooltip: { displayColors: true, callbacks: { label: c => c.datasetIndex ? '1–2 ★ share: ' + c.raw.toFixed(1) + ' %' : 'Mean rating: ' + c.raw.toFixed(2) + ' ★' } } },
        scales: { x: { grid: { display: false }, title: { text: 'Order status' } }, y: { min: 0, max: 5, title: { text: 'Mean review rating (★)' } },
          y1: { position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false }, title: { text: 'Share of 1–2 ★ reviews (%)' }, ticks: { callback: v => v + ' %' } } } }) },
      (v, i) => i ? v.toFixed(1) + ' %' : v.toFixed(2) + ' ★');
    const [dl, rt] = rs;
    $('iRateStatus').innerHTML = dl.rating != null && rt.rating != null
      ? `<b>Interpretation</b> Delivered orders average ${dl.rating.toFixed(2)}★ against ${rt.rating.toFixed(2)}★ for returned ones, and ${pct(rt.low)} of returned-order reviews are 1–2 stars versus ${pct(dl.low)} of delivered ones. A return is a satisfaction event, not just a logistics cost.`
      : '<b>Interpretation</b> Not enough reviewed delivered and returned orders in this view to compare.';
  }

  // ---------------- interactions ----------------
  function showTab(name) {
    TAB = name;
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('section.tab').forEach(s => s.classList.remove('active'));
    const sec = $(name); void sec.offsetWidth; sec.classList.add('active');
    const shown = new URLSearchParams(location.search); if (name === 'overview') shown.delete('tab'); else shown.set('tab', name);
    history.replaceState(null, '', location.pathname + (shown.toString() ? '?' + shown : ''));
    paint();
    requestAnimationFrame(() => sec.querySelectorAll('canvas').forEach(cv => charts[cv.id] && charts[cv.id].resize()));
  }
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
  ['fCountry', 'fSegment', 'fCategory'].forEach(id => $(id).addEventListener('change', () => load()));
  $('reset').onclick = () => { $('fCountry').value = $('fSegment').value = $('fCategory').value = ''; load(); };
  document.addEventListener('keydown', e => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (['input', 'select', 'textarea'].includes(tag) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === '1') showTab('overview');
    if (e.key === '2') showTab('customers');
    if (e.key.toLowerCase() === 'r' && !$('reset').disabled) $('reset').click();
  });
  ECA.onTheme.push(() => { palette(); Object.keys(charts).forEach(k => { charts[k].destroy(); delete charts[k]; }); paint(); });

  // ---------------- live refresh: poll the DB change counter ----------------
  async function poll() {
    if (document.hidden) return;
    try {
      const v = await (await fetch(CFG.version, { cache: 'no-store' })).json();
      $('liveText').textContent = `Live · ${v.orders.toLocaleString()} orders`;
      if (v.version !== version) {
        version = v.version;
        ECA.toast('Database changed — dashboard refreshed');
        load({ flash: true });
      }
    } catch (e) { $('liveText').textContent = 'Offline'; }
  }
  setInterval(poll, 4000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

  palette();
  if (TAB !== 'overview') showTab(TAB);
  load();
  poll();
})();
