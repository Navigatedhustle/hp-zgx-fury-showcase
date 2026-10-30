/* ============================================================
   HP deck shell — builds slides, drives steps, navigation, presenter tools.
   Inputs (written by the assembler):
     <script id="deck-config" type="application/json">  {title, storageKey, embed, assetBase}
     <script id="assets" type="application/json">       {img:{key:dataUri}, icons:{name:svg}}
     <script id="deck-slides" type="application/json">  [{id,title,steps,notes,sources,theme,bleed,hasScript,stamp}]
     <template data-slide="{id}">…inner html…</template>
     DECK.define("{id}", function(H){ …; return {mount, go}; })
   ============================================================ */
(function(){
"use strict";
const J = id => { const n = document.getElementById(id); try { return n ? JSON.parse(n.textContent) : null; } catch(e){ return null; } };
const CFG = Object.assign({title:'Deck', storageKey:'hpdeck', embed:false, assetBase:null}, J('deck-config') || {});
const Q = new URLSearchParams(location.search);
if (Q.has('embed')) CFG.embed = true;
window.DECK_ASSETS = J('assets') || {img:{}, icons:{}};
const META = J('deck-slides') || [];

const DECK = window.DECK = {
  defs:{}, errors:[], slides:[], cur:0, step:0, instant:Q.has('instant'), showSrc:false,
  define(id, factory){ this.defs[id] = factory; },
  assetUrl(key){
    const img = window.DECK_ASSETS.img || {};
    if (img[key]) return img[key];
    return CFG.assetBase ? CFG.assetBase.replace(/\/?$/, '/') + encodeURIComponent(key) : '';
  }
};
function err(slideId, phase, e){
  const msg = (e && (e.stack || e.message)) || String(e);
  DECK.errors.push({slide:slideId, phase, message:msg});
  console.error('[slide ' + slideId + '] ' + phase + ':', e);
  flagErrors();
}
window.addEventListener('error', e => {
  DECK.errors.push({slide:null, phase:'window', message:e.message + ' @' + e.lineno});
  flagErrors();
});

/* ---------- build ---------- */
function resolveAssets(root){
  root.querySelectorAll('[src^="asset:"]').forEach(n => n.setAttribute('src', DECK.assetUrl(n.getAttribute('src').slice(6))));
  root.querySelectorAll('[style*="asset:"]').forEach(n => {
    n.setAttribute('style', n.getAttribute('style').replace(/url\((['"]?)asset:([\w.-]+)\1\)/g, (m, q, k) => 'url("' + DECK.assetUrl(k) + '")'));
  });
  root.querySelectorAll('[data-icon]').forEach(n => {
    if (!n.classList.contains('icon')) n.classList.add('icon');
    n.innerHTML = H.icon(n.dataset.icon) || '';
  });
}
function autoSteps(root){
  const loose = root.querySelectorAll('.appear:not([data-step])').length;
  let maxStep = 0;
  root.querySelectorAll('[data-step]').forEach(n => { maxStep = Math.max(maxStep, +n.dataset.step || 0); });
  return Math.max(loose, maxStep);
}
function build(){
  const stage = document.getElementById('stage');
  const logo = DECK.assetUrl('hp');
  META.forEach((m, i) => {
    const sec = document.createElement('section');
    sec.className = 'slide s-' + m.id + (m.theme && m.theme !== 'light' ? ' theme-' + m.theme : '') + (m.bleed ? ' bleed' : '');
    sec.dataset.id = m.id;
    const tpl = document.querySelector('template[data-slide="' + m.id + '"]');
    sec.innerHTML = tpl ? tpl.innerHTML : '';
    resolveAssets(sec);
    if (m.sources) { const s = document.createElement('div'); s.className = 'src'; s.innerHTML = m.sources; sec.appendChild(s); }
    if (m.stamp !== false) {
      const st = document.createElement('div'); st.className = 'stamp';
      st.innerHTML = '<span>' + String(i + 1).padStart(2, '0') + '</span>' + (logo ? '<img src="' + logo + '" alt="HP">' : '');
      sec.appendChild(st);
    }
    stage.appendChild(sec);
    const slide = {meta:m, root:sec, def:{}, steps:0};
    DECK.slides.push(slide);
  });
}

/* Mounting runs a slide's script and measures its charts, so it has to happen while the slide is
   laid out. Doing all of them at load costs a visible freeze on a long deck, so a slide is mounted
   on demand — always before it is shown — and the rest drift in while the browser is idle. */
function mountSlide(s){
  if (s.mounted) return s;
  s.mounted = true;
  const m = s.meta;
  const wasOn = s.root.classList.contains('on');
  if (!wasOn) { s.root.classList.add('on'); s.root.style.visibility = 'hidden'; }
  if (DECK.defs[m.id]) {
    try { s.def = DECK.defs[m.id](window.H) || {}; } catch(e){ err(m.id, 'define', e); }
  } else if (m.hasScript) {
    err(m.id, 'parse', new Error('slide script failed to load (syntax error?)'));
  }
  if (typeof s.def.mount === 'function') { try { s.def.mount(s.root); } catch(e){ err(m.id, 'mount', e); } }
  // after mount(), so a script that injects .appear/[data-step] is counted
  s.steps = Number.isFinite(+m.steps) && m.steps !== null && m.steps !== undefined ? Math.max(0, +m.steps) : autoSteps(s.root);
  applyStep(s, 0);
  if (!wasOn) { s.root.classList.remove('on'); s.root.style.visibility = ''; }
  return s;
}

const mountAll = () => DECK.slides.forEach(mountSlide);
DECK.mountAll = mountAll;

/* Mount the neighbours too, so stepping or swiping never waits on a script. */
function mountAround(i){
  for (let k = i - 1; k <= i + 1; k++) { const s = DECK.slides[k]; if (s) mountSlide(s); }
}

function mountIdle(){
  const rest = () => {
    const s = DECK.slides.find(x => !x.mounted);
    if (!s) return;
    mountSlide(s);
    schedule();
  };
  const schedule = () => (window.requestIdleCallback ? requestIdleCallback(rest, {timeout:500}) : setTimeout(rest, 50));
  schedule();
}

/* ---------- steps ---------- */
function applyStep(s, step){
  const root = s.root;
  if (s.meta.auto !== false) {
    let k = 0;
    root.querySelectorAll('.appear').forEach(n => {
      const on = n.hasAttribute('data-step') ? step >= +n.dataset.step : (k++ < step);
      n.classList.toggle('in', on);
    });
    root.querySelectorAll('[data-count]').forEach(n => {
      const host = n.closest('.appear');
      const on = n.hasAttribute('data-step') ? step >= +n.dataset.step : (!host || host.classList.contains('in'));
      const d = +(n.dataset.decimals || 0), pre = n.dataset.prefix || '', suf = n.dataset.suffix || '';
      const f = x => pre + H.fmt.num(x, d) + suf;
      if (on) H.countTo(n, +n.dataset.count, +(n.dataset.ms || 900), f); else H.resetCount(n, f);
    });
  }
  if (typeof s.def.go === 'function') { try { s.def.go(root, step); } catch(e){ err(s.meta.id, 'go(' + step + ')', e); } }
}

/* ---------- navigation ---------- */
function show(i, step, silent){
  i = H.clamp(i, 0, DECK.slides.length - 1);
  const s = DECK.slides[i]; if (!s) return;
  mountAround(i);  // s.steps is only trustworthy once the slide's script has run
  if (step === 'end') step = s.steps;
  step = H.clamp(step || 0, 0, s.steps);
  DECK.slides.forEach((x, k) => x.root.classList.toggle('on', k === i));
  const changedSlide = i !== DECK.cur;
  DECK.cur = i; DECK.step = step;
  applyStep(s, step);
  const prog = document.getElementById('progress');
  // each slide is one unit of the deck; a stepped slide fills its unit as its steps advance.
  if (prog) prog.style.width = H.clamp((i + (s.steps ? step / s.steps : 1)) / DECK.slides.length * 100, 0, 100) + '%';
  if (!CFG.embed) { try { history.replaceState(null, '', '#' + (i + 1) + (step ? '.' + step : '')); } catch(e){} }
  if (changedSlide && noteEd.classList.contains('on')) neFill();
  announce(s, i, step, changedSlide);
  pushPresenter(); post();
  if (!silent) document.dispatchEvent(new CustomEvent('deck:change', {detail:{index:i, step}}));
}
function next(){ const s = DECK.slides[DECK.cur]; if (!s) return; if (DECK.step < s.steps) show(DECK.cur, DECK.step + 1); else if (DECK.cur < DECK.slides.length - 1) show(DECK.cur + 1, 0); }
function prev(){ if (DECK.step > 0) show(DECK.cur, DECK.step - 1); else if (DECK.cur > 0) show(DECK.cur - 1, 'end'); }
DECK.next = next; DECK.prev = prev; DECK.show = show;

/* ---------- announcements (screen readers) + transient toast ---------- */
let liveEl = null, liveT = null;
function say(msg){
  if (!liveEl) {
    liveEl = document.createElement('div');
    liveEl.id = 'live'; liveEl.className = 'sr';
    liveEl.setAttribute('role', 'status');
    liveEl.setAttribute('aria-live', 'polite');
    liveEl.setAttribute('aria-atomic', 'true');
    document.body.appendChild(liveEl);
  }
  clearTimeout(liveT);
  liveT = setTimeout(() => { liveEl.textContent = msg; }, 90); // coalesce rapid step changes
}
function announce(s, i, step, changedSlide){
  if (!document.body) return;
  const where = 'Slide ' + (i + 1) + ' of ' + DECK.slides.length;
  const what = s.meta.title ? ': ' + s.meta.title : '';
  say(changedSlide || !s.steps ? where + what + (s.steps ? '. Step ' + step + ' of ' + s.steps + '.' : '.')
                               : 'Step ' + step + ' of ' + s.steps + '.');
}
function toast(msg){
  const h = document.getElementById('hud');
  if (h) {
    h.textContent = msg; h.classList.remove('gone');
    clearTimeout(DECK._toast); DECK._toast = setTimeout(() => h.classList.add('gone'), 5000);
  }
  say(msg);
}

/* ---------- overlays: modal semantics + focus restore ---------- */
let lastFocus = null;
function ovOpen(node){
  if (node.classList.contains('on')) return;
  lastFocus = document.activeElement;
  node.classList.add('on'); node.setAttribute('aria-hidden', 'false');
}
function ovClose(node){
  if (!node.classList.contains('on')) return;
  node.classList.remove('on'); node.setAttribute('aria-hidden', 'true');
  const f = lastFocus; lastFocus = null;
  if (f && f.focus && document.contains(f)) { try { f.focus(); } catch(e){} }
}
function ovToggle(node){ node.classList.contains('on') ? ovClose(node) : ovOpen(node); }
function asDialog(node, label){
  node.setAttribute('role', 'dialog');
  node.setAttribute('aria-modal', 'true');
  node.setAttribute('aria-label', label);
  node.setAttribute('aria-hidden', 'true');
  node.tabIndex = -1;  // so the overlay itself can take focus when it opens
}

/* ---------- scaling ---------- */
function fit(){
  const st = document.getElementById('stage');
  const k = Math.min(innerWidth / 1600, innerHeight / 900);
  st.style.transform = 'translate(-50%,-50%) scale(' + k + ')';
  // A 16:9 stage letterboxed into a portrait phone puts 17px body text at ~4px. Say so rather
  // than rendering something nobody can read.
  document.body.classList.toggle('cramped', !CFG.embed && k < 0.42 && innerHeight > innerWidth);
}

/* ---------- speaker notes (edits persist in localStorage) ---------- */
const NKEY = 'hpdeck-notes-' + CFG.storageKey;
let noteEdits = {}, noteStore = false;
try { localStorage.setItem(NKEY + '-t', '1'); localStorage.removeItem(NKEY + '-t'); noteEdits = JSON.parse(localStorage.getItem(NKEY) || '{}'); noteStore = true; } catch(e){}
const notesFor = i => { const s = DECK.slides[i]; if (!s) return []; return noteEdits[s.meta.id] || s.meta.notes || []; };
function saveNotes(){ if (noteStore) try { localStorage.setItem(NKEY, JSON.stringify(noteEdits)); } catch(e){} }

const noteEd = document.createElement('div'); noteEd.id = 'noteed'; noteEd.className = 'ov';
noteEd.innerHTML = '<div class="head"><b>Speaker notes</b><i data-k="slide"></i><button data-k="reset">Restore</button>' +
  '<button data-k="export">Export all</button><button data-k="save">Download</button><button data-k="close">Close</button></div>' +
  '<textarea data-k="area" spellcheck="false" placeholder="One note per line"></textarea><div class="foot" data-k="foot"></div>';
const nq = k => noteEd.querySelector('[data-k="' + k + '"]');
function neFill(){
  const s = DECK.slides[DECK.cur]; if (!s) return;
  nq('slide').textContent = 'Slide ' + (DECK.cur + 1) + (noteEdits[s.meta.id] ? ' · edited' : '');
  nq('area').value = notesFor(DECK.cur).map(t => t.replace(/<[^>]+>/g, '')).join('\n');
  nq('foot').textContent = noteStore ? 'Saves as you type.' : 'Session only — export before closing.';
}
function download(name, txt){
  try {
    const url = URL.createObjectURL(new Blob([txt], {type:'text/plain;charset=utf-8'}));
    const a = document.createElement('a');
    a.href = url; a.download = name; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return true;
  } catch(e){ return false; }
}
const notesText = () => DECK.slides.map((s, i) => 'SLIDE ' + String(i + 1).padStart(2, '0') + ' — ' + (s.meta.title || '') + '\n' +
  notesFor(i).map(t => '  • ' + t.replace(/<[^>]+>/g, '')).join('\n')).join('\n\n');
const notesFile = () => (CFG.title || 'deck').replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) + '-notes.txt';
function exportNotes(){
  const txt = notesText(), name = notesFile();
  try { navigator.clipboard && navigator.clipboard.writeText(txt); } catch(e){}
  const w = open('', 'hpdeck-notes-export', 'width=760,height=900');
  if (!w) { // popup blocked: hand the presenter a file instead of failing silently
    const ok = download(name, txt);
    const foot = nq('foot');
    if (foot) foot.textContent = ok ? 'Popup blocked — downloaded ' + name + ' (also copied to the clipboard).'
                                    : 'Popup blocked and the download failed — the notes are on the clipboard.';
    toast(ok ? 'Notes downloaded as ' + name : 'Notes copied to the clipboard');
    return;
  }
  w.document.write('<!doctype html><meta charset=utf-8><title>Speaker notes</title><style>body{margin:0;padding:34px 40px;font:14px/1.6 ui-monospace,Consolas,monospace;white-space:pre-wrap}</style>');
  w.document.body.textContent = txt; w.document.close();
}

/* ---------- presenter window (S) ---------- */
let pres = null, t0 = null;
function openPresenter(){
  pres = open('', 'hpdeck-presenter', 'width=1100,height=760');
  if (!pres) { toast('Presenter window blocked — allow pop-ups for this page, then press S again'); return; }
  t0 = t0 || Date.now();
  pres.document.write(`<!doctype html><meta charset=utf-8><title>Presenter — ${CFG.title}</title>
  <style>body{margin:0;background:#0D0F16;color:#E8ECF6;font:18px/1.55 -apple-system,"Segoe UI",Arial;display:flex;flex-direction:column;height:100vh}
  header{display:flex;align-items:center;gap:18px;padding:16px 26px;border-bottom:1px solid #2A3145;font:600 13px ui-monospace,monospace;letter-spacing:.1em}
  header b{color:#8FD3FF} header .t{margin-left:auto;font-size:22px;color:#fff}
  button{font:600 12px ui-monospace,monospace;letter-spacing:.09em;text-transform:uppercase;background:#161A26;color:#C7D3EC;border:1px solid #2A3145;border-radius:7px;padding:9px 14px;cursor:pointer}
  main{flex:1;overflow:auto;padding:22px 30px} h1{font-size:26px;margin:0 0 6px;letter-spacing:-.01em} .st{font:600 13px ui-monospace,monospace;color:#7F8CA8;letter-spacing:.12em;margin-bottom:18px}
  ul{margin:0;padding-left:22px} li{margin-bottom:12px} li b{color:#fff} li i{color:#9FB0D6}
  footer{padding:14px 30px;border-top:1px solid #2A3145;color:#7F8CA8;font:600 13px ui-monospace,monospace;letter-spacing:.08em}</style>
  <header><button id=p>◀ Prev</button><button id=n>Next ▶</button><span id=pos></span><span class=t id=tm>00:00</span><button id=r>Reset timer</button></header>
  <main><h1 id=ti></h1><div class=st id=st></div><ul id=no></ul></main><footer id=nx></footer>`);
  pres.document.close();
  pres.document.getElementById('n').onclick = () => next();
  pres.document.getElementById('p').onclick = () => prev();
  pres.document.getElementById('r').onclick = () => { t0 = Date.now(); };
  pres.addEventListener('keydown', onKey);
  clearInterval(DECK._tm);
  DECK._tm = setInterval(() => {
    if (!pres || pres.closed) return clearInterval(DECK._tm);
    const s = Math.floor((Date.now() - t0) / 1000);
    pres.document.getElementById('tm').textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }, 1000);
  pushPresenter();
}
function pushPresenter(){
  if (!pres || pres.closed) return;
  const s = DECK.slides[DECK.cur], nx = DECK.slides[DECK.cur + 1], d = pres.document;
  d.getElementById('pos').textContent = 'SLIDE ' + (DECK.cur + 1) + ' / ' + DECK.slides.length;
  d.getElementById('ti').textContent = s.meta.title || '';
  d.getElementById('st').textContent = s.steps ? 'STEP ' + DECK.step + ' / ' + s.steps : 'NO STEPS';
  d.getElementById('no').innerHTML = notesFor(DECK.cur).map(t => '<li>' + t + '</li>').join('');
  d.getElementById('nx').textContent = nx ? 'NEXT → ' + (nx.meta.title || 'Slide ' + (DECK.cur + 2)) : 'END OF DECK';
}

/* ---------- overview (O) ---------- */
const overview = document.createElement('div'); overview.id = 'overview'; overview.className = 'ov';
asDialog(overview, 'Slide overview');
function openOverview(){
  mountAll();  // thumbnails clone the live DOM, so every slide must have run its script first
  overview.innerHTML = '<div class="grid"></div>';
  const g = overview.firstChild;
  DECK.slides.forEach((s, i) => {
    const label = String(i + 1).padStart(2, '0') + '  ' + (s.meta.title || '');
    const th = document.createElement('button'); th.type = 'button';
    th.className = 'th' + (i === DECK.cur ? ' cur' : '');
    th.setAttribute('aria-label', 'Go to slide ' + (i + 1) + (s.meta.title ? ': ' + s.meta.title : ''));
    if (i === DECK.cur) th.setAttribute('aria-current', 'true');
    const box = document.createElement('div'); box.className = 'box'; box.setAttribute('aria-hidden', 'true');
    const clone = s.root.cloneNode(true); clone.classList.add('on'); clone.removeAttribute('id');
    clone.querySelectorAll('.appear').forEach(n => n.classList.add('in'));
    box.appendChild(clone); th.appendChild(box);
    const lab = document.createElement('span'); lab.textContent = label; th.appendChild(lab);
    th.addEventListener('click', () => { ovClose(overview); show(i, 0); });
    g.appendChild(th);
  });
  ovOpen(overview);
  const first = g.children[DECK.cur] || g.firstChild;
  if (first) first.focus();
  requestAnimationFrame(() => overview.querySelectorAll('.box').forEach(b => { b.firstChild.style.transform = 'scale(' + (b.clientWidth / 1600) + ')'; }));
}

/* ---------- help (?) ---------- */
const help = document.createElement('div'); help.id = 'help'; help.className = 'ov';
asDialog(help, 'Keyboard shortcuts');
help.innerHTML = '<h4>Keyboard</h4><table>' + [
  ['→ Space PgDn', 'Next step / slide'], ['← PgUp', 'Previous'], ['Home End', 'First / last slide'], ['F', 'Fullscreen'],
  ['S', 'Presenter window (notes + timer)'], ['E', 'Edit speaker notes'], ['C', 'Show sources'], ['O', 'Overview'],
  ['R', 'Replay slide'], ['B', 'Black screen'], ['?', 'This help'],
  ['Tab', 'Move between the controls on a slide'], ['Space Enter', 'Activate the focused control']]
  .map(r => '<tr><td><kbd>' + r[0] + '</kbd></td><td>' + r[1] + '</td></tr>').join('') + '</table>';
const black = document.createElement('div'); black.id = 'black';

/* ---------- keys ---------- */
/* Space/Enter belong to the focused control, not to the deck: every in-slide button,
   link, tab and segmented control has to stay keyboard-operable. Arrows always navigate. */
const ACTIVATABLE_ROLE = /^(button|link|tab|menuitem|menuitemcheckbox|menuitemradio|option|checkbox|radio|switch)$/;
function activatable(t){
  if (!t || t.nodeType !== 1) return false;
  const tag = t.tagName;
  if (tag === 'BUTTON' || tag === 'SUMMARY' || (tag === 'A' && t.hasAttribute('href'))) return true;
  const role = t.getAttribute && t.getAttribute('role');
  return !!(role && ACTIVATABLE_ROLE.test(role.trim().toLowerCase()));
}
function onKey(e){
  if (DECK.editor && DECK.editor.key(e)) return;  // edit mode owns these keys (runtime/edit.js)
  const t = e.target, tag = t && t.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) { if (e.key === 'Escape' && t.blur) t.blur(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key;
  if ((k === ' ' || k === 'Enter') && activatable(t)) return;  // let the browser activate it
  if (black.classList.contains('on') && k !== 'b' && k !== 'B' && k !== '.') { black.classList.remove('on'); }
  switch (k) {
    case 'ArrowRight': case 'ArrowDown': case ' ': case 'PageDown': case 'Enter': next(); break;
    case 'ArrowLeft': case 'ArrowUp': case 'PageUp': case 'Backspace': prev(); break;
    case 'Home': show(0, 0); break;
    case 'End': show(DECK.slides.length - 1, 'end'); break;
    case 'f': case 'F': if (!document.fullscreenElement) document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); else document.exitFullscreen(); break;
    case 's': case 'S': if (!CFG.embed) openPresenter(); break;
    case 'e': case 'E': if (!CFG.embed) { ovToggle(noteEd); if (noteEd.classList.contains('on')) { neFill(); nq('area').focus(); } } break;
    case 'c': case 'C': DECK.showSrc = !DECK.showSrc; document.getElementById('stage').classList.toggle('show-src', DECK.showSrc); break;
    case 'o': case 'O': if (overview.classList.contains('on')) ovClose(overview); else openOverview(); break;
    case 'Escape': ovClose(overview); ovClose(help); ovClose(noteEd); break;
    case 'r': case 'R': show(DECK.cur, 0); break;
    case 'b': case 'B': case '.': black.classList.toggle('on'); break;
    case '?': ovToggle(help); if (help.classList.contains('on')) help.focus(); break;
    default: return;
  }
  e.preventDefault();
}

/* ---------- embed API (used by the builder app) ---------- */
function post(){
  if (!CFG.embed || window.parent === window) return;
  const s = DECK.slides[DECK.cur];
  window.parent.postMessage({type:'hpdeck', event:'state', index:DECK.cur, step:DECK.step, steps:s ? s.steps : 0, count:DECK.slides.length, errors:DECK.errors.length}, '*');
}
window.addEventListener('message', e => {
  const d = e.data; if (!d || d.type !== 'hpdeck') return;
  if (d.cmd === 'goto') show(d.index || 0, d.step === 'end' ? 'end' : (d.step || 0));
  else if (d.cmd === 'next') next();
  else if (d.cmd === 'prev') prev();
  else if (d.cmd === 'state') post();
  else if ((d.cmd === 'edit' || d.cmd === 'select' || d.cmd === 'locks') && DECK.editor) DECK.editor.msg(d);
});

/* ---------- print ---------- */
function preparePrint(){
  mountAll();  // every slide prints, including ones never shown on screen
  DECK.instant = true;
  document.body.classList.add('instant');
  DECK.slides.forEach(s => applyStep(s, s.steps));
}
function afterPrint(){ DECK.instant = Q.has('instant'); document.body.classList.toggle('instant', DECK.instant); show(DECK.cur, DECK.step, true); }
window.addEventListener('beforeprint', preparePrint);
window.addEventListener('afterprint', afterPrint);

/* ---------- script-error indicator ----------
   A standalone deck has no console in front of the audience: show a small, non-blocking
   badge when a slide script fails. The builder has its own indicator, so never in embed mode. */
let errFlag = null;
function flagErrors(){
  if (CFG.embed || !DECK.errors.length || !document.body) return;
  if (!errFlag) {
    errFlag = document.createElement('div'); errFlag.id = 'errflag';
    const btn = document.createElement('button');
    btn.type = 'button'; btn.setAttribute('aria-expanded', 'false');
    const list = document.createElement('pre'); list.id = 'errlist';
    btn.setAttribute('aria-controls', 'errlist');
    btn.addEventListener('click', () => {
      const open = !errFlag.classList.contains('open');
      errFlag.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', String(open));
    });
    errFlag.append(btn, list);
    document.body.appendChild(errFlag);
  }
  const n = DECK.errors.length;
  errFlag.firstChild.textContent = '⚠ ' + n + ' script error' + (n === 1 ? '' : 's');
  errFlag.lastChild.textContent = DECK.errors
    .map(e => (e.slide ? 'slide ' + e.slide + ' · ' : '') + e.phase + ': ' + e.message).join('\n\n');
}

/* ---------- on-screen controls ----------
   Keyboard and swipe are the fast paths, but a deck opened by someone who did not build it has to
   be navigable with a mouse or a thumb. Low-chrome cluster, fades when idle, never in embed mode. */
const CONTROLS = [
  ['prev', 'Previous', 'M14 6l-6 6 6 6', () => prev()],
  ['next', 'Next', 'M10 6l6 6-6 6', () => next()],
  ['overview', 'Overview', 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z', () => (overview.classList.contains('on') ? ovClose(overview) : openOverview())],
  ['full', 'Fullscreen', 'M4 9V4h5M20 15v5h-5M15 4h5v5M9 20H4v-5', () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  }],
  ['help', 'Shortcuts', 'M9 9a3 3 0 1 1 4 2.8c-.6.3-1 .9-1 1.7M12 17h.01', () => ovToggle(help)],
];
let idleT = null;
function buildControls(){
  if (CFG.embed) return;
  const bar = document.createElement('nav');
  bar.id = 'controls'; bar.setAttribute('aria-label', 'Deck controls');
  CONTROLS.forEach(([key, label, d, fn]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.dataset.k = key; b.title = label; b.setAttribute('aria-label', label);
    b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + d + '"/></svg>';
    b.addEventListener('click', () => { fn(); wake(); });
    bar.appendChild(b);
  });
  document.body.appendChild(bar);
  const rot = document.createElement('div');
  rot.id = 'rotate';
  rot.innerHTML = '<b>Turn your device sideways</b><span>This deck is built for a wide screen. '
    + 'In landscape the slides fill the display and stay readable.</span>';
  document.body.appendChild(rot);
  const wake = () => {
    bar.classList.remove('idle');
    clearTimeout(idleT);
    idleT = setTimeout(() => bar.classList.add('idle'), 2600);
  };
  ['pointermove', 'pointerdown', 'keydown'].forEach(e => document.addEventListener(e, wake, {passive:true}));
  wake();
}

/* ---------- QA API ---------- */
DECK.api = {
  count: () => DECK.slides.length,
  steps: i => DECK.slides[i] ? mountSlide(DECK.slides[i]).steps : 0,
  goto: (i, step) => show(i, step, true),
  errors: () => DECK.errors.slice(),
  preparePrint
};

/* ---------- boot ---------- */
function boot(){
  document.title = CFG.title;
  if (CFG.embed) document.body.classList.add('embed');
  if (DECK.instant) document.body.classList.add('instant');
  document.body.append(noteEd, overview, help, black);
  asDialog(noteEd, 'Speaker notes');
  nq('area').addEventListener('input', () => {
    const s = DECK.slides[DECK.cur]; if (!s) return;
    const lines = nq('area').value.split('\n').map(x => x.trim()).filter(Boolean);
    if (lines.length) noteEdits[s.meta.id] = lines; else delete noteEdits[s.meta.id];
    saveNotes(); pushPresenter();
  });
  nq('area').addEventListener('keydown', e => { if (e.key === 'Escape') { ovClose(noteEd); e.stopPropagation(); } });
  nq('close').onclick = () => ovClose(noteEd);
  nq('export').onclick = exportNotes;
  nq('save').onclick = () => {
    const name = notesFile();
    nq('foot').textContent = download(name, notesText()) ? 'Downloaded ' + name : 'Download blocked by the browser.';
  };
  nq('reset').onclick = () => { const s = DECK.slides[DECK.cur]; if (s) { delete noteEdits[s.meta.id]; saveNotes(); neFill(); pushPresenter(); } };
  help.onclick = () => ovClose(help);

  build();
  fit(); addEventListener('resize', fit);
  document.addEventListener('keydown', onKey);

  let tx = null;
  document.addEventListener('touchstart', e => { const t = e.target; tx = (DECK.editing || (t.closest && t.closest('button,input,a,select,textarea'))) ? null : e.touches[0].clientX; }, {passive:true});
  document.addEventListener('touchend', e => { if (tx == null) return; const dx = e.changedTouches[0].clientX - tx; if (Math.abs(dx) > 50) (dx < 0 ? next : prev)(); tx = null; });

  let i = 0, st = 0;
  if (Q.has('slide')) { i = +Q.get('slide') || 0; st = Q.get('step') === 'end' ? 'end' : (+Q.get('step') || 0); }
  else { const m = location.hash.match(/^#(\d+)(?:\.(\d+))?/); if (m) { i = +m[1] - 1; st = +(m[2] || 0); } }
  show(i, st, true);

  const hud = document.getElementById('hud');
  if (hud) setTimeout(() => hud.classList.add('gone'), 3500);
  buildControls();
  mountIdle();  // the rest of the deck warms up in the background
  flagErrors();
  DECK.ready = true;
  document.dispatchEvent(new CustomEvent('deck:ready'));
  post();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
