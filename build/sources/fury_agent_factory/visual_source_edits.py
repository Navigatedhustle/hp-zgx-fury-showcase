"""Compile bounded visual repair plans without rewriting working application logic."""
import json
import re
from html.parser import HTMLParser


class Containers(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.all_ids = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.all_ids.append(values['id'])
        if tag in ('div', 'section') and values.get('role') in ('list', 'table') and values.get('id'):
            self.ids.append(values['id'])


def allowed_lists(source):
    parsed = Containers(source.get('index.html', ''))
    return sorted(value for value in set(parsed.ids) if parsed.all_ids.count(value) == 1)


CSS_VALUES = ('none', '#173c34', '#111111', '#ffffff', '#f7fafc', '#0b1220', '1', '0', '2', '3', '100%', 'auto', 'relative', 'absolute', 'static', 'wrap', 'anywhere', 'break-word', 'cover', 'center', 'block', 'flex', 'grid', 'inline-block', '1fr', 'minmax(0, 1fr)', 'repeat(auto-fit, minmax(min(100%, 250px), 1fr))', 'var(--fury-artwork-hero)', '400', '500', '600', '700', '14px', '16px', '18px', '20px', '1.5', '0.5rem', '1rem', '1.5rem', '0.5rem 1rem', '1 1 280px', '1 1 300px')


def allowed_style_selectors(source):
    text = '\n'.join(source.values())
    return sorted(set(re.findall(r'[.#][A-Za-z_][A-Za-z0-9_-]*', text)) | {'body', 'main', 'nav', 'header', 'form', 'img', 'section', 'article'})


CSS_PROPERTIES = ('color', 'opacity', 'background-color', 'background-image', 'border-color', 'outline-color', 'font-size', 'font-weight', 'line-height', 'min-width', 'max-width', 'width', 'min-height', 'height', 'padding', 'gap', 'flex', 'flex-wrap', 'overflow-wrap', 'word-break', 'grid-template-columns', 'position', 'inset', 'z-index', 'object-fit', 'object-position', 'display')


def structured_css(rules):
    if not isinstance(rules, list) or len(rules) > 40:
        raise ValueError('Expected up to 40 structured CSS declarations')
    lines = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'selector', 'property', 'value'}:
            raise ValueError('CSS declaration needs selector, property and value')
        selector, prop, value = rule['selector'], rule['property'], rule['value']
        if (not isinstance(selector, str) or not 1 <= len(selector) <= 180
                or not re.fullmatch(r"[a-zA-Z0-9_#.,:>+~*()\[\]=\"' -]+", selector)
                or prop not in CSS_PROPERTIES or not isinstance(value, str)
                or not 1 <= len(value) <= 160 or not re.fullmatch(r'[a-zA-Z0-9#%().,/ _+!-]+', value)
                or 'url(' in value.lower() or '!important' in value.lower()):
            raise ValueError('Invalid bounded CSS declaration: '+repr(rule)+'. Use a plain element selector and plain value; no media query or CSS punctuation.')
        if prop == 'display' and value == 'none':
            if selector != '.hero-fallback':
                raise ValueError('Visual repair cannot hide application controls or content')
            selector = ':root[style*="--fury-artwork-hero"] .hero-fallback'
        if (prop == 'opacity' and value != '1') or (prop in ('font-size', 'width', 'height', 'max-width') and value == '0'):
            raise ValueError('Visual repair cannot make text or controls invisible')
        lines.append(selector + ' {' + prop + ':' + value + ' !important;}')
    return lines


def reconstruct(text, source):
    plan = json.loads(text)
    if isinstance(plan, dict) and 'css_rules' in plan:
        if set(plan) != {'summary', 'list_ids', 'css_rules'}:
            raise ValueError('Expected summary, list_ids and css_rules')
        plan = {**plan, 'css_lines': structured_css(plan['css_rules'])}
        del plan['css_rules']
    if (not isinstance(plan, dict) or set(plan) != {'summary', 'list_ids', 'css_lines'}
            or not isinstance(plan['summary'], str) or len(plan['summary']) > 400
            or not isinstance(plan['list_ids'], list) or len(plan['list_ids']) > 8
            or any(not isinstance(value, str) or value not in allowed_lists(source) for value in plan['list_ids'])
            or len(set(plan['list_ids'])) != len(plan['list_ids'])
            or not isinstance(plan['css_lines'], list) or len(plan['css_lines']) > 40
            or any(not isinstance(line, str) or '\n' in line or '\r' in line or len(line) > 500 for line in plan['css_lines'])):
        raise ValueError('Expected a bounded plan using existing generic list containers and up to 40 CSS override lines')
    files = {}
    if plan['list_ids']:
        if 'app.js' not in source:
            raise ValueError('No owned application script to extend')
        ids = json.dumps(plan['list_ids']).replace('</', '<\\/')
        # Preserve nodes, text, IDs, listeners, network calls and rendering functions.
        # Child-list observation covers the actual renderer's async empty/populated states.
        extension = '''
;(() => {
  const ids = LIST_IDS;
  const repair = () => {
    for (const id of ids) {
      const container = document.getElementById(id);
      if (!container) continue;
      container.setAttribute('role', 'list');
      for (const item of container.children) item.setAttribute('role', 'listitem');
    }
  };
  repair();
  new MutationObserver(repair).observe(document.body, {childList:true, subtree:true});
})();
'''.replace('LIST_IDS', ids)
        files['app.js'] = source['app.js'] + '\n/* Model-selected visual accessibility repair plan. */\n' + extension
    if plan['css_lines']:
        if 'styles.css' not in source:
            raise ValueError('No owned stylesheet to extend')
        lines = [line.replace('@BS@', chr(92)).replace('@DQ@', chr(34)) for line in plan['css_lines']]
        files['styles.css'] = source['styles.css'] + '\n/* Model-authored visual repair overrides. */\n' + '\n'.join(lines) + '\n'
    if not files:
        name = next((name for name in ('styles.css', 'index.html', 'app.js') if name in source), None)
        if name is None:
            raise ValueError('No owned frontend source to review')
        files[name] = source[name]
    return {'summary': plan['summary'], 'files': files}
