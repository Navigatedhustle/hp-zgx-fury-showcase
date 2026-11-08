/* ============================================================
   HP deck in-slide editor — the overlay half of the direct-manipulation editor.
   Inert until the builder (the parent frame) turns it on; zero listeners until then.

     parent -> deck : {type:'hpdeck', cmd:'edit',   on:true|false}
                      {type:'hpdeck', cmd:'select', eid:string|null}
                      {type:'hpdeck', cmd:'locks',  map:{eid:{editable_text,deletable,locks}}}
     deck -> parent : {type:'hpdeck', event:'edit-ready'}
                      {type:'hpdeck', event:'edit-select', eid, tag, classes, text, rect, canText, canDelete, locks}
                      {type:'hpdeck', event:'edit-op', op:{...}}   // shapes match backend/app/edit.py
                      {type:'hpdeck', event:'edit-dirty', eid, text}

   It reports intents only: no fetch, no storage, no optimistic reorder/delete — the parent
   owns the server round-trip and re-renders. Every gesture offered is one edit.py will
   accept (the locks map is the server's own outline()).

   Chrome lives in document.body, outside #stage, so autoSteps() never counts it, the
   overview clone never copies it and nothing in a slide moves when something is selected.
   Element rects are read live (rAF) and reported in stage coordinates, so the CSS-scaled
   stage is handled at any zoom.
   ============================================================ */
