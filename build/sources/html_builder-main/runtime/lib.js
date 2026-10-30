/* ============================================================
   H — helper library available to every slide script.
   Keep the API small, stable and documented in skill/HP_DECK_SKILL.md.
   ============================================================ */
(function(){
"use strict";
const $  = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const reduced = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

const fmt = {
  money(n, d){ d = d || 0; return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d}); },
  num(n, d){ d = d || 0; return Number(n).toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d}); },
  pct(n, d){ return fmt.num(n, d || 0) + '%'; },
  compact(n){ const a = Math.abs(n);
    if (a >= 1e9) return (n/1e9).toFixed(a >= 1e10 ? 0 : 1).replace(/\.0$/, '') + 'B';
    if (a >= 1e6) return (n/1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (a >= 1e3) return (n/1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'K';
    return String(Math.round(n)); },
  moneyCompact(n){ return (n < 0 ? '-$' : '$') + fmt.compact(Math.abs(n)); }
};

/* animate(ms, fn(k 0..1 eased), done) -> cancel() */
function animate(ms, fn, done){
  if (reduced() || (window.DECK && window.DECK.instant)) { fn(1); done && done(); return () => {}; }
  let raf, t0 = performance.now(), stop = false;
  (function step(now){
    if (stop) return;
    const k = clamp((now - t0) / ms, 0, 1), e = 1 - Math.pow(1 - k, 3);
    fn(e);
    if (k < 1) raf = requestAnimationFrame(step); else done && done();
  })(t0);
  return () => { stop = true; cancelAnimationFrame(raf); };
}

/* countTo(node, to, ms, format) — counts from the node's last value */
function countTo(node, to, ms, format){
  format = format || (x => fmt.num(x));
  const from = node._cv || 0;
  if (node._cancel) node._cancel();
  if (from === to) { node.textContent = format(to); return; }
  node._cancel = animate(ms || 700, e => { node.textContent = format(from + (to - from) * e); }, () => { node._cv = to; });
  node._cv = to;
}
function resetCount(node, format){ if (node._cancel) node._cancel(); node._cv = 0; node.textContent = (format || (x => fmt.num(x)))(0); }

/* reveal(root, selector, step, offset) — first (step - offset) matches get .in */
function reveal(root, selector, step, offset){
  offset = offset || 0;
  $$(selector, root).forEach((n, k) => n.classList.toggle('in', k < step - offset));
}

/* shared reactive state across slides */
const state = (function(){
  const data = {}, subs = [];
  return {
    get(k, d){ return k in data ? data[k] : d; },
    set(k, v){ data[k] = v; subs.forEach(f => { try { f(k, v); } catch(e){ console.error(e); } }); },
    init(k, v){ if (!(k in data)) data[k] = v; return data[k]; },
    on(f){ subs.push(f); }
  };
})();

function icon(name){ const A = window.DECK_ASSETS || {}; return (A.icons && A.icons[name]) || ''; }
function asset(key){ return window.DECK && window.DECK.assetUrl ? window.DECK.assetUrl(key) : ''; }

/* wire a range/number input to a formatter + callback */
function bindInput(input, out, format, onChange){
  const sync = () => { const v = +input.value; if (out) out.textContent = format ? format(v) : v; onChange && onChange(v); };
  input.addEventListener('input', sync); sync(); return sync;
}

/* segmented buttons: container of .btn[data-v]; returns set(v) */
function segmented(container, onChange, initial){
  const btns = $$('[data-v]', container);
  const set = v => { btns.forEach(b => { const on = b.dataset.v == v; b.classList.toggle('sel', on); b.setAttribute('aria-pressed', on); }); onChange && onChange(v); };
  btns.forEach(b => b.addEventListener('click', () => set(b.dataset.v)));
  if (initial != null) set(initial);
  return set;
}

/* spotlight: click a child to focus it, click again to clear */
function spotlight(container, childSel){
  childSel = childSel || ':scope > *';
  container.classList.add('spot');
  const kids = $$(childSel, container);
  kids.forEach(k => k.addEventListener('click', () => {
    const was = k.classList.contains('open');
    kids.forEach(x => x.classList.remove('open'));
    k.classList.toggle('open', !was);
    container.classList.toggle('spotting', !was);
  }));
  return () => { kids.forEach(x => x.classList.remove('open')); container.classList.remove('spotting'); };
}

/* accordion: .acc > item > button.head + .body — one open at a time. -> set(i), -1 closes all */
function accordion(container, initial){
  const items = $$(':scope > *', container);
  const set = i => items.forEach((it, k) => {
    const on = k === i, h = $('.head', it);
    it.classList.toggle('open', on);
    if (h) h.setAttribute('aria-expanded', on);
  });
  items.forEach((it, i) => { const h = $('.head', it); if (h) h.addEventListener('click', () => set(it.classList.contains('open') ? -1 : i)); });
  set(initial == null ? 0 : initial);
  return set;
}

/* hotspots: numbered .hotspot buttons over an image — one note open at a time. -> {open(i), clear()} */
function hotspots(container, onOpen){
  const pts = $$('.hotspot', container);
  const open = i => { pts.forEach((p, k) => { const on = k === i; p.classList.toggle('open', on); p.setAttribute('aria-expanded', on); }); onOpen && onOpen(i); };
  pts.forEach((p, i) => { p.setAttribute('aria-expanded', 'false'); p.addEventListener('click', () => open(p.classList.contains('open') ? -1 : i)); });
  return { open, clear(){ open(-1); } };
}

/* tabs: buttons [data-tab=x] show [data-panel=x] */
function tabs(root, initial){
  const btns = $$('[data-tab]', root), panels = $$('[data-panel]', root);
  const set = t => { btns.forEach(b => b.classList.toggle('sel', b.dataset.tab === t)); panels.forEach(p => p.classList.toggle('on', p.dataset.panel === t)); };
  btns.forEach(b => b.addEventListener('click', () => set(b.dataset.tab)));
  set(initial || (btns[0] && btns[0].dataset.tab));
  return set;
}

/* ---------- SVG charts (animated by show(n) / set(values)) ---------- */
const NS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const k in (attrs || {})) n.setAttribute(k, attrs[k]); return n; };
const SER = i => 's' + ((i % 4) + 1);                     // series class: .s1 .s2 .s3 .s4
const flat = rows => [].concat.apply([], rows);
const series = o => o.series || [{values:o.values, cls:o.cls}];

