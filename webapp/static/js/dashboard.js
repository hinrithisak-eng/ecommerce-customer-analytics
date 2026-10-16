// Analytics pages. One fetch of /api/analytics per filter change; every chart and
// table on the page is drawn from that response.
(function () {
  const CFG = window.DASH;
  const $ = id => document.getElementById(id);
  const root = document.documentElement;
  const sel = { country: $('fCountry'), segment: $('fSegment'), category: $('fCategory') };
  const charts = {};
  const endLabel = {};          // canvas id -> formatter for the value printed at the end of each bar
  let last = null, ctrl = null, prevKpi = {};

  // ------------------------------------------------------------------ formatting
  const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
  const nf2 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const num = v => nf0.format(v);
  const usd = v => '$' + nf0.format(v);
  const usd2 = v => '$' + nf2.format(v);
  const usdK = v => Math.abs(v) >= 1000 ? '$' + (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : '$' + nf0.format(v);
  const pct = (v, d = 1) => (v * 100).toFixed(d) + '%';
  const monthName = m => new Date(m + '-01T00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  const monthShort = m => new Date(m + '-01T00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // ------------------------------------------------------------------ theme
  let T = {};
  function readTheme() {
    const cs = getComputedStyle(root), v = n => cs.getPropertyValue(n).trim();
    T = {
      s: [1, 2, 3, 4, 5].map(i => v('--series-' + i)), muted: v('--series-muted'),
      ink: v('--ink'), ink2: v('--ink-2'), tick: v('--tick'), grid: v('--grid'), base: v('--baseline'),
      surface: v('--surface'), tipBg: v('--tooltip-bg'), tipInk: v('--tooltip-ink'),
      good: v('--good'), critical: v('--critical'), neutral: v('--neutral-dot'),
    };
    const D = Chart.defaults;
    D.font.family = getComputedStyle(document.body).fontFamily;
    D.font.size = 12.5;
    D.color = T.tick;
    D.borderColor = T.grid;
    D.animation.duration = 350;
    D.maintainAspectRatio = false;
    Object.assign(D.plugins.tooltip, {
      backgroundColor: T.tipBg, titleColor: T.tipInk, bodyColor: T.tipInk, padding: 10, cornerRadius: 6,
      displayColors: false, titleFont: { weight: '600' }, caretSize: 5,
    });
    D.plugins.legend.labels = Object.assign({}, D.plugins.legend.labels, {
      color: T.ink2, boxWidth: 10, boxHeight: 10, padding: 14, font: { size: 13 },
    });
  }

  // value printed just past the end of each bar (selective labels: bars only, not lines)
  Chart.register({
    id: 'endLabels',
    afterDatasetsDraw(c) {
      const f = endLabel[c.canvas.id]; if (!f) return;
      const ctx = c.ctx, horiz = c.options.indexAxis === 'y';
      ctx.save();
      ctx.font = '500 12.5px ' + Chart.defaults.font.family;
      ctx.fillStyle = T.ink2;
      c.getDatasetMeta(0).data.forEach((el, i) => {
        const raw = c.data.datasets[0].data[i]; if (raw == null) return;
        const txt = f(raw, i);
        if (horiz) { ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(txt, el.x + 6, el.y); }
        else { ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillText(txt, el.x, el.y - 4); }
      });
      ctx.restore();
    },
  });

  const axis = (extra = {}) => Object.assign({
    grid: { color: T.grid, drawTicks: false, lineWidth: 1 },
    border: { display: false },
    ticks: { color: T.tick, padding: 8 },
  }, extra);
  const catAxis = (extra = {}) => Object.assign({
    grid: { display: false }, border: { display: true, color: T.base }, ticks: { color: T.ink2, padding: 6 },
  }, extra);

  function draw(id, cfg, label) {
    endLabel[id] = label || null;
    const old = charts[id];
    if (old && old.config.type === cfg.type) {
      old.data = cfg.data; old.options = cfg.options; old.update();
    } else {
      if (old) old.destroy();
      charts[id] = new Chart($(id), cfg);
    }
  }

  const hbar = (id, labels, values, colors, fmt, tipFmt, pad = 64) => draw(id, {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: { topRight: 4, bottomRight: 4 },
      borderSkipped: 'start', barPercentage: .72, categoryPercentage: .9, maxBarThickness: 26 }] },
    options: {
      indexAxis: 'y', layout: { padding: { right: pad } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => tipFmt(c.raw, c.dataIndex) } } },
      scales: { x: axis({ beginAtZero: true, ticks: { color: T.tick, padding: 8, callback: v => fmt(v), maxTicksLimit: 5 } }), y: catAxis() },
    },
  }, fmt);

  // ------------------------------------------------------------------ small DOM helpers
  const sub = (id, text) => { const el = $('sub-' + id); if (el) el.textContent = text; };
  function table(id, head, rows, right = []) {
    const th = head.map((h, i) => `<th class="${right.includes(i) ? 'r' : ''}">${esc(h)}</th>`).join('');
    const tr = rows.map(r => '<tr>' + r.map((v, i) => `<td class="${right.includes(i) ? 'r' : ''}">${esc(v)}</td>`).join('') + '</tr>').join('');
    $('tbl-' + id).innerHTML = `<table class="mini"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  }
  function partBar(container, parts, total, unit) {
    const seg = parts.map(p => `<span style="flex:${p.n || 0} 1 0;background:${p.color}" title="${esc(p.label)}: ${num(p.n)}"></span>`).join('');
    const li = parts.map(p => `<li><span class="sw" style="background:${p.color}"></span><span>${esc(p.label)}</span>` +
      `<span class="v">${num(p.n)} ${unit}</span><span class="p">${total ? pct(p.n / total) : '–'}</span></li>`).join('');
    container.innerHTML = `<div class="bars"><div class="seg" role="img" aria-label="${esc(parts.map(p => p.label + ' ' + num(p.n)).join(', '))}">${seg}</div><ul class="legend">${li}</ul></div>`;
  }
  const ICONS = {
    dollar: '<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2c-.5-1-1.6-1.6-2.8-1.6-1.6 0-2.8.9-2.8 2.2 0 3 5.8 1.6 5.8 4.5 0 1.3-1.3 2.2-3 2.2-1.3 0-2.5-.6-3-1.7M12 6v1.6M12 16.5V18"/>',
    cart: '<path d="M3 4h2.5l2.2 11h10.6l2.2-8H7"/><circle cx="9.5" cy="19.5" r="1.3"/><circle cx="17" cy="19.5" r="1.3"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0113 0"/><path d="M16 4.5a3.5 3.5 0 010 7M18 14.5a6.5 6.5 0 013.5 5.5"/>',
    repeat: '<path d="M4 12a8 8 0 0113.7-5.6L20 8.5M20 4v4.5h-4.5M20 12a8 8 0 01-13.7 5.6L4 15.5M4 20v-4.5h4.5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    truck: '<path d="M2.5 6h11v10h-11zM13.5 9.5h4l3 3.5v3h-7"/><circle cx="6.5" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>',
    receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
    undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 010 11H11"/>',
    x: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0115 0"/>',
  };
  const svgI = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n]}</svg>`;
  const icon = d => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
  function delta(cur, prev, label) {
    if (!prev) return label || '';
    const ch = (cur - prev) / prev, up = ch >= 0;
    return `<span class="pill ${up ? 'up' : 'down'}">${icon(up ? 'M7 17L17 7M9 7h8v8' : 'M7 7l10 10M17 9v8H9')}${Math.abs(ch * 100).toFixed(1)}%</span> ${label || ''}`;
  }
  function kpis(list) {
    const box = $('kpis');
    box.innerHTML = list.map(k => `<div class="kpi ${k.hero ? 'hero' : ''}" data-k="${k.key}"><div class="kpi-top"><div class="kpi-label">${esc(k.label)}</div>` +
      (k.icon ? `<span class="icon-chip">${svgI(k.icon)}</span>` : '') + `</div>` +
      `<div class="kpi-value">${k.value}</div><div class="kpi-sub">${k.sub || '&nbsp;'}</div></div>`).join('');
    list.forEach(k => {
      if (prevKpi.flash && prevKpi[k.key] !== undefined && prevKpi[k.key] !== k.value) {
        const el = box.querySelector(`[data-k="${k.key}"]`);
        el.classList.add('changed'); setTimeout(() => el.classList.remove('changed'), 1800);
      }
      prevKpi[k.key] = k.value;
    });
    prevKpi.flash = false;
  }
  // sequential shades of the accent: one hue, light -> dark, for ordered magnitudes
  const rgb = h => { h = h.replace('#', ''); if (h.length === 3) h = [...h].map(c => c + c).join(''); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
  const mix = (a, b, p) => { const A = rgb(a), B = rgb(b); return `rgb(${A.map((v, i) => Math.round(v * p / 100 + B[i] * (1 - p / 100))).join(',')})`; };
  const alpha = (a, o) => `rgba(${rgb(a).join(',')},${o})`;
  const shade = p => mix(T.s[0], T.surface, p);

  // ------------------------------------------------------------------ overview
  let measure = 'rev', range = 0;
  function monthChart(d) {
    const all = d.monthly, M = range ? all.slice(-range) : all;
    const isRev = measure === 'rev', vals = M.map(r => isRev ? r.rev : r.n);
    const best = M.reduce((a, b) => ((isRev ? b.rev : b.n) > (isRev ? a.rev : a.n) ? b : a), M[0]);
    const avg = vals.reduce((s, v) => s + v, 0) / vals.length;
    const f = isRev ? usd : num;
    sub('cMonth', `${isRev ? 'Net revenue' : 'Orders'} per month, averaging ${f(avg)}. Peak: ${monthName(best.m)} (${f(isRev ? best.rev : best.n)}).`);
    const ctx = $('cMonth').getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 280);
    grad.addColorStop(0, alpha(T.s[0], .24));
    grad.addColorStop(1, alpha(T.s[0], 0));
    draw('cMonth', {
      type: 'line',
      data: { labels: M.map(r => monthShort(r.m)), datasets: [{ data: vals, borderColor: T.s[0], borderWidth: 2.5, backgroundColor: grad, fill: 'origin',
        pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: T.surface, pointHoverBackgroundColor: T.s[0], pointHitRadius: 14, tension: .35 }] },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          title: c => monthName(M[c[0].dataIndex].m),
          label: c => [`Net revenue  ${usd(M[c.dataIndex].rev)}`, `Orders  ${num(M[c.dataIndex].n)}`] } } },
        scales: { x: catAxis({ border: { display: false }, ticks: { color: T.tick, padding: 6, maxRotation: 0, autoSkipPadding: 14 } }),
          y: axis({ beginAtZero: true, ticks: { color: T.tick, padding: 8, callback: isRev ? usdK : num, maxTicksLimit: 5 } }) },
      },
    });
  }

  function gauge(d) {
    const M = d.monthly, cur = M[M.length - 1];
    const target = M.reduce((s, r) => s + r.rev, 0) / M.length * 1.1;
    const p = Math.min(cur.rev / target, 1), pct0 = Math.round(cur.rev / target * 100);
    const L = Math.PI * 80;                    // semicircle length for r = 80
    const prev = M[M.length - 2];
    sub('target', `${monthName(cur.m)} vs. target of the monthly average + 10%`);
    $('target').innerHTML = `<div class="gauge"><svg viewBox="0 0 200 112" aria-hidden="true">
        <path class="g-track" d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="18" stroke-linecap="round"/>
        <path class="g-val" d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="18" stroke-linecap="round" stroke-dasharray="${L}" stroke-dashoffset="${L * (1 - p)}"/></svg>
        <div class="gauge-num"><b>${pct0}%</b><span>${prev ? delta(cur.rev, prev.rev, 'vs ' + monthName(prev.m).split(' ')[0]) : ''}</span></div></div>
      <p class="gauge-note">${cur.rev >= target ? `<b>Target met</b> with ${usd(cur.rev - target)} to spare.` : `<b>${usd(target - cur.rev)}</b> short of target this month.`}</p>
      <div class="split"><div><span>Target</span><b>${usd(target)}</b></div><div><span>Revenue</span><b>${usd(cur.rev)}</b></div></div>`;
  }

  function overview(d) {
    const K = d.kpis, M = d.monthly, R = d.retention;
    const lm = M[M.length - 1], pm = M[M.length - 2];
    const vs = pm ? `vs ${monthName(pm.m).split(' ')[0]}` : '';
    kpis([
      { key: 'revenue', label: 'Net revenue', icon: 'dollar', hero: true, value: usd(K.revenue), sub: pm ? delta(lm.rev, pm.rev, `${monthName(lm.m).split(' ')[0]} ${vs}`) : '' },
      { key: 'orders', label: 'Orders', icon: 'cart', value: num(K.orders), sub: pm ? delta(lm.n, pm.n, `${monthName(lm.m).split(' ')[0]} ${vs}`) : '' },
      { key: 'cust', label: 'Customers', icon: 'users', value: num(K.customers), sub: `${pct(R.repeat_rate, 0)} ordered more than once` },
    ]);
    monthChart(d);
    gauge(d);

    // top categories: share of net revenue, darker = bigger
    const C = d.category, catTotal = C.reduce((s, r) => s + r.rev, 0);
    const cc = C.map((_, i) => shade(100 - i * (70 / Math.max(1, C.length - 1))));
    sub('cats', C.length > 1 ? `${C[0].k} alone is ${pct(C[0].rev / catTotal, 0)} of net revenue.` : '');
    $('catTotal').textContent = usdK(catTotal);
    draw('cCat', {
      type: 'doughnut',
      data: { labels: C.map(r => r.k), datasets: [{ data: C.map(r => r.rev), backgroundColor: cc, borderColor: T.surface, borderWidth: 2, hoverOffset: 4 }] },
      options: { cutout: '72%', plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${usd(c.raw)} · ${pct(c.raw / catTotal)}` } } } },
    });
    $('catLegend').innerHTML = C.map((r, i) => `<li><span class="sw" style="background:${cc[i]}"></span><span>${esc(r.k)}</span><span class="v">${usd(r.rev)}</span></li>`).join('');

    // map: countries shaded by net revenue
    const CO = d.country, coMax = Math.max(...CO.map(r => r.rev)), coTot = CO.reduce((s, r) => s + r.rev, 0);
    const byC = Object.fromEntries(CO.map(r => [r.k, r]));
    const mapEl = document.querySelector('.sea-map');
    mapEl.querySelectorAll('.c').forEach(el => {
      const r = byC[el.dataset.country];
      el.style.fill = r ? shade(25 + 75 * r.rev / coMax) : T.grid;
      el.querySelector('title').textContent = r ? `${r.k}: ${usd(r.rev)} net revenue · ${num(r.c)} customers · ${num(r.n)} orders` : `${el.dataset.country}: no orders in this view`;
    });
    $('mapScale').style.background = `linear-gradient(90deg, ${shade(25)}, ${shade(100)})`;
    sub('map', CO.length > 1 ? `${CO[0].k}, ${CO[1].k} and ${CO[2] ? CO[2].k : ''} bring in ${pct((CO[0].rev + CO[1].rev + (CO[2] ? CO[2].rev : 0)) / coTot, 0)} of net revenue.` : `Showing ${CO[0].k} only.`);
    $('countryList').innerHTML = CO.map(r => `<li data-country="${esc(r.k)}" title="${num(r.c)} customers · ${num(r.n)} orders · ${pct(r.rev / coTot, 0)} of net revenue"><div class="row"><span>${esc(r.k)}</span><b>${usd(r.rev)}</b></div>` +
      `<div class="track"><i style="width:${(r.rev / coMax * 100).toFixed(1)}%"></i></div></li>`).join('');

    // fulfilment funnel
    const F = d.funnel;
    sub('funnel', `${pct(F[2].n / F[0].n)} of orders end up delivered and kept.`);
    $('funnel').innerHTML = F.map((s, i) => `<div class="stage"><div class="lbl">${esc(s.k)}</div><div class="val">${num(s.n)}</div>` +
      `<div class="rate">${i ? `<span class="pill ${s.n / F[i - 1].n >= .85 ? 'up' : 'down'}">${pct(s.n / F[i - 1].n, 0)}</span>` : '<span class="pill up">100%</span>'}</div>` +
      `<div class="col"><i style="height:${Math.max(4, s.n / F[0].n * 100).toFixed(1)}%" title="${esc(s.k)}: ${num(s.n)} orders"></i></div></div>`).join('');

    // recent orders
    $('recent').innerHTML = `<table class="mini"><thead><tr><th>Order</th><th>Date</th><th>Customer</th><th>Category</th><th class="r">Total</th><th>Status</th></tr></thead><tbody>` +
      d.recent_orders.map(r => `<tr><td><a href="${CFG.ordersUrl}?q=${encodeURIComponent(r.order_id)}">${esc(r.order_id)}</a></td><td class="num">${esc(r.order_date)}</td>` +
        `<td>${esc(r.customer_id)}</td><td>${esc(r.product_category)}</td><td class="r">${usd2(r.total_amount)}</td>` +
        `<td><span class="status-pill ${r.order_status}">${r.order_status}</span></td></tr>`).join('') + '</tbody></table>';

    // acquisition channels: customers per channel, colour fixed per channel
    const CH = d.channel, chTot = CH.reduce((s, r) => s + r.c, 0);
    const chColor = k => T.s[CFG.channels.indexOf(k)] || T.muted;
    const chs = CFG.channels.map(k => CH.find(r => r.k === k)).filter(Boolean);
    const topCh = [...CH].sort((a, b) => b.c - a.c)[0];
    sub('chan', `${topCh.k} brought in the most customers.`);
    $('chan').innerHTML = `<div class="stackbar" role="img" aria-label="Customers by channel">${chs.map(r => `<span style="flex:${r.c} 1 0;background:${chColor(r.k)}" title="${esc(r.k)}: ${num(r.c)}"></span>`).join('')}</div>` +
      `<ul class="legend rows">${chs.map(r => `<li><span class="sw" style="background:${chColor(r.k)}"></span><span>${esc(r.k)}</span><span class="v">${pct(r.c / chTot, 0)}</span></li>`).join('')}</ul>`;

    // activity feed
    const kindIcon = { delivered: 'receipt', returned: 'undo', cancelled: 'x', signup: 'user' };
    const fmtDate = s => new Date(s + 'T00:00').toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });
    $('activity').innerHTML = d.activity.map(e => `<li><span class="icon-chip ${e.kind}">${svgI(kindIcon[e.kind])}</span>` +
      `<div><b>${esc(e.who)}</b> ${esc(e.text)}<time datetime="${e.date}">${fmtDate(e.date)}</time></div></li>`).join('');
  }

  function histogram(d) {
    const H = d.histogram;
    const under100 = H.counts.slice(0, 4).reduce((a, b) => a + b, 0);
    sub('cHist', `${pct(under100 / d.n, 0)} of orders are under $100; a long tail runs past $1,000.`);
    draw('cHist', {
      type: 'bar',
      data: { labels: H.labels, datasets: [{ data: H.counts, backgroundColor: T.s[0], borderRadius: { topLeft: 4, topRight: 4 },
        borderSkipped: 'start', barPercentage: .94, categoryPercentage: .96 }] },
      options: {
        layout: { padding: { top: 18 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${num(c.raw)} orders (${pct(c.raw / d.n)})` } } },
        scales: { x: catAxis({ ticks: { color: T.tick, padding: 6, maxRotation: 0, autoSkip: false, font: { size: 12 } } }),
          y: axis({ beginAtZero: true, ticks: { color: T.tick, padding: 8, maxTicksLimit: 5 } }) },
      },
    }, v => v ? num(v) : '');
    table('cHist', ['Order value', 'Orders', 'Share'], H.labels.map((l, i) => [l, num(H.counts[i]), pct(H.counts[i] / d.n)]), [1, 2]);
  }

  // ------------------------------------------------------------------ customers & service
  function customers(d) {
    const R = d.retention, cor = d.correlation;
    kpis([
      { key: 'cust', label: 'Customers', icon: 'users', hero: true, value: num(R.customers), sub: `${usd(d.rev_per_customer)} net revenue each` },
      { key: 'repeat', label: 'Repeat customers', icon: 'repeat', value: pct(R.repeat_rate), sub: 'Placed more than one order' },
      { key: 'dormant', label: 'Dormant customers', icon: 'clock', value: pct(R.dormant_share), sub: 'No order in the last 180 days' },
      { key: 'corr', label: 'Delivery time vs rating', icon: 'truck', value: (cor.r < 0 ? '−' : '') + Math.abs(cor.r).toFixed(2), sub: `Correlation across ${num(cor.n)} reviews` },
    ]);

    // segments: a comparison table reads better than four separate charts
    const SG = d.segments, maxRpc = Math.max(...SG.map(s => s.rev_per_customer));
    const nw = SG.find(s => s.k === 'New'), vip = SG.find(s => s.k === 'VIP');
    sub('segments', nw && vip ? `A VIP customer is worth ${(vip.rev_per_customer / nw.rev_per_customer).toFixed(1)}× a new one. Top 20% of customers bring ${pct(R.top20_share, 0)} of revenue.`
      : `Top 20% of customers bring ${pct(R.top20_share, 0)} of revenue.`);
    $('segments').innerHTML = `<table class="mini"><thead><tr><th>Segment</th><th class="r">Customers</th><th class="r">Orders each</th>` +
      `<th class="r">Avg order</th><th class="r" style="width:38%">Revenue per customer</th></tr></thead><tbody>` +
      SG.map(s => `<tr><td>${esc(s.k)}</td><td class="r">${num(s.customers)}</td><td class="r">${s.orders_per_customer.toFixed(2)}</td>` +
        `<td class="r">${usd2(s.aov)}</td><td class="r"><div class="databar"><i style="width:${(s.rev_per_customer / maxRpc * 100).toFixed(1)}%"></i>${usd(s.rev_per_customer)}</div></td></tr>`).join('') +
      '</tbody></table>';

    // recency bands are ordered, so one hue from light to dark rather than three unrelated colours
    const ch = d.churn, tot = ch.high + ch.medium + ch.low;
    sub('recency', `${pct(ch.high / tot, 0)} haven't ordered in more than 180 days, measured to ${new Date(ch.snapshot + 'T00:00').toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })}.`);
    partBar($('recency'), [
      { label: 'Within 90 days', n: ch.low, color: shade(100) },
      { label: '91–180 days', n: ch.medium, color: shade(60) },
      { label: 'Over 180 days', n: ch.high, color: shade(40) },
    ], tot, 'customers');

    histogram(d);
    const CO = d.country, coTot = CO.reduce((s, r) => s + r.rev, 0);
    sub('cCountry', CO.length > 1 ? `${CO[0].k} leads with ${pct(CO[0].rev / coTot, 0)} of net revenue.` : `${CO[0].k} only.`);
    hbar('cCountry', CO.map(r => r.k), CO.map(r => r.rev), T.s[0], usdK, (v, i) => `${usd(v)} · ${num(CO[i].c)} customers`);
    table('cCountry', ['Country', 'Customers', 'Net revenue', 'Share'], CO.map(r => [r.k, num(r.c), usd2(r.rev), pct(r.rev / coTot)]), [1, 2, 3]);

    // channels: highlight the best, grey the rest
    const CH = d.channel;
    sub('cChan', CH.length > 1 ? `${CH[0].k} customers spend the most (${usd(CH[0].rpc)}); ${CH[CH.length - 1].k} the least (${usd(CH[CH.length - 1].rpc)}).` : '');
    hbar('cChan', CH.map(r => r.k), CH.map(r => r.rpc), CH.map((_, i) => i === 0 ? T.s[0] : T.muted), usd, v => `${usd2(v)} per customer`);
    table('cChan', ['Channel', 'Revenue per customer'], CH.map(r => [r.k, usd2(r.rpc)]), [1]);

    // payment mix: 100% stacked, colour fixed per method (never by rank)
    const PA = d.payment_by_age, ages = Object.keys(PA), methods = CFG.payments;
    const lead = ages.map(a => methods.reduce((b, m) => ((PA[a][m] || 0) > (PA[a][b] || 0) ? m : b), methods[0]));
    sub('cPay', ages.length ? `${lead[0]} leads among ${ages[0]}s; ${lead[lead.length - 1]} among ${ages[ages.length - 1]}.` : '');
    draw('cPay', {
      type: 'bar',
      data: { labels: ages, datasets: methods.map((m, i) => ({ label: m, data: ages.map(a => (PA[a][m] || 0) * 100),
        backgroundColor: T.s[i], borderColor: T.surface, borderWidth: { right: 2 }, borderSkipped: false, barPercentage: .7, maxBarThickness: 26 })) },
      options: {
        indexAxis: 'y',
        plugins: { legend: { position: 'top', align: 'start' },
          tooltip: { displayColors: true, callbacks: { label: c => ` ${c.dataset.label}  ${c.raw.toFixed(1)}%` } } },
        scales: { x: axis({ stacked: true, max: 100, ticks: { color: T.tick, padding: 8, callback: v => v + '%', stepSize: 25 } }),
          y: catAxis({ stacked: true }) },
      },
    });
    table('cPay', ['Age group', ...methods], ages.map(a => [a, ...methods.map(m => pct(PA[a][m] || 0))]), methods.map((_, i) => i + 1));

    const B = d.delivery_bands, rated = B.filter(b => b.rating != null);
    sub('cDeliv', rated.length > 1 ? `Average rating falls from ${rated[0].rating.toFixed(1)} (${rated[0].band}) to ${rated[rated.length - 1].rating.toFixed(1)} (${rated[rated.length - 1].band}).` : '');
    draw('cDeliv', {
      type: 'bar',
      data: { labels: B.map(b => b.band), datasets: [{ data: B.map(b => b.rating), backgroundColor: T.s[0],
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'start', barPercentage: .6, maxBarThickness: 56 }] },
      options: {
        layout: { padding: { top: 20 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.raw == null ? '–' : c.raw.toFixed(2)} stars · ${num(B[c.dataIndex].n)} reviews` } } },
        scales: { x: catAxis({ title: { display: true, text: 'Delivery time', color: T.tick } }),
          y: axis({ min: 0, max: 5, ticks: { color: T.tick, padding: 8, stepSize: 1 }, title: { display: true, text: 'Average rating (1–5)', color: T.tick } }) },
      },
    }, v => v.toFixed(2));
    table('cDeliv', ['Delivery time', 'Reviews', 'Average rating'], B.map(b => [b.band, num(b.n), b.rating == null ? '–' : b.rating.toFixed(2)]), [1, 2]);

    // one bubble per (days, rating) pair, area ~ number of reviews; least-squares line on top
    const P = d.scatter, maxC = Math.max(1, ...P.map(p => p.c));
    const xs = P.map(p => p.x), x0 = Math.min(...xs), x1 = Math.max(...xs);
    sub('cScatter', `r = ${cor.r.toFixed(2)}: each extra day of delivery costs about ${Math.abs(cor.slope).toFixed(2)} stars on average.`);
    draw('cScatter', {
      type: 'bubble',
      data: { datasets: [
        { label: 'Reviews', data: P.map(p => ({ x: p.x, y: p.y, r: 2.5 + 9 * Math.sqrt(p.c / maxC), c: p.c })),
          backgroundColor: alpha(T.s[0], .45), borderColor: T.surface, borderWidth: 1 },
        { type: 'line', label: 'Trend', data: [{ x: x0, y: cor.intercept + cor.slope * x0 }, { x: x1, y: cor.intercept + cor.slope * x1 }],
          borderColor: T.ink, backgroundColor: T.ink, borderWidth: 2, pointRadius: 0, pointHitRadius: 0 },
      ] },
      options: {
        plugins: { legend: { position: 'top', align: 'start' },
          tooltip: { filter: c => c.datasetIndex === 0, callbacks: { label: c => `${c.raw.x} days, ${c.raw.y} stars · ${num(c.raw.c)} reviews` } } },
        scales: { x: axis({ type: 'linear', title: { display: true, text: 'Delivery time (days)', color: T.tick } }),
          y: axis({ min: 0.5, max: 5.5, afterBuildTicks: ax => { ax.ticks = [1, 2, 3, 4, 5].map(value => ({ value })); }, ticks: { color: T.tick, padding: 8 }, title: { display: true, text: 'Rating', color: T.tick } }) },
      },
    });
    table('cScatter', ['Delivery days', 'Rating', 'Reviews'], [...P].sort((a, b) => a.x - b.x || a.y - b.y).map(p => [p.x, p.y, num(p.c)]), [0, 1, 2]);

    const RC = d.returns_by_category;
    sub('cRet', RC.length > 1 ? `${RC[0].k} has the highest return rate at ${pct(RC[0].rate)}, against ${pct(d.kpis.return_rate)} overall.` : '');
    hbar('cRet', RC.map(r => r.k), RC.map(r => r.rate), RC.map((_, i) => i === 0 ? T.s[0] : T.muted), v => pct(v, v < .1 && v > 0 ? 1 : 0), v => pct(v) + ' returned', 52);
    endLabel.cRet = v => pct(v);
    table('cRet', ['Category', 'Return rate'], RC.map(r => [r.k, pct(r.rate)]), [1]);

    const RS = d.rating_by_status, dl = RS[0], rt = RS[1];
    sub('reviews', dl.rating != null && rt.rating != null ? `Returned orders average ${rt.rating.toFixed(1)} stars, against ${dl.rating.toFixed(1)} for delivered.` : '');
    $('reviews').innerHTML = `<table class="mini"><thead><tr><th>Order status</th><th class="r">Reviews</th><th class="r">Average rating</th><th class="r">Rated 1–2 stars</th></tr></thead><tbody>` +
      RS.map(r => `<tr><td><span class="status ${r.s}">${r.s}</span></td><td class="r">${num(r.n)}</td>` +
        `<td class="r">${r.rating == null ? '–' : r.rating.toFixed(2)}</td><td class="r">${r.low == null ? '–' : pct(r.low)}</td></tr>`).join('') +
      '</tbody></table>';
  }

  // ------------------------------------------------------------------ loading
  function params() {
    const p = new URLSearchParams();
    for (const [k, el] of Object.entries(sel)) if (el.value) p.set(k, el.value);
    return p;
  }
  function syncControls() {
    let any = false;
    for (const el of Object.values(sel)) { el.classList.toggle('is-set', !!el.value); any = any || !!el.value; }
    $('clear').disabled = !any;
    const q = params().toString();
    history.replaceState(null, '', location.pathname + (q ? '?' + q : ''));
  }
  function render(d) {
    $('scopeText').textContent = d.n === d.total_orders ? `${num(d.n)} orders` : `${num(d.n)} of ${num(d.total_orders)} orders`;
    const empty = d.n === 0;
    $('empty').hidden = !empty; $('cards').hidden = empty; $('kpis').hidden = empty;
    if (empty) return;
    (CFG.view === 'overview' ? overview : customers)(d);
  }
  async function load(flash = false) {
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    const mine = ctrl;
    $('live').classList.add('loading');
    try {
      const r = await fetch(CFG.api + '?' + params(), { signal: mine.signal, cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      last = await r.json();
      prevKpi.flash = flash;
      render(last);
    } catch (e) {
      if (e.name !== 'AbortError') { $('scopeText').textContent = 'Could not load data. Retrying when the server responds.'; console.error(e); }
    } finally {
      if (ctrl === mine) $('live').classList.remove('loading');
    }
  }

  // ------------------------------------------------------------------ wiring
  const url = new URLSearchParams(location.search);
  for (const [k, el] of Object.entries(sel)) {
    const v = url.get(k);
    if (v && [...el.options].some(o => o.value === v)) el.value = v;
    el.addEventListener('change', () => { syncControls(); load(); });
  }
  const clear = () => { Object.values(sel).forEach(el => { el.value = ''; }); syncControls(); load(); };
  $('clear').addEventListener('click', clear);
  $('clear2').addEventListener('click', clear);

  document.querySelectorAll('.view-toggle').forEach(g => g.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    g.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    g.closest('.card').classList.toggle('show-table', b.dataset.view === 'table');
  }));

  document.addEventListener('ca:data-changed', () => load(true));
  document.addEventListener('ca:theme', () => {
    readTheme();
    Object.values(charts).forEach(c => c.destroy());
    for (const k in charts) delete charts[k];
    if (last) render(last);
  });

  // overview-only controls
  const segCtl = (id, fn) => { const g = $(id); if (!g) return;
    g.addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return;
      g.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); fn(b); if (last && last.n) monthChart(last); }); };
  segCtl('measure', b => { measure = b.dataset.m; });
  segCtl('range', b => { range = +b.dataset.r; });

  // map <-> list hover linking
  const mapEl = document.querySelector('.sea-map'), list = $('countryList');
  if (mapEl && list) {
    const hot = k => {
      mapEl.classList.toggle('has-hover', !!k);
      mapEl.querySelectorAll('.c').forEach(el => el.classList.toggle('hot', el.dataset.country === k));
      list.querySelectorAll('li').forEach(li => li.classList.toggle('hot', li.dataset.country === k));
    };
    mapEl.addEventListener('mouseover', e => { const c = e.target.closest('.c'); hot(c ? c.dataset.country : null); });
    mapEl.addEventListener('mouseleave', () => hot(null));
    list.addEventListener('mouseover', e => { const li = e.target.closest('li'); hot(li ? li.dataset.country : null); });
    list.addEventListener('mouseleave', () => hot(null));
  }

  syncControls();
  // wait for the web font so canvas text is drawn in Inter, not the fallback
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => { readTheme(); load(); });
})();
