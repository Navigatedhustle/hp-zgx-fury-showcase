"""Compile bounded visual repair plans without rewriting working application logic."""
import json
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


def reconstruct(text, source):
    plan = json.loads(text)
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