/* What a chart was built from, kept on its container for QA (backend/app/qa/charts.py): the data on screen is
   checked against the source PowerPoint's chart like any other figure. `live` marks a chart the audience changed
   through set() — a calculator's output, which is not the source's data and is not held to it. */
function record(container, type, labels, ser, o){
  try {
    container.setAttribute('data-chart', type);
    container.__chart = {type, labels:(labels || []).map(String),
      series:ser.map(x => ({name:String(x.name || ''), values:(x.values || []).map(Number)})),
      max:o && o.max != null ? +o.max : null, min:o && o.min != null ? +o.min : null, live:false};
  } catch(e){}
}
function recordLive(container, values){
  const c = container.__chart;
  if (c) { c.live = true; if (values && c.series[0]) c.series[0].values = values.map(Number); }
}

/* Chart frame + baseline. `o.grid` (true, or a tick count) reserves room on the left and draws
   horizontal gridlines from lo to hi, labelled with o.ylabel (set o.ylabels:false for bare lines). */
function frame(container, o, pad, hi, lo){
  const W = container.clientWidth || 800, Hh = container.clientHeight || 400;
  if (o.grid) pad = Object.assign({}, pad, {l:o.ylabels === false ? 14 : 52});
  const s = svg('svg', {class:'chart', viewBox:`0 0 ${W} ${Hh}`, preserveAspectRatio:'none'});
  const iw = W - pad.l - pad.r, ih = Hh - pad.t - pad.b;
  if (o.grid) {
    const n = o.grid === true ? 4 : +o.grid, f = o.ylabel || (v => fmt.compact(v));
    lo = lo || 0;
    for (let k = 0; k <= n; k++) {
      const y = pad.t + ih - ih * k / n;
      s.appendChild(svg('line', {class:'grid', x1:pad.l, x2:W - pad.r, y1:y, y2:y}));
      if (o.ylabels !== false) { const t = svg('text', {x:pad.l - 10, y:y + 4, 'text-anchor':'end'}); t.textContent = f(lo + (hi - lo) * k / n); s.appendChild(t); }
    }
  }
  s.appendChild(svg('line', {class:'axis', x1:pad.l, x2:W - pad.r, y1:pad.t + ih, y2:pad.t + ih}));
  return {s, W, Hh, pad, iw, ih};
}

