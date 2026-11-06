import json
import pytest
from visual_source_edits import reconstruct, allowed_lists

SOURCE = {'index.html': '<div id="reservations" role="table"></div><form id="booking"></form>', 'app.js': 'window.working=true;', 'styles.css': 'body{color:#111}'}


def plan(ids=(), css=()):
    return json.dumps({'summary': 'Repair fictional list semantics', 'list_ids': list(ids), 'css_lines': list(css)})


def test_quotes_do_not_affect_model_selected_container_identity():
    assert allowed_lists(SOURCE) == ['reservations']
    assert allowed_lists({**SOURCE, 'index.html': SOURCE['index.html'].replace('"', "'")}) == ['reservations']


def test_compiler_preserves_every_original_application_and_css_byte():
    result = reconstruct(plan(['reservations'], ['.button { color: #111; }']), SOURCE)
    assert result['files']['app.js'].startswith(SOURCE['app.js'] + '\n')
    assert result['files']['styles.css'].startswith(SOURCE['styles.css'] + '\n')
    assert 'index.html' not in result['files']
    assert SOURCE['app.js'] == 'window.working=true;'


@pytest.mark.parametrize('ids,css', [(['booking'], []), (['missing'], []), (['reservations'] * 2, []), ([None], []), ([], ['x'] * 41), ([], ['bad\nline']), ([], ['x' * 501])])
def test_out_of_scope_or_unbounded_repairs_are_rejected(ids, css):
    with pytest.raises(ValueError):
        reconstruct(plan(ids, css), SOURCE)


def test_ambiguous_ids_and_native_list_tags_are_not_eligible():
    assert allowed_lists({'index.html': '<div id="x" role="list"></div><div id="x" role="list"></div><ul id="y" role="list"></ul>'}) == []
    assert allowed_lists({'index.html': '<form id="x"></form><div id="x" role="list"></div>'}) == []


def test_passing_review_can_preserve_existing_source():
    assert reconstruct(plan(), SOURCE)['files'] == {'styles.css': SOURCE['styles.css']}


def test_structured_color_repair_compiles_punctuation_and_preserves_source():
    patch = {'summary': 'Repair actual contrast', 'list_ids': [], 'css_rules': [
        {'selector': '.reservation-date', 'property': 'color', 'value': '#173c34'},
        {'selector': '.reservation-date', 'property': 'opacity', 'value': '1'}]}
    css = reconstruct(json.dumps(patch), SOURCE)['files']['styles.css']
    assert css.startswith(SOURCE['styles.css'])
    assert '.reservation-date {color:#173c34 !important;}' in css
    assert '.reservation-date {opacity:1 !important;}' in css


@pytest.mark.parametrize('selector,prop,value', [
    ('.reservation-date', 'color', '#173c34 " opacity: 1 "'),
    ('.reservation-date', 'color', '#173c34; display:none'),
    ('form', 'display', 'none'),
    ('form', 'opacity', '0'),
    ('.reservation-date', 'font-size', '0'),
    ('body', 'background-image', 'url(https://example.com)'),
    ('body{display:none}', 'color', '#111')])
def test_structured_repair_rejects_malformed_css_and_hidden_controls(selector, prop, value):
    patch = {'summary': 'Rejected repair', 'list_ids': [], 'css_rules': [
        {'selector': selector, 'property': prop, 'value': value}]}
    with pytest.raises(ValueError):
        reconstruct(json.dumps(patch), SOURCE)