(function(){
"use strict";
const parentOrigin = new URL(location.href).origin;
const DECK = window.DECK;
if (!DECK) return;

const VOID = ' area base br col embed hr img input link meta param source track wbr ';
const MAX_TEXT = 2000;  // edit.py refuses longer

let on = false, layer = null, ring = null, hoverBox = null, dropBox = null, delBtn = null;
let selEl = null, selEid = null, hoverEl = null;
let locks = {};          // eid -> ElementInfo subset, straight from outline()
let editing = null;      // {el, eid, orig}
let drag = null;         // {el, eid, x0, y0, started, sibs, from, axis, idx}
let raf = 0, lastRect = null, postT = 0, dirtyT = 0;

/* ---------- messaging ---------- */
function send(msg){
  if (!window.parent || window.parent === window) return;
  msg.type = 'hpdeck';
  try { window.parent.postMessage(msg, parentOrigin); } catch(e){}
}

/* ---------- geometry (the stage is transform-scaled; read it, never assume 1) ---------- */
const stage = () => document.getElementById('stage');
const cur = () => { const s = DECK.slides[DECK.cur]; return s ? s.root : null; };
const R1 = v => Math.round(v * 10) / 10;

function stageRect(el){
  const st = stage(); if (!st) return {x:0, y:0, w:0, h:0};
  const sr = st.getBoundingClientRect(), r = el.getBoundingClientRect();
  const k = sr.width ? sr.width / 1600 : 1;
  return {x:R1((r.left - sr.left) / k), y:R1((r.top - sr.top) / k), w:R1(r.width / k), h:R1(r.height / k)};
}

/* ---------- addressing ---------- */
function find(eid){
  const root = cur(); if (!root || !eid) return null;
  const all = root.querySelectorAll('[data-eid]');
  for (let i = 0; i < all.length; i++) if (all[i].getAttribute('data-eid') === eid) return all[i];
  return null;
}
function hit(node){
  const root = cur();
  if (!root || !node || !node.closest) return null;
  if (node.closest('#hp-edit')) return null;
  const el = node.closest('[data-eid]');
  return el && el !== root && root.contains(el) ? el : null;
}
function sibsOf(el){
  const p = el.parentNode;
  if (!p || !p.children) return [];
  // shell appends .src/.stamp to the slide root and the LLM never stamps <script>/<style>:
  // element siblings the server can address are exactly the stamped ones.
  return Array.prototype.filter.call(p.children, n => n.hasAttribute && n.hasAttribute('data-eid'));
}
const infoOf = eid => locks[eid] || null;

function canText(el){
  if (!el) return false;
  const L = infoOf(el.getAttribute('data-eid'));
  if (L && L.editable_text === false) return false;
  if (el.children.length) return false;                       // edit.py: has-children (never offer it)
  if (el.hasAttribute('data-icon')) return false;              // the runtime owns that text
  return VOID.indexOf(' ' + el.tagName.toLowerCase() + ' ') < 0;
}
function canDelete(el){
  if (!el) return false;
  const L = infoOf(el.getAttribute('data-eid'));
  if (L && L.deletable === false) return false;
  const root = cur();
  if (el.parentNode === root && sibsOf(el).length < 2) return false;  // edit.py: empty-slide
  return true;
}
const norm = s => String(s == null ? '' : s).replace(/ /g, ' ').replace(/\s+/g, ' ').trim();

/* ---------- selection ---------- */
function select(el, quiet){
  if (editing && editing.el !== el) stopText(true);
  selEl = el || null;
  selEid = el ? el.getAttribute('data-eid') : null;
  hoverEl = null;
  lastRect = null;
  paint();
  if (!quiet) sendSelect();
}
function sendSelect(){
  clearTimeout(postT);
  if (!selEl || !document.contains(selEl)) { lastRect = null; send({event:'edit-select', eid:null}); return; }
  const L = infoOf(selEid) || {};
  lastRect = stageRect(selEl);
  send({
    event:'edit-select', eid:selEid, tag:selEl.tagName.toLowerCase(),
    classes:(selEl.getAttribute('class') || '').split(/\s+/).filter(Boolean),
    text:norm(selEl.textContent).slice(0, MAX_TEXT), rect:lastRect,
    canText:canText(selEl), canDelete:canDelete(selEl), locks:(L.locks || []).slice()
  });
}

/* ---------- chrome ---------- */
function buildLayer(){
  if (layer) return;
  layer = document.createElement('div');
  layer.id = 'hp-edit';
  layer.setAttribute('aria-hidden', 'true');
  const mk = cls => { const n = document.createElement('div'); n.className = cls; layer.appendChild(n); return n; };
  hoverBox = mk('hover');
  dropBox = mk('drop');
  ring = mk('ring');
  delBtn = document.createElement('button');
  delBtn.type = 'button'; delBtn.className = 'del'; delBtn.textContent = '×';
  delBtn.title = 'Delete element'; delBtn.setAttribute('aria-label', 'Delete element');
  delBtn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); doDelete(); });
  layer.appendChild(delBtn);
  buildHandles();
  document.body.appendChild(layer);
}
function place(node, r, pad){
  if (!r || (!r.width && !r.height)) { node.style.display = 'none'; return; }
  node.style.display = 'block';
  node.style.left = (r.left - pad) + 'px';
  node.style.top = (r.top - pad) + 'px';
  node.style.width = (r.width + pad * 2) + 'px';
  node.style.height = (r.height + pad * 2) + 'px';
}
function dropGeom(){
  const d = drag.drop;
  if (!d || !d.rect) return null;
  const T = 3, r = d.rect;
  if (d.row) return {left:(d.after ? r.right + 2 : r.left - T - 2), top:r.top, width:T, height:r.height};
  return {left:r.left, top:(d.after ? r.bottom + 2 : r.top - T - 2), width:r.width, height:T};
}
function paint(){
  if (!layer) return;
  if (selEl && !document.contains(selEl)) { selEl = null; selEid = null; lastRect = null; send({event:'edit-select', eid:null}); }
  if (hoverEl && !document.contains(hoverEl)) hoverEl = null;

  const dragging = !!(drag && drag.started);
  place(ring, selEl ? selEl.getBoundingClientRect() : null, 1);
  ring.classList.toggle('drag', dragging);
  ring.classList.toggle('locked', !!(selEl && !canText(selEl) && !canDelete(selEl)));
  place(hoverBox, (hoverEl && hoverEl !== selEl && !dragging && !editing) ? hoverEl.getBoundingClientRect() : null, 0);
  place(dropBox, dragging ? dropGeom() : null, 0);

  if (selEl && !dragging && !editing && canDelete(selEl)) {
    const r = selEl.getBoundingClientRect();
    let y = r.top - 32; if (y < 4) y = r.top + 6;
    delBtn.style.display = 'block';
    delBtn.style.left = Math.min(Math.max(r.right - 13, 4), innerWidth - 30) + 'px';
    delBtn.style.top = Math.min(Math.max(y, 4), innerHeight - 30) + 'px';
  } else delBtn.style.display = 'none';
  placeHandles();

  // the toolbar lives in the parent, so a rect that moved (step, resize, rescale) has to be resent
  if (selEl && lastRect) {
    const r = stageRect(selEl);
    if (Math.abs(r.x - lastRect.x) > .5 || Math.abs(r.y - lastRect.y) > .5 ||
        Math.abs(r.w - lastRect.w) > .5 || Math.abs(r.h - lastRect.h) > .5) {
      lastRect = r;
      clearTimeout(postT);
      postT = setTimeout(() => { if (on && selEl) sendSelect(); }, 140);
    }
  }
}
function loop(){ if (!on) return; paint(); raf = requestAnimationFrame(loop); }