/* bars(container, {labels, values, format, max, grid, highlight:[idx], classes:[...]}) -> {show(n), set(values)} */
function bars(container, o){
  const n = o.labels.length;
  let vals = o.values.slice(), max = o.max || Math.max.apply(null, vals) * 1.1 || 1;
  const F = frame(container, o, {l:10, r:10, t:34, b:40}, max);
  const s = F.s, W = F.W, Hh = F.Hh, pad = F.pad, iw = F.iw, ih = F.ih, bw = iw / n * 0.62, gap = iw / n;
  const f = o.format || (v => fmt.num(v));
  record(container, 'bars', o.labels, [{name:o.name, values:o.values}], o);
  const items = o.labels.map((lab, i) => {
    const x = pad.l + gap * i + (gap - bw) / 2;
    const cls = 'bar ' + ((o.classes && o.classes[i]) || (o.highlight && o.highlight.indexOf(i) < 0 ? 'muted' : ''));
    const r = svg('rect', {class:cls, x, width:bw, y:pad.t + ih, height:0, rx:4});
    const t = svg('text', {x:x + bw/2, y:Hh - 12, 'text-anchor':'middle'}); t.textContent = lab;
    const v = svg('text', {class:'vlab', x:x + bw/2, y:pad.t + ih - 8, 'text-anchor':'middle', opacity:0});
    s.append(r, t, v); return {r, v};
  });
  container.innerHTML = ''; container.appendChild(s);
  let shown = 0;
  function paint(){
    items.forEach((it, i) => {
      const on = i < shown, h = on ? (vals[i] / max) * ih : 0;
      it.r.setAttribute('y', pad.t + ih - h); it.r.setAttribute('height', h);
      it.v.setAttribute('y', pad.t + ih - h - 10); it.v.setAttribute('opacity', on ? 1 : 0); it.v.textContent = f(vals[i]);
    });
  }
  paint();
  return { show(k){ shown = k; paint(); }, set(v){ vals = v.slice(); recordLive(container, vals); if (!o.max) max = Math.max.apply(null, vals) * 1.1 || 1; paint(); } };
}

/* line(container, {labels, values | series:[{name, values, cls}], min, max, grid, ylabel}) -> {show(fraction 0..1)}
   One series keeps the filled area under it; several draw as .s1-.s4 lines with no fill. */
