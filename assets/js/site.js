/* nksaunders.space — theme toggle and System Spotlight. No dependencies. */
(function () {
  'use strict';
  var root = document.documentElement;

  /* ---------- Day / night ---------- */
  var toggle = document.getElementById('theme-toggle');
  function syncToggle() {
    if (!toggle) return;
    toggle.setAttribute('aria-label', root.dataset.theme === 'night' ? 'Switch to day mode' : 'Switch to night mode');
  }
  syncToggle();
  if (toggle) toggle.addEventListener('click', function () {
    root.dataset.theme = root.dataset.theme === 'night' ? 'day' : 'night';
    try { localStorage.setItem('theme', root.dataset.theme); } catch (e) {}
    syncToggle();
  });

  /* ---------- System Spotlight ---------- */
  var panel = document.querySelector('.spotlight');
  if (!panel) return;
  var SVGNS = 'http://www.w3.org/2000/svg';
  var el = function (id) { return document.getElementById(id); };
  var plot = el('sp-plot'), caption = el('sp-caption');
  var tabs = panel.querySelectorAll('.sp-tab');
  var systems = [], idx = 0, tab = 'transit';

  // Plot box in SVG user units (viewBox 360 x 210).
  var X0 = 44, X1 = 352, Y0 = 10, Y1 = 176;

  function svg(tag, attrs, parent) {
    var n = document.createElementNS(SVGNS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function extent(arrs, pad) {
    var lo = Infinity, hi = -Infinity;
    arrs.forEach(function (a) { (a || []).forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; }); });
    var d = (hi - lo) || 1;
    return [lo - d * pad, hi + d * pad];
  }
  function fmt(v) { return Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1); }

  var SHAPES = ['circle', 'square', 'triangle', 'diamond'];
  function marker(shape, cx, cy, r) {
    var f = function (v) { return v.toFixed(1); };
    if (shape === 'square') { var q = r * 0.9; return 'M' + f(cx - q) + ' ' + f(cy - q) + 'h' + f(2 * q) + 'v' + f(2 * q) + 'h' + f(-2 * q) + 'z'; }
    if (shape === 'triangle') { var h = r * 1.25; return 'M' + f(cx) + ' ' + f(cy - h) + 'L' + f(cx + h) + ' ' + f(cy + h * 0.8) + 'L' + f(cx - h) + ' ' + f(cy + h * 0.8) + 'z'; }
    if (shape === 'diamond') { var g = r * 1.3; return 'M' + f(cx) + ' ' + f(cy - g) + 'L' + f(cx + g) + ' ' + f(cy) + 'L' + f(cx) + ' ' + f(cy + g) + 'L' + f(cx - g) + ' ' + f(cy) + 'z'; }
    return 'M' + f(cx - r) + ' ' + f(cy) + 'a' + r + ' ' + r + ' 0 1 0 ' + 2 * r + ' 0a' + r + ' ' + r + ' 0 1 0 ' + -2 * r + ' 0';
  }

  function drawChart(d, ylab, label) {
    plot.textContent = '';
    var s = svg('svg', { viewBox: '0 0 360 210', role: 'img', 'aria-label': label }, plot);
    var xr = extent([d.x, d.model_x], 0.02);
    var yr = extent([d.y, d.model_y], 0.12);
    var sx = function (v) { return X0 + (v - xr[0]) / (xr[1] - xr[0]) * (X1 - X0); };
    var sy = function (v) { return Y1 - (v - yr[0]) / (yr[1] - yr[0]) * (Y1 - Y0); };

    svg('path', { class: 'axis', d: 'M' + X0 + ' ' + Y0 + 'V' + Y1 + 'H' + X1 }, s);
    if (d.ref != null && d.ref > yr[0] && d.ref < yr[1]) svg('line', { class: 'ref', x1: X0, x2: X1, y1: sy(d.ref), y2: sy(d.ref) }, s);

    if (d.yerr) {
      var e = '';
      d.x.forEach(function (x, i) { e += 'M' + sx(x).toFixed(1) + ' ' + sy(d.y[i] - d.yerr[i]).toFixed(1) + 'V' + sy(d.y[i] + d.yerr[i]).toFixed(1); });
      svg('path', { class: 'err', d: e }, s);
    }
    var r = d.inst ? 2.3 : 1.9, p = '';
    d.x.forEach(function (x, i) {
      var cx = sx(x), cy = Math.max(Y0, Math.min(Y1, sy(d.y[i])));
      p += marker(SHAPES[(d.inst ? d.inst[i] : 0) % SHAPES.length], cx, cy, r);
    });
    svg('path', { class: 'pts', d: p }, s);
    if (d.model_x && d.model_x.length) {
      var m = d.model_x.map(function (x, i) { return (i ? 'L' : 'M') + sx(x).toFixed(1) + ' ' + sy(d.model_y[i]).toFixed(1); }).join('');
      svg('path', { class: 'model', d: m }, s);
    }
    // Ticks: ends and zero of the x axis.
    var ticks = d.phase ? [[-0.5, 'start'], [0, 'middle'], [0.5, 'end']]
      : [[xr[0] + (xr[1] - xr[0]) * 0.02, 'start'], [0, 'middle'], [xr[1] - (xr[1] - xr[0]) * 0.02, 'end']];
    ticks.forEach(function (t) {
      if (t[0] < xr[0] || t[0] > xr[1]) return;
      svg('text', { x: sx(t[0]), y: 192, 'text-anchor': t[1] }, s).textContent = t[0] === 0 ? '0' : (d.phase ? String(t[0]) : fmt(t[0]));
    });
    svg('text', { x: (X0 + X1) / 2, y: 206, 'text-anchor': 'middle' }, s).textContent = d.xlab || 'hours from mid-transit';
    var yl = svg('text', { x: 12, y: (Y0 + Y1) / 2, 'text-anchor': 'middle', transform: 'rotate(-90 12 ' + (Y0 + Y1) / 2 + ')' }, s);
    yl.textContent = ylab;
  }

  function starDiagram(lam, b) {
    var a = (lam || 0) * Math.PI / 180, bb = b || 0;
    var rot = function (x, y) { return [x * Math.cos(a) - y * Math.sin(a), -(x * Math.sin(a) + y * Math.cos(a))]; };
    var p1 = rot(-1.35, bb), p2 = rot(1.35, bb), pc = rot(0.25, bb);
    var s = svg('svg', { viewBox: '-1.5 -1.5 3 3', width: 64, height: 64, 'aria-hidden': 'true' });
    var defs = svg('defs', {}, s);
    var g = svg('linearGradient', { id: 'sp-spin', x1: 0, x2: 1, y1: 0, y2: 0 }, defs);
    svg('stop', { offset: 0, 'stop-color': '#4C7BD9' }, g);
    svg('stop', { offset: .5, 'stop-color': 'var(--panel)', style: 'stop-color: var(--panel)' }, g);
    svg('stop', { offset: 1, 'stop-color': '#D9604C' }, g);
    svg('circle', { cx: 0, cy: 0, r: 1, fill: 'url(#sp-spin)', stroke: 'var(--rule)', style: 'stroke: var(--rule)', 'stroke-width': .04 }, s);
    svg('line', { x1: 0, y1: -1.35, x2: 0, y2: 1.35, style: 'stroke: var(--muted)', 'stroke-width': .03, 'stroke-dasharray': '.08 .08' }, s);
    svg('line', { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1], style: 'stroke: var(--ink)', 'stroke-width': .04 }, s);
    svg('circle', { cx: pc[0], cy: pc[1], r: .13, style: 'fill: var(--ink)' }, s);
    return s;
  }

  function render() {
    var sys = systems[idx];
    el('sp-name').textContent = sys.name;
    el('sp-desc').textContent = sys.description || '';
    var paper = el('sp-paper');
    paper.textContent = sys.paper && sys.paper.label ? sys.paper.label + ' →' : '';
    if (sys.paper && sys.paper.url) paper.href = sys.paper.url;
    el('sp-count').textContent = systems.length > 1 ? (idx + 1) + ' of ' + systems.length : '';
    el('sp-note').hidden = !sys.example;
    tabs.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.tab === tab)); });
    caption.textContent = '';

    if (tab === 'transit') {
      var t = sys.transit;
      drawChart({ x: t.x, y: t.y, yerr: t.yerr, model_x: t.model_x, model_y: t.model_y, ref: 1 }, 'relative flux', 'Transit light curve of ' + sys.name);
      caption.textContent = t.caption || 'Binned TESS photometry (points) with the best-fit transit model.';
    } else if (tab === 'rv') {
      if (sys.rv) {
        var v = sys.rv;
        drawChart({ x: v.x, y: v.y, yerr: v.yerr, inst: v.inst, model_x: v.model_x, model_y: v.model_y, ref: 0, phase: true, xlab: 'orbital phase (transit at 0)' },
          'RV (m/s)', 'Radial velocity orbit of ' + sys.name);
        var leg = document.createElement('div');
        leg.className = 'sp-legend';
        var glyph = ['●', '■', '▲', '◆'];
        leg.textContent = v.labels.map(function (l, i) { return glyph[i % 4] + ' ' + l; }).join('   ') + '  ·  K = ' + v.K + ' m/s';
        caption.appendChild(leg);
      } else {
        plot.innerHTML = '<p class="sp-empty">No radial velocities here yet.</p>';
      }
    } else if (sys.rm) {
      var r = sys.rm;
      drawChart({ x: r.x || [], y: r.y || [], yerr: r.yerr, model_x: r.model_x, model_y: r.model_y, ref: 0 }, 'RV anomaly (m/s)', 'Rossiter–McLaughlin curve of ' + sys.name);
      caption.appendChild(starDiagram(r.lambda_deg, r.b));
      var txt = document.createElement('div');
      txt.className = 'sp-lambda';
      txt.textContent = r.lambda_deg != null ? ('λ = ' + String(r.lambda_deg).replace('-', '−') + '°' + (r.lambda_err != null ? ' ± ' + r.lambda_err + '°' : '')) : '';
      caption.appendChild(txt);
    } else {
      plot.innerHTML = '<p class="sp-empty">No obliquity measurement yet. On the list.</p>';
    }
  }

  function pickStart(n) {
    // A different system than the last visit, when there is more than one.
    var last = -1;
    try { last = parseInt(sessionStorage.getItem('spotlight') || '-1', 10); } catch (e) {}
    var i = Math.floor(Math.random() * n);
    if (n > 1 && i === last) i = (i + 1) % n;
    return i;
  }
  function remember() { try { sessionStorage.setItem('spotlight', String(idx)); } catch (e) {} }

  tabs.forEach(function (b) {
    b.addEventListener('click', function () { tab = b.dataset.tab; render(); });
  });
  el('sp-shuffle').addEventListener('click', function () {
    if (!systems.length) return;
    idx = (idx + 1) % systems.length; remember(); render();
  });

  fetch(panel.dataset.src).then(function (r) { return r.json(); }).then(function (data) {
    systems = (data.systems || []).filter(function (s) { return s.transit && s.transit.x && s.transit.x.length; });
    if (!systems.length) throw new Error('no systems');
    idx = pickStart(systems.length); remember(); render();
  }).catch(function () {
    el('sp-name').textContent = 'System Spotlight';
    plot.innerHTML = '<p class="sp-empty">Spotlight data unavailable right now.</p>';
  });
})();