/* ---------- text editing ----------
   plaintext-only where it exists, paste intercepted, Enter commits: what the server gets is
   always the plain single line the user sees (edit.py escapes it — never send markup). */
function startText(el){
  if (!el || !canText(el)) return;
  if (editing && editing.el === el) return;
  if (el !== selEl) select(el);
  else if (editing) stopText(true);
  editing = {el, eid:el.getAttribute('data-eid'), orig:el.textContent};
  el.contentEditable = 'plaintext-only';
  if (el.contentEditable !== 'plaintext-only') el.contentEditable = 'true';
  el.spellcheck = false;
  el.addEventListener('keydown', onTextKey, true);
  el.addEventListener('paste', onPaste, true);
  el.addEventListener('input', onTextInput);
  el.addEventListener('blur', onTextBlur);
  document.body.classList.add('hp-ed-text');
  try { el.focus({preventScroll:true}); } catch(e){ el.focus(); }
  try {
    const rng = document.createRange(); rng.selectNodeContents(el);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(rng);
  } catch(e){}
  paint();
}
function stopText(commit){
  if (!editing) return;
  const el = editing.el, eid = editing.eid, orig = editing.orig;
  editing = null;
  clearTimeout(dirtyT);
  el.removeEventListener('keydown', onTextKey, true);
  el.removeEventListener('paste', onPaste, true);
  el.removeEventListener('input', onTextInput);
  el.removeEventListener('blur', onTextBlur);
  el.removeAttribute('contenteditable');
  el.removeAttribute('spellcheck');
  document.body.classList.remove('hp-ed-text');
  const txt = norm(el.textContent).slice(0, MAX_TEXT);
  if (!commit || txt === norm(orig)) { el.textContent = orig; }  // revert / no-op: leave the markup as authored
  else { el.textContent = txt; send({event:'edit-op', op:{op:'set_text', eid, text:txt}}); }
  paint();
}
function onTextKey(e){
  e.stopPropagation();  // the deck must never navigate on a keystroke meant for the caret
  if (e.key === 'Escape') { e.preventDefault(); stopText(false); }
  else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); stopText(true); }
  else if (e.key === 'Tab') { e.preventDefault(); stopText(true); }
}
function onPaste(e){
  e.preventDefault(); e.stopPropagation();
  const t = (e.clipboardData && e.clipboardData.getData('text/plain')) || '';
  try { document.execCommand('insertText', false, t.replace(/\s+/g, ' ')); } catch(err){}
}
function onTextInput(){
  if (!editing) return;
  const eid = editing.eid, el = editing.el;
  clearTimeout(dirtyT);
  dirtyT = setTimeout(() => send({event:'edit-dirty', eid, text:norm(el.textContent).slice(0, MAX_TEXT)}), 120);
}
function onTextBlur(){ stopText(true); }

/* ---------- delete ---------- */
function doDelete(){
  if (!selEl || !canDelete(selEl)) return;
  const eid = selEid;
  select(null, true);
  send({event:'edit-op', op:{op:'delete', eid}});
  send({event:'edit-select', eid:null});
}