function line(container, o){
  const ser = series(o), all = flat(ser.map(x => x.values)), one = ser.length === 1;
  const lo = o.min != null ? o.min : Math.min.apply(null, all), hi = o.max != null ? o.max : Math.max.apply(null, all);
  const F = frame(container, o, {l:16, r:16, t:30, b:40}, hi, lo);
  record(container, 'line', o.labels, ser, o);
  const s = F.s, Hh = F.Hh, pad = F.pad, iw = F.iw, ih = F.ih, N = ser[0].values.length;
  const X = i => pad.l + iw * (N === 1 ? .5 : i / (N - 1));
  const Y = v => pad.t + ih - (hi === lo ? .5 : (v - lo) / (hi - lo)) * ih;
  let area = null;
  const paths = ser.map((se, k) => {
    const d = se.values.map((v, i) => (i ? 'L' : 'M') + X(i) + ' ' + Y(v)).join(' ');
    if (one) { area = svg('path', {class:'area', d:d + ` L ${X(N - 1)} ${pad.t + ih} L ${X(0)} ${pad.t + ih} Z`}); s.appendChild(area); }
    const p = svg('path', {class:'line ' + (se.cls || (one ? '' : SER(k))), d});
    s.appendChild(p); return p;
  });
  (o.labels || []).forEach((lab, i) => { const t = svg('text', {x:X(i), y:Hh - 12, 'text-anchor':'middle'}); t.textContent = lab; s.appendChild(t); });
  container.innerHTML = ''; container.appendChild(s);
  const lens = paths.map(p => p.getTotalLength ? p.getTotalLength() : 2000);
  paths.forEach((p, k) => {
    p.style.strokeDasharray = lens[k]; p.style.strokeDashoffset = lens[k];
    if (!reduced()) p.style.transition = 'stroke-dashoffset 1.2s cubic-bezier(.2,.7,.2,1)';
  });
  if (area) { if (!reduced()) area.style.transition = 'opacity .8s'; area.style.opacity = 0; }
  return { show(fr){
    const k = clamp(fr, 0, 1);
    paths.forEach((p, i) => { p.style.strokeDashoffset = lens[i] * (1 - k); });
    if (area) area.style.opacity = k >= 1 ? .1 : 0;
  } };
}

/* stackedBars(container, {labels, series:[{name, values, cls}], format, max, grid}) -> {show(n)}
   show(n) draws the first n categories; the value label on top is the column total. */
function stackedBars(container, o){
  const ser = o.series, n = o.labels.length, f = o.format || (v => fmt.num(v));
  const totals = o.labels.map((_, i) => ser.reduce((a, se) => a + (+se.values[i] || 0), 0));
  const max = o.max || Math.max.apply(null, totals) * 1.1 || 1;
  record(container, 'stackedBars', o.labels, ser, o);
  const F = frame(container, o, {l:10, r:10, t:34, b:40}, max);
  const s = F.s, Hh = F.Hh, pad = F.pad, bw = F.iw / n * 0.6, gap = F.iw / n, ih = F.ih;
  const cols = o.labels.map((lab, i) => {
    const x = pad.l + gap * i + (gap - bw) / 2;
    const segs = ser.map((se, k) => { const r = svg('rect', {class:'bar ' + (se.cls || SER(k)), x, width:bw, y:pad.t + ih, height:0}); s.appendChild(r); return r; });
    const t = svg('text', {x:x + bw/2, y:Hh - 12, 'text-anchor':'middle'}); t.textContent = lab;
    const v = svg('text', {class:'vlab', x:x + bw/2, y:pad.t + ih, 'text-anchor':'middle', opacity:0}); v.textContent = f(totals[i]);
    s.append(t, v); return {segs, v};
  });
  container.innerHTML = ''; container.appendChild(s);
  let shown = 0;
  function paint(){
    cols.forEach((c, i) => {
      let y = pad.t + ih;
      c.segs.forEach((r, k) => { const h = i < shown ? ((+ser[k].values[i] || 0) / max) * ih : 0; y -= h; r.setAttribute('y', y); r.setAttribute('height', h); });
      c.v.setAttribute('y', y - 10); c.v.setAttribute('opacity', i < shown ? 1 : 0);
    });
  }
  paint();
  return { show(k){ shown = k; paint(); } };
}

