"""A curated accessibility pass, run in-page next to the DOM check.

Why not axe-core
----------------
`axe.min.js` is ~550 KB of minified third-party JavaScript (MPL-2.0). The Python Playwright binding has no
`@axe-core/playwright`, so using it means vendoring that blob into this repo and keeping it current — and
this project has no vendor directory, no npm dependency on the backend side, and an explicit rule that a
deck ships with nothing external in it. Against that cost, only a handful of axe's ~100 rules say anything
about a 1600x900 slide stage: the rest assume document semantics (landmarks, heading order, page-has-heading,
html-has-lang, region) and would be pure noise on a `<section class="slide">`. Worse, axe's own
`color-contrast` rule returns *incomplete* precisely where slide contrast actually fails — text on a
background image — which is the case `qa/pixels.py` handles by sampling the rendered pixels.

So the four rule families that do apply are implemented here directly, keeping axe's rule ids so the
findings read the same and axe can be dropped in later if the trade-off changes. Coverage is a floor, not a
certificate: automated accessibility testing is widely estimated to catch only 30-40% of real issues, and
these rules are a subset of that. Everything reports as `warn` — none of them is reliable enough on
generated slide markup to block a version on its own.

Rules: image-alt, button-name, aria-valid-attr, aria-valid-attr-value, aria-required-attr, duplicate-id.
Deliberately excluded: aria-hidden-focus (the runtime keeps closed overlays `aria-hidden` with their buttons
still in the DOM, so it fires on every slide that has an overlay).
"""
from __future__ import annotations

A11Y_CHECK_JS = r"""
() => {
  const root = document.querySelector('.slide.on');
  if (!root) return {findings: []};
  const out = [];
  const chrome = el => el.closest('.stamp,.src,.nav,.hud');  // runtime chrome is not the slide's markup
  const label = el => { let s = el.tagName.toLowerCase(); if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.'); const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30); return t ? `${s} "${t}"` : s; };
  const q = sel => [...root.querySelectorAll(sel)].filter(el => !chrome(el));
  const add = (rule, items, how) => { if (!items.length) return;
    out.push({severity: 'warn', code: 'a11y-' + rule,
              message: `[${rule}] ${items.length} issue(s): ${items.slice(0, 3).join('; ')} — ${how}`}); };

  // image-alt: a missing alt attribute is undecided markup. alt="" is a valid "decorative" statement and passes.
  add('image-alt',
      q('img').filter(el => !el.hasAttribute('alt') && !el.classList.contains('bg-img'))
              .concat(q('[role="img"]').filter(el => !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby')))
              .map(label),
      'add alt="..." describing it, or alt="" if it is decorative');

  // button-name: an interactive control a screen reader cannot announce.
  add('button-name',
      q('button,[role="button"]').filter(el => !(el.innerText || '').trim() && !el.getAttribute('aria-label') &&
          !el.getAttribute('aria-labelledby') && !el.getAttribute('title') &&
          ![...el.querySelectorAll('img[alt]')].some(i => i.getAttribute('alt').trim())).map(label),
      'give it visible text, aria-label or title');

  // aria-valid-attr / aria-valid-attr-value / aria-required-attr
  const VALID = new Set(['aria-activedescendant','aria-atomic','aria-autocomplete','aria-busy','aria-checked','aria-colcount','aria-colindex','aria-colspan','aria-controls','aria-current','aria-describedby','aria-description','aria-details','aria-disabled','aria-errormessage','aria-expanded','aria-flowto','aria-haspopup','aria-hidden','aria-invalid','aria-keyshortcuts','aria-label','aria-labelledby','aria-level','aria-live','aria-modal','aria-multiline','aria-multiselectable','aria-orientation','aria-owns','aria-placeholder','aria-posinset','aria-pressed','aria-readonly','aria-relevant','aria-required','aria-roledescription','aria-rowcount','aria-rowindex','aria-rowspan','aria-selected','aria-setsize','aria-sort','aria-valuemax','aria-valuemin','aria-valuenow','aria-valuetext']);
  const BOOL = {'aria-atomic':1,'aria-busy':1,'aria-disabled':1,'aria-expanded':1,'aria-hidden':1,'aria-modal':1,'aria-multiline':1,'aria-multiselectable':1,'aria-readonly':1,'aria-required':1,'aria-selected':1};
  const TRI = {'aria-checked':1,'aria-pressed':1};
  const IDREF = {'aria-labelledby':1,'aria-describedby':1,'aria-controls':1,'aria-owns':1,'aria-details':1,'aria-flowto':1,'aria-activedescendant':1};
  const REQUIRED = {checkbox:['aria-checked'], switch:['aria-checked'], radio:['aria-checked'],
                    combobox:['aria-expanded'], slider:['aria-valuenow'], scrollbar:['aria-valuenow'],
                    option:['aria-selected'], tab:['aria-selected'], heading:['aria-level']};
  const badAttr = [], badValue = [], missing = [];
  for (const el of q('*')) {
    for (const a of el.attributes) {
      const n = a.name.toLowerCase();
      if (!n.startsWith('aria-')) continue;
      if (!VALID.has(n)) { badAttr.push(`${label(el)} has ${n}`); continue; }
      const v = (a.value || '').trim();
      if (BOOL[n] && !['true','false'].includes(v)) badValue.push(`${label(el)} ${n}="${v}"`);
      else if (TRI[n] && !['true','false','mixed'].includes(v)) badValue.push(`${label(el)} ${n}="${v}"`);
      else if (IDREF[n] && v) {
        const dead = v.split(/\s+/).filter(id => id && !document.getElementById(id));
        if (dead.length) badValue.push(`${label(el)} ${n} points at missing id ${dead.join(', ')}`);
      }
    }
    const role = (el.getAttribute('role') || '').trim().toLowerCase();
    for (const need of (REQUIRED[role] || [])) if (!el.hasAttribute(need)) missing.push(`${label(el)} role="${role}" without ${need}`);
  }
  add('aria-valid-attr', badAttr, 'not an ARIA attribute — check the spelling');
  add('aria-valid-attr-value', badValue, 'use the values the attribute allows, and point idrefs at elements that exist');
  add('aria-required-attr', missing, 'a role carries the state it promises');

  // duplicate-id: ids the slide defines twice, or that collide with the deck runtime's own ids.
  const counts = new Map();
  for (const el of document.querySelectorAll('[id]')) counts.set(el.id, (counts.get(el.id) || 0) + 1);
  const dupes = [], seenId = new Set();
  for (const el of q('[id]')) {
    const id = el.id;
    if (!id || seenId.has(id)) continue;
    seenId.add(id);
    if (counts.get(id) > 1) dupes.push(`${id} (${label(el)})`);
  }
  add('duplicate-id', dupes, 'ids must be unique across the whole deck page — scope them with the slide id');
  return {findings: out};
}
"""