/* ---------- resize ----------
   Eight handles on the selection. A drag writes `width`/`height` (and `flex-basis`, when the element
   is a flex child that would otherwise ignore width) in **stage pixels**, never a coordinate: the
   1600x900 stage is transform-scaled, so screen pixels are meaningless and `position`/`transform` are
   refused by edit.py on purpose. Resizing therefore works *with* the layout it was designed into —
   the element grows, its siblings reflow, and the slide is still the slide.

   Preview is local and optimistic (the element's own inline style) so the drag feels direct; the
   committed value goes to the parent as a set_style op, which is the only thing that persists. If the
   server refuses it, the parent re-renders and the preview disappears with it. */
const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
const MIN_PX = 24;          // below this an element cannot be grabbed again
let handleEls = [];
let resize = null;          // {el, eid, dir, x0, y0, w0, h0, k, flexChild, w, h}

function buildHandles(){
  HANDLES.forEach(dir => {
    const n = document.createElement('div');
    n.className = 'hnd h-' + dir;
    n.dataset.dir = dir;
    n.addEventListener('pointerdown', e => startResize(e, dir), true);
    layer.appendChild(n);
    handleEls.push(n);
  });
}

/* Can this element be resized at all? Text spans and runtime-owned slots cannot: growing a <span>
   that only wraps a word does nothing the user asked for, and the runtime rewrites [data-icon]. */
function canResize(el){
  if (!el || !on) return false;
  const L = infoOf(el.getAttribute('data-eid'));
  if (L && L.deletable === false && L.editable_text === false) return false;
  if (el.hasAttribute('data-icon')) return false;
  const d = getComputedStyle(el).display;
  return d !== 'inline';                        // inline boxes ignore width/height entirely
}

/* stage px per screen px — the stage is CSS-scaled to the viewport and the ratio is never 1. */
function stageScale(){
  const st = stage();
  if (!st) return 1;
  const r = st.getBoundingClientRect();
  return r.width ? 1600 / r.width : 1;
}

function placeHandles(){
  const show = selEl && canResize(selEl) && !(drag && drag.started) && !editing && !resize;
  if (!show && !resize) { handleEls.forEach(n => { n.style.display = 'none'; }); return; }
  const r = (resize ? resize.el : selEl).getBoundingClientRect();
  handleEls.forEach(n => {
    const d = n.dataset.dir;
    const x = d.includes('w') ? r.left : d.includes('e') ? r.right : r.left + r.width / 2;
    const y = d.includes('n') ? r.top : d.includes('s') ? r.bottom : r.top + r.height / 2;
    n.style.display = 'block';
    n.style.left = (x - 5) + 'px';
    n.style.top = (y - 5) + 'px';
  });
}

function startResize(e, dir){
  if (e.button || !selEl || !canResize(selEl)) return;
  e.preventDefault(); e.stopPropagation();
  if (editing) stopText(true);
  const el = selEl;
  const r = el.getBoundingClientRect();
  const k = stageScale();
  const parent = el.parentNode;
  const pd = parent && parent.nodeType === 1 ? getComputedStyle(parent).display : '';
  resize = {
    el, eid:el.getAttribute('data-eid'), dir, x0:e.clientX, y0:e.clientY,
    w0:r.width * k, h0:r.height * k, k,
    // In a flex row a sibling with flex-grow eats the space, so width alone appears to do nothing.
    // Writing flex-basis too is what makes the drag mean what it looks like it means.
    flexChild: (pd === 'flex' || pd === 'inline-flex') && getComputedStyle(el).flexGrow !== '0',
    // An <img> is capped by `.figure img{max-width:80%;max-height:80%}` and by its own natural size, so a
    // drag that only wrote width/height stopped at the cap. Images also keep their aspect ratio: the
    // drag sets the width and the height follows.
    img: el.tagName === 'IMG', ratio: r.height ? r.width / r.height : 1,
    w:null, h:null,
  };
  document.body.classList.add('hp-ed-resizing');
  layer.classList.add('resizing');
  try { e.target.setPointerCapture(e.pointerId); } catch(err){}
}