/* groupedBars(container, {labels, series:[{name, values, cls}], format, max, grid}) -> {show(n)} */
function groupedBars(container, o){
  const ser = o.series, n = o.labels.length, m = ser.length;
  const max = o.max || Math.max.apply(null, flat(ser.map(x => x.values))) * 1.1 || 1;
  record(container, 'groupedBars', o.labels, ser, o);
  const F = frame(container, o, {l:10, r:10, t:34, b:40}, max);
  const s = F.s, Hh = F.Hh, pad = F.pad, ih = F.ih, gap = F.iw / n, group = gap * 0.72, bw = group / m;
  const cols = o.labels.map((lab, i) => {
    const x0 = pad.l + gap * i + (gap - group) / 2;
    const rs = ser.map((se, k) => { const r = svg('rect', {class:'bar ' + (se.cls || SER(k)), x:x0 + bw * k, width:Math.max(2, bw - 4), y:pad.t + ih, height:0, rx:3}); s.appendChild(r); return r; });
    const t = svg('text', {x:x0 + group/2, y:Hh - 12, 'text-anchor':'middle'}); t.textContent = lab; s.appendChild(t);
    return rs;
  });
  container.innerHTML = ''; container.appendChild(s);
  let shown = 0;
  function paint(){
    cols.forEach((rs, i) => rs.forEach((r, k) => {
      const h = i < shown ? ((+ser[k].values[i] || 0) / max) * ih : 0;
      r.setAttribute('y', pad.t + ih - h); r.setAttribute('height', h);
    }));
  }
  paint();
  return { show(k){ shown = k; paint(); } };
}

/* hbars(container, {rows:[{name, value, cls}], format, max}) -> {show(n)} — builds .hbars > .hbar > .track */
function hbars(container, o){
  const f = o.format || (v => fmt.num(v));
  const max = o.max || Math.max.apply(null, o.rows.map(r => +r.value)) || 1;
  container.classList.add('hbars'); container.innerHTML = '';
  record(container, 'hbars', o.rows.map(r => r.name), [{name:o.name, values:o.rows.map(r => r.value)}], o);
  const items = o.rows.map(r => {
    const wrap = el('div', 'hbar', '<div class="row"><span class="name"></span><span class="val num"></span></div>' +
                                   '<div class="track"><div class="fillbar"></div></div>');
    $('.name', wrap).textContent = r.name;
    if (r.cls) $('.fillbar', wrap).classList.add(r.cls);
    container.appendChild(wrap);
    return {bar:$('.fillbar', wrap), lab:$('.val', wrap), v:+r.value};
  });
  const paint = n => items.forEach((it, i) => {
    it.bar.style.width = (i < n ? clamp(it.v / max, 0, 1) * 100 : 0) + '%';
    it.lab.textContent = i < n ? f(it.v) : '';
  });
  paint(o.rows.length);
  return { show(n){ paint(n); } };
}

/* sparkline(container, {values, cls, min, max}) — a bare trend line, no axes or labels */
function sparkline(container, o){
  const W = container.clientWidth || 160, Hh = container.clientHeight || 44, v = o.values;
  const lo = o.min != null ? o.min : Math.min.apply(null, v), hi = o.max != null ? o.max : Math.max.apply(null, v);
  const X = i => 3 + (W - 6) * (v.length === 1 ? .5 : i / (v.length - 1));
  const Y = x => Hh - 4 - (hi === lo ? .5 : (x - lo) / (hi - lo)) * (Hh - 8);
  const s = svg('svg', {class:'chart spark', viewBox:`0 0 ${W} ${Hh}`, preserveAspectRatio:'none'});
  record(container, 'sparkline', o.labels || [], [{name:o.name, values:v}], o);
  s.appendChild(svg('path', {class:'line ' + (o.cls || ''), d:v.map((x, i) => (i ? 'L' : 'M') + X(i) + ' ' + Y(x)).join(' ')}));
  container.innerHTML = ''; container.appendChild(s);
}

/* donut(container, {value 0..100, label}) -> {set(v)} */
function donut(container, o){
  const S = 220, r = 92, c = 2 * Math.PI * r;
  const s = svg('svg', {class:'chart', viewBox:`0 0 ${S} ${S}`});
  s.appendChild(svg('circle', {cx:S/2, cy:S/2, r, fill:'none', stroke:'var(--track)', 'stroke-width':22}));
  const arc = svg('circle', {cx:S/2, cy:S/2, r, fill:'none', stroke:o.color || 'var(--blue)', 'stroke-width':22, 'stroke-linecap':'round',
    'stroke-dasharray':c, 'stroke-dashoffset':c, transform:`rotate(-90 ${S/2} ${S/2})`});
  arc.style.transition = 'stroke-dashoffset 1s cubic-bezier(.2,.7,.2,1)';
  const t = svg('text', {x:S/2, y:S/2 + 14, 'text-anchor':'middle', style:'font-size:44px;font-weight:700;fill:var(--ink)'});
  s.append(arc, t); container.innerHTML = ''; container.appendChild(s);
  record(container, 'donut', [o.label || ''], [{name:o.label, values:[o.value != null ? o.value : 0]}], o);
  if (container.__chart) container.__chart.pending = o.value == null;  // filled in by the first set()
  return { set(v){ const c = container.__chart; if (c) { if (c.pending) { c.series[0].values = [+v]; c.pending = false; } else if (c.series[0].values[0] !== +v) recordLive(container, [v]); } arc.setAttribute('stroke-dashoffset', c * (1 - clamp(v, 0, 100) / 100)); countTo(t, v, 900, x => Math.round(x) + '%'); } };
}