function moveResize(e){
  const d = resize.dir;
  const dx = (e.clientX - resize.x0) * resize.k;
  const dy = (e.clientY - resize.y0) * resize.k;
  if (d.includes('e')) resize.w = Math.max(MIN_PX, Math.round(resize.w0 + dx));
  if (d.includes('w')) resize.w = Math.max(MIN_PX, Math.round(resize.w0 - dx));
  if (d.includes('s')) resize.h = Math.max(MIN_PX, Math.round(resize.h0 + dy));
  if (d.includes('n')) resize.h = Math.max(MIN_PX, Math.round(resize.h0 - dy));
  if (resize.img) {
    if (resize.w == null) resize.w = Math.max(MIN_PX, Math.round(resize.h * resize.ratio));
    resize.h = null;
  }
  const st = resize.el.style;
  if (resize.img) { st.maxWidth = 'none'; st.maxHeight = 'none'; st.height = 'auto'; }
  if (resize.w != null) { st.width = resize.w + 'px'; if (resize.flexChild) st.flexBasis = resize.w + 'px'; }
  if (resize.h != null) st.height = resize.h + 'px';
  e.preventDefault();
}

function endResize(){
  const r = resize;
  resize = null;
  document.body.classList.remove('hp-ed-resizing');
  layer.classList.remove('resizing');
  if (!r || (r.w == null && r.h == null)) { paint(); return; }
  const style = {};
  if (r.w != null && Math.abs(r.w - r.w0) >= 1) {
    style.width = r.w + 'px';
    if (r.flexChild) style['flex-basis'] = r.w + 'px';
  }
  if (r.h != null && Math.abs(r.h - r.h0) >= 1) style.height = r.h + 'px';
  if (r.img && style.width) Object.assign(style, {height:'auto', 'max-width':'none', 'max-height':'none'});
  if (Object.keys(style).length) send({event:'edit-op', op:{op:'set_style', eid:r.eid, style}});
  paint();
}

/* ---------- pointer: select, drag to reorder, double-click to type ---------- */
function inEdit(node){ return !!(editing && node && editing.el.contains(node)); }
function guard(e){
  if (inEdit(e.target)) return;                                   // caret placement inside the field
  if (e.target && e.target.closest && e.target.closest('#hp-edit')) return;
  e.preventDefault(); e.stopPropagation();                        // slide buttons/tabs stay quiet while editing
}
function onDown(e){
  if (e.button) return;
  if (resize) return;                                             // a handle already captured this press
  if (inEdit(e.target)) return;
  guard(e);
  const deep = hit(e.target);
  if (editing) stopText(true);
  if (!deep) { select(null); return; }
  // Pressing inside the current selection drags *it* (so a container can be dragged by any of
  // its content); releasing without moving drills down to the deepest element instead.
  const keep = !!(selEl && selEl !== deep && selEl.contains(deep));
  const el = keep ? selEl : deep;
  if (!keep && el !== selEl) select(el);
  drag = {el, eid:el.getAttribute('data-eid'), x0:e.clientX, y0:e.clientY, started:false, idx:null, drill:keep ? deep : null};
}
/* Where the pointer lands in reading order, as a 0-based position among the element siblings
   counted *without* the dragged one — exactly what edit.py's ReorderOp.index means.
   Rows, columns and grids all fall out of the same rule: skip whole rows above the pointer,
   then compare across the row (or down the column when a sibling is alone on its line). */