/* ============================================================
   H.scene — whole interactions, not parts of one.

   Why this exists. The cinematic variant was asked to invent bespoke interactive JavaScript per slide
   from a one-line idea, fifteen times a deck: build the markup, wire a control, recompute on input,
   set the complete state for any step idempotently, reset cleanly when the audience steps backwards,
   and keep the control alive after the last step. That is the hardest thing in the pipeline and it was
   done freehand every time, which is why cinematic slides came out worse than the calm ones.

   A scene takes data and returns `{steps, go(step)}`. The glue — the step machine, the reset, the
   reduced-motion path, the control staying live at the end — is written once, here, and tested. The
   slide supplies content and a caption per step, which is the part that genuinely differs.

   Contract every scene keeps, so the runtime's guarantees hold without the slide restating them:
     * `go(step)` sets the COMPLETE state for that step. Any order, any number of times.
     * Controls work at every step and are never required to advance the slide.
     * Nothing animates when DECK.instant or prefers-reduced-motion is on; the end state is set directly.
     * Everything is built inside the container passed in. No ids, no document queries, no timers.
   ============================================================ */
const scene = (function(){

  /* A caption line under a scene: one short sentence per step, or none. */
  function caption(box, texts){
    if (!texts || !texts.length) return () => {};
    const n = el('p', 'scene-cap');
    box.appendChild(n);
    return step => {
      const t = texts[clamp(step, 0, texts.length - 1)];
      if (n.textContent !== t) { n.textContent = t || ''; n.classList.remove('in'); void n.offsetWidth; n.classList.add('in'); }
    };
  }

  /* Values that move between states. `node._cv` is countTo's memory, so stepping back counts down. */
  function setValues(box, values, format){
    $$('[data-v]', box).forEach(n => {
      const key = n.getAttribute('data-v');
      if (!(key in values)) return;
      countTo(n, Number(values[key]) || 0, 600, format && format[key]);
    });
  }

  /* ---------------------------------------------------------- build
     One clear moment per step out of markup the slide already wrote: `.appear` elements, optionally
     carrying `data-step`, plus a caption per step. The staged reveal every deck needs, with the
     idempotence handled. */
  function build(box, o){
    o = o || {};
    const sel = o.select || '.appear';
    const total = o.steps || $$(sel, box).length;
    const cap = caption(box, o.captions);
    return {
      steps: total,
      go(step){
        reveal(box, sel, step + 1, 0);   // step 0 shows the first item: a slide is never blank on arrival
        cap(step);
        if (o.onStep) o.onStep(step);
      },
    };
  }

  /* ---------------------------------------------------------- compare
     Two states of the world, and a control that moves between them. Before/after, with/without,
     today/target. The numbers count rather than swap, because the movement IS the message.

     o.options: [{label, values:{key:number}, note}] — two or three.
     Elements marked `data-v="key"` take the values. `o.format` maps a key to a formatter. */
  function compare(box, o){
    const opts = o.options || [];
    const cap = caption(box, o.captions);
    let cur = 0;
    const ctl = el('div', 'seg');
    opts.forEach((opt, i) => {
      const b = el('button', 'seg-b', opt.label);
      b.type = 'button';
      b.addEventListener('click', () => show(i));
      ctl.appendChild(b);
    });
    (o.controlInto ? $(o.controlInto, box) || box : box).appendChild(ctl);

    function show(i){
      cur = clamp(i, 0, opts.length - 1);
      $$('.seg-b', ctl).forEach((b, k) => b.classList.toggle('on', k === cur));
      setValues(box, opts[cur].values || {}, o.format);
      if (o.onChange) o.onChange(cur, opts[cur]);
    }
    return {
      steps: o.steps == null ? Math.max(0, opts.length - 1) : o.steps,
      // Stepping drives the same control the audience can click, so the two can never disagree, and
      // the control keeps working once the steps are spent.
      go(step){ show(o.steps === 0 ? cur : step); cap(step); },
      show,
    };
  }

  /* ---------------------------------------------------------- calculator
     Inputs the presenter can move, and figures derived from them live. The slide that answers
     "what is this costing you" better than any static number can.

     o.inputs: [{key, label, min, max, step, value, suffix}]
     o.compute(values) -> {outKey: number}; outputs are `data-v` elements.
     o.steps optionally walks preset scenarios via o.presets: [{label, set:{key:value}}]. */
  function calculator(box, o){
    const defs = o.inputs || [];
    const vals = {};
    const host = (o.controlInto ? $(o.controlInto, box) : null) || box;
    const rows = el('div', 'calc-rows');
    defs.forEach(d => {
      vals[d.key] = d.value != null ? d.value : d.min || 0;
      const row = el('label', 'calc-row');
      row.appendChild(el('span', 'calc-lab', d.label));
      const input = el('input');
      input.type = 'range';
      input.min = d.min; input.max = d.max; input.step = d.step || 1; input.value = vals[d.key];
      input.setAttribute('aria-label', d.label);
      const out = el('span', 'calc-out');
      const show = () => { out.textContent = (d.format ? d.format(vals[d.key]) : fmt.num(vals[d.key])) + (d.suffix || ''); };
      input.addEventListener('input', () => { vals[d.key] = Number(input.value); show(); recompute(); });
      show();
      row.appendChild(input);
      row.appendChild(out);
      rows.appendChild(row);
      d._input = input;
    });
    host.appendChild(rows);
    const cap = caption(box, o.captions);

    function recompute(){
      const out = o.compute ? o.compute({ ...vals }) : {};
      setValues(box, out, o.format);
      if (o.onChange) o.onChange({ ...vals }, out);
    }
    function apply(set){
      Object.keys(set || {}).forEach(k => {
        const d = defs.find(x => x.key === k);
        if (!d) return;
        vals[k] = set[k];
        d._input.value = set[k];
        d._input.dispatchEvent(new Event('input'));
      });
    }
    recompute();
    const presets = o.presets || [];
    return {
      steps: o.steps == null ? presets.length : o.steps,
      // A preset moves the sliders themselves, so the audience sees WHY the answer changed, and can
      // then take the controls over from wherever the last step left them.
      go(step){
        const p = presets[step - 1];
        if (p) apply(p.set); else if (step === 0 && presets.length) apply(Object.fromEntries(defs.map(d => [d.key, d.value != null ? d.value : d.min || 0])));
        cap(step);
      },
      values: () => ({ ...vals }),
      apply,
    };
  }

  /* ---------------------------------------------------------- chartFocus
     A chart where each step brings one series or category forward and says why it matters. The chart
     stays readable at every step; focus is emphasis, never a redraw.

     o.draw(container, focusIndex) -> void. o.labels: names for the legend buttons. */
  function chartFocus(box, o){
    const host = $(o.into, box) || box;
    const cap = caption(box, o.captions);
    const labels = o.labels || [];
    let cur = -1;
    let legend = null;
    if (labels.length) {
      legend = el('div', 'focus-legend');
      labels.forEach((name, i) => {
        const b = el('button', 'focus-b', name);
        b.type = 'button';
        b.addEventListener('click', () => focus(cur === i ? -1 : i));
        legend.appendChild(b);
      });
      (o.legendInto ? $(o.legendInto, box) || box : box).appendChild(legend);
    }
    function focus(i){
      cur = i;
      if (legend) $$('.focus-b', legend).forEach((b, k) => b.classList.toggle('on', k === i));
      if (o.draw) o.draw(host, i);
      if (o.onFocus) o.onFocus(i);
    }
    focus(-1);
    return {
      steps: o.steps == null ? labels.length : o.steps,
      go(step){ focus(step === 0 ? -1 : Math.min(step - 1, labels.length - 1)); cap(step); },
      focus,
    };
  }

  /* ---------------------------------------------------------- explorer
     Clickable items with a detail panel. Steps walk the items in order; afterwards the audience picks.
     The one interaction that survives being handed to someone else in the room.

     o.items: [{label, title, body}] — or the slide's own `[data-item]` elements with `data-title`/`data-body`. */
  function explorer(box, o){
    o = o || {};
    const items = $$(o.select || '[data-item]', box);
    const panel = $(o.panel || '[data-panel]', box);
    const cap = caption(box, o.captions);
    let cur = -1;
    items.forEach((n, i) => {
      if (n.tagName !== 'BUTTON') n.setAttribute('tabindex', '0');
      n.addEventListener('click', () => open(cur === i ? -1 : i));
      n.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(cur === i ? -1 : i); } });
    });
    function open(i){
      cur = i;
      items.forEach((n, k) => { n.classList.toggle('on', k === i); n.setAttribute('aria-expanded', String(k === i)); });
      if (panel) {
        const src = items[i];
        panel.classList.toggle('in', i >= 0);
        if (src) {
          const t = $('[data-panel-title]', panel), b = $('[data-panel-body]', panel);
          if (t) t.textContent = src.getAttribute('data-title') || src.textContent.trim();
          if (b) b.innerHTML = src.getAttribute('data-body') || '';
        }
      }
      if (o.onOpen) o.onOpen(i, items[i]);
    }
    open(-1);
    return {
      steps: o.steps == null ? items.length : o.steps,
      go(step){ open(step === 0 ? -1 : Math.min(step - 1, items.length - 1)); cap(step); },
      open,
    };
  }

  /* ---------------------------------------------------------- timeline
     Ordered stages, advanced by step, with a scrubber that stays live afterwards. Process, roadmap,
     migration, anything where the ORDER is the content.

     Stages are the slide's own `[data-stage]` elements. */
  function timeline(box, o){
    o = o || {};
    const stages = $$(o.select || '[data-stage]', box);
    const cap = caption(box, o.captions);
    let cur = 0;
    const bar = el('div', 'tl-bar');
    stages.forEach((n, i) => {
      const dot = el('button', 'tl-dot');
      dot.type = 'button';
      dot.setAttribute('aria-label', n.getAttribute('data-stage') || `Stage ${i + 1}`);
      dot.addEventListener('click', () => at(i + 1));
      bar.appendChild(dot);
    });
    (o.barInto ? $(o.barInto, box) || box : box).appendChild(bar);
    function at(n){
      cur = clamp(n, 0, stages.length);
      stages.forEach((s, i) => {
        s.classList.toggle('in', i < cur);
        s.classList.toggle('now', i === cur - 1);
      });
      $$('.tl-dot', bar).forEach((d, i) => { d.classList.toggle('on', i < cur); d.classList.toggle('now', i === cur - 1); });
      if (o.onStage) o.onStage(cur - 1, stages[cur - 1]);
    }
    at(o.start == null ? 1 : o.start);
    return {
      steps: o.steps == null ? Math.max(0, stages.length - 1) : o.steps,
      go(step){ at(step + 1); cap(step); },
      at,
    };
  }

  return { build, compare, calculator, chartFocus, explorer, timeline };
})();

window.H = { $, $$, el, clamp, fmt, animate, countTo, resetCount, reveal, state, icon, asset, bindInput, segmented, spotlight, tabs,
  accordion, hotspots, chart:{ bars, stackedBars, groupedBars, line, donut, hbars, sparkline }, scene, reduced };
})();