function dropAt(x, y){
  const others = drag.sibs.filter(n => n !== drag.el);
  const rs = others.map(n => n.getBoundingClientRect());
  const row = rs.map((r, i) => rs.some((o, j) => j !== i &&
    Math.min(o.bottom, r.bottom) - Math.max(o.top, r.top) > Math.min(o.height, r.height) * .5));
  let i = 0;
  for (; i < rs.length; i++) {
    const r = rs[i];
    if (y < r.top - 1) break;
    if (y > r.bottom + 1) continue;
    if (row[i] ? x < r.left + r.width / 2 : y < r.top + r.height / 2) break;
  }
  const k = Math.min(i, rs.length - 1);
  return {idx:i, rect:rs[k], row:row[k], after:i >= rs.length};
}
function onMove(e){
  if (!on) return;
  if (resize) { moveResize(e); return; }
  if (!drag) { hoverEl = editing ? null : hit(e.target); return; }
  if (!drag.started) {
    if (Math.abs(e.clientX - drag.x0) + Math.abs(e.clientY - drag.y0) < 6) return;
    const sibs = sibsOf(drag.el);
    if (sibs.length < 2) { drag = null; return; }   // edit.py: no-siblings
    drag.sibs = sibs; drag.from = sibs.indexOf(drag.el); drag.started = true;
    document.body.classList.add('hp-ed-dragging');
  }
  drag.drop = dropAt(e.clientX, e.clientY);
  drag.idx = drag.drop.idx;
  e.preventDefault();
}
function onUp(){
  if (resize) { endResize(); return; }
  if (!drag) return;
  const d = drag; drag = null;
  document.body.classList.remove('hp-ed-dragging');
  if (d.started) { if (d.idx != null && d.idx !== d.from) send({event:'edit-op', op:{op:'reorder', eid:d.eid, index:d.idx}}); }
  else if (d.drill) select(d.drill);
  paint();
}
function onDbl(e){
  guard(e);
  if (inEdit(e.target)) return;
  const el = hit(e.target);
  if (el && canText(el)) startText(el);
}
function onSlideChange(){ if (on) select(null); }

/* ---------- keys (called from shell.js onKey before anything else) ---------- */
function key(e){
  if (!on) return false;
  if (editing) return true;                         // the caret owns every key
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  if (e.key === 'Escape' && selEl) { select(null); e.preventDefault(); return true; }
  if (!selEl) return false;
  if ((e.key === 'Enter' || e.key === 'F2') && canText(selEl)) { startText(selEl); e.preventDefault(); return true; }
  if (e.key === 'Delete' && canDelete(selEl)) { doDelete(); e.preventDefault(); return true; }
  return false;
}

/* ---------- on / off ---------- */
const STAGE_EVENTS = [['pointerdown', onDown], ['click', guard], ['mousedown', guard], ['mouseup', guard], ['dblclick', onDbl]];
function enable(){
  if (on) return;
  const st = stage(); if (!st) return;
  on = true; DECK.editing = true;
  buildLayer();
  document.body.classList.add('hp-editing');
  STAGE_EVENTS.forEach(([k, fn]) => st.addEventListener(k, fn, true));
  window.addEventListener('pointermove', onMove, true);
  window.addEventListener('pointerup', onUp, true);
  window.addEventListener('pointercancel', onUp, true);
  document.addEventListener('deck:change', onSlideChange);
  raf = requestAnimationFrame(loop);
  send({event:'edit-ready'});
}
function disable(){
  if (!on) return;
  stopText(true);
  on = false; DECK.editing = false;
  const st = stage();
  if (st) STAGE_EVENTS.forEach(([k, fn]) => st.removeEventListener(k, fn, true));
  window.removeEventListener('pointermove', onMove, true);
  window.removeEventListener('pointerup', onUp, true);
  window.removeEventListener('pointercancel', onUp, true);
  document.removeEventListener('deck:change', onSlideChange);
  cancelAnimationFrame(raf); raf = 0;
  clearTimeout(postT); clearTimeout(dirtyT);
  document.body.classList.remove('hp-editing', 'hp-ed-dragging', 'hp-ed-text');
  if (layer && layer.parentNode) layer.parentNode.removeChild(layer);
  layer = ring = hoverBox = dropBox = delBtn = null;
  selEl = selEid = hoverEl = null; drag = null; lastRect = null;
}

function msg(d){
  if (d.cmd === 'locks') { locks = (d.map && typeof d.map === 'object') ? d.map : {}; if (on) { paint(); if (selEl) sendSelect(); } return; }
  if (d.cmd === 'edit') { d.on ? enable() : disable(); return; }
  if (!on) return;
  if (d.cmd === 'select') select(d.eid ? find(d.eid) : null);
}

DECK.editor = {msg, key, active: () => on};
})();
