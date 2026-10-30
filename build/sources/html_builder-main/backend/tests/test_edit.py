import pytest

from app.edit import (
    EID_ATTR,
    DeleteOp,
    EditRequest,
    ReorderOp,
    SetStyleOp,
    SetTextOp,
    apply_ops,
    ensure_ids,
    outline,
    parse_ops,
    script_hooks,
    strip_ids,
)
from app.edit import _parse, _serialize
from app.skillpack import examples
from app.spec import parse_spec, scope_css

RAW_CSS = ".card{padding:10px}@keyframes pop{from{opacity:0}to{opacity:1}}.card.appear{animation:pop .3s}"
RAW = """<meta>{"pattern":"cards","title":"T","steps":3}</meta>
<html>
<div class="eyebrow">Eyebrow</div>
<h1 class="title">Heading</h1>
<div class="grid">
  <div class="card appear"><h3>One</h3><p>first</p></div>
  <div class="card appear"><h3>Two</h3><p>second</p></div>
  <div class="card appear" data-step="3"><h3>Three</h3><p>third</p></div>
</div>
<div class="stat"><b data-count="42">0</b></div>
</html>
<css>%s</css>
<script>function go(root, step){ H.reveal(root, '.card', step); H.$('.stat', root); }</script>""" % RAW_CSS


@pytest.fixture
def spec():
    s, _ = parse_spec(RAW, "x1")
    return ensure_ids(s)


def eid(spec, **match):
    """First element in the outline matching tag / class / text."""
    for e in outline(spec):
        if "tag" in match and e.tag != match["tag"]:
            continue
        if "cls" in match and match["cls"] not in e.classes:
            continue
        if "text" in match and match["text"] not in e.text:
            continue
        if "attr" in match and match["attr"] not in spec.html:
            continue
        return e.eid
    raise AssertionError(f"no element for {match}")


# ---------------------------------------------------------------- addressing
def test_ensure_ids_is_idempotent_and_reversible(spec):
    again = ensure_ids(spec)
    assert again.html == spec.html
    plain, _ = parse_spec(RAW, "x1")
    assert strip_ids(spec.html) == plain.html
    ids = [e.eid for e in outline(spec)]
    assert len(ids) == len(set(ids)) and all(ids)


def test_existing_ids_survive_new_neighbours():
    s, _ = parse_spec('<html><div data-eid="e1">a</div><div>b</div><div data-eid="keep">c</div></html>', "x")
    out = outline(ensure_ids(s))
    assert [e.eid for e in out] == ["e1", "e2", "keep"]


def test_ids_are_not_stamped_inside_script_or_style():
    s = parse_spec('<html><p>a</p></html>', "x")[0]
    s.html = '<p>a</p><script>var x = "<b>";</script>'
    stamped = ensure_ids(s)
    assert stamped.html.count(EID_ATTR) == 1
    assert apply_ops(stamped, [SetTextOp(eid="e2", text="nope")]).error_code == "unknown-eid"


# ---------------------------------------------------------------- round trip
@pytest.mark.parametrize("ex", examples(), ids=lambda e: e.name)
def test_gold_example_round_trips_unchanged(ex):
    s = ex.spec("gold")
    assert _serialize(_parse(s.html)) == s.html  # parse -> serialize is byte-exact
    assert apply_ops(s, []).spec.html == s.html  # a no-op edit touches nothing
    assert strip_ids(ensure_ids(s).html) == s.html  # stamping ids is fully reversible


# ---------------------------------------------------------------- set_text
def test_set_text_replaces_content(spec):
    r = apply_ops(spec, [SetTextOp(eid=eid(spec, cls="title"), text="New heading")])
    assert r.ok and r.changed
    assert "<h1 class=\"title\"" in r.spec.html and ">New heading</h1>" in r.spec.html
    assert "Heading" not in r.spec.html


def test_set_text_escapes_markup_and_entities(spec):
    nasty = '</div><script>alert("x")</script> & 3 < 5 "quoted" \'q\''
    r = apply_ops(spec, [SetTextOp(eid=eid(spec, cls="eyebrow"), text=nasty)])
    assert r.ok
    assert "<script>" not in r.spec.html and "</div><script" not in r.spec.html
    assert "&lt;/div&gt;&lt;script&gt;" in r.spec.html and "&amp; 3 &lt; 5" in r.spec.html
    # the escaped text parses back to exactly what the user typed, and nothing else moved
    back = _parse(r.spec.html)
    node = next(e for e in back.iter() if e.get(EID_ATTR) == eid(spec, cls="eyebrow"))
    assert node.text == nasty
    assert len(outline(r.spec)) == len(outline(spec))


def test_set_text_refuses_containers_unless_opted_in(spec):
    card = eid(spec, cls="card")
    assert apply_ops(spec, [SetTextOp(eid=card, text="flat")]).error_code == "has-children"
    r = apply_ops(spec, [SetTextOp(eid=card, text="flat", replace_children=True)])
    assert r.ok and "<h3" not in r.spec.html.split("</div>")[0]
    assert r.qa_recommended


def test_set_text_refuses_to_eat_step_driven_children(spec):
    stat = eid(spec, cls="stat")
    assert apply_ops(spec, [SetTextOp(eid=stat, text="x", replace_children=True)]).error_code == "protected-children"


def test_set_text_refuses_void_and_icon_elements():
    s = ensure_ids(parse_spec('<html><img src="asset:a.png"><i data-icon="lock"></i></html>', "x")[0])
    assert apply_ops(s, [SetTextOp(eid="e1", text="x")]).error_code == "void-element"
    assert apply_ops(s, [SetTextOp(eid="e2", text="x")]).error_code == "icon-slot"


def test_longer_text_asks_for_qa_but_shorter_does_not(spec):
    t = eid(spec, cls="title")
    assert not apply_ops(spec, [SetTextOp(eid=t, text="Hi")]).qa_recommended
    assert apply_ops(spec, [SetTextOp(eid=t, text="A far longer heading than the slide was laid out for")]).qa_recommended


# ---------------------------------------------------------------- delete
def test_delete_removes_the_subtree_and_asks_for_qa(spec):
    card = outline(spec)[3]  # first .card
    r = apply_ops(spec, [DeleteOp(eid=card.eid)])
    assert r.ok and r.changed and r.qa_recommended
    assert "One" not in r.spec.html and "Two" in r.spec.html
    assert len(outline(r.spec)) == len(outline(spec)) - 3  # card + h3 + p
    assert "\n  <div class=\"card appear\"" in r.spec.html  # indentation survived


def test_delete_refuses_the_slide_root(spec):
    assert apply_ops(spec, [DeleteOp(eid="root")]).error_code == "root-protected"
    assert apply_ops(spec, [DeleteOp(eid="")]).error_code == "root-protected"
    one = ensure_ids(parse_spec("<html><p>only</p></html>", "x")[0])
    assert apply_ops(one, [DeleteOp(eid="e1")]).error_code == "empty-slide"


def test_delete_refuses_the_last_element_a_script_selects(spec):
    assert apply_ops(spec, [DeleteOp(eid=eid(spec, cls="stat"))]).error_code == "script-ref"
    assert apply_ops(spec, [DeleteOp(eid=eid(spec, cls="grid"))]).error_code == "script-ref"  # holds every .card
    r = apply_ops(spec, [DeleteOp(eid=outline(spec)[3].eid)])  # one of three .card: allowed, flagged
    assert r.ok and any(w.code == "script-ref" for w in r.warnings)


def test_delete_reports_step_engine_dependencies(spec):
    r = apply_ops(spec, [DeleteOp(eid=outline(spec)[3].eid)])
    assert {w.code for w in r.warnings} >= {"step-order"}
    stepped = next(e for e in outline(spec) if "card" in e.classes and "Three" in e.text)
    assert {w.code for w in apply_ops(spec, [DeleteOp(eid=stepped.eid)]).warnings} >= {"step-ref"}


# ---------------------------------------------------------------- reorder
def test_reorder_moves_among_siblings(spec):
    cards = [e for e in outline(spec) if "card" in e.classes]
    r = apply_ops(spec, [ReorderOp(eid=cards[-1].eid, index=0)])
    assert r.ok and r.qa_recommended
    order = [e.text[:5] for e in outline(r.spec) if "card" in e.classes]
    assert order == ["Three", "Onefi", "Twose"]
    assert any(w.code == "step-order" for w in r.warnings)
    assert r.spec.html.count('class="card appear"') == 3  # nothing duplicated or lost
    assert r.spec.html.count('data-step="3"') == 1


def test_reorder_validates_the_target(spec):
    cards = [e for e in outline(spec) if "card" in e.classes]
    assert apply_ops(spec, [ReorderOp(eid=cards[0].eid, index=9)]).error_code == "bad-index"
    assert apply_ops(spec, [ReorderOp(eid=cards[0].eid, index=-1)]).error_code == "bad-index"
    assert apply_ops(spec, [ReorderOp(eid=eid(spec, cls="stat"), index=0)]).ok  # top level has siblings
    lone = ensure_ids(parse_spec("<html><div><p>a</p></div></html>", "x")[0])
    assert apply_ops(lone, [ReorderOp(eid="e2", index=0)]).error_code == "no-siblings"


# ---------------------------------------------------------------- set_style
def test_set_style_writes_inline_and_merges(spec):
    t = eid(spec, cls="title")
    r = apply_ops(spec, [SetStyleOp(eid=t, style={"color": "var(--blue)", "font-size": "58px", "text-align": "center"})])
    assert r.ok and 'style="color:var(--blue);font-size:58px;text-align:center"' in r.spec.html
    r2 = apply_ops(r.spec, [SetStyleOp(eid=t, style={"font-size": "40px", "color": ""})])
    assert 'style="font-size:40px;text-align:center"' in r2.spec.html


def test_set_style_rejects_anything_off_the_allowlist(spec):
    t = eid(spec, cls="title")
    bad = [
        {"position": "fixed"},
        {"z-index": "9999"},
        {"transform": "scale(4)"},
        {"background": "url(http://evil/x.png)"},
        {"background-color": "expression(alert(1))"},
        {"color": "red;position:fixed"},
        {"color": "red !important"},
        {"width": "100px} .other{display:none"},
        {"background": 'var(--a);background-image:url("x")'},
    ]
    for style in bad:
        r = apply_ops(spec, [SetStyleOp(eid=t, style=style)])
        assert not r.ok and r.error_code in ("style-prop", "style-value"), style
        assert r.spec.html == spec.html
    assert apply_ops(spec, [SetStyleOp(eid=t, style={})]).error_code == "empty-style"


def test_cosmetic_styles_do_not_force_qa_but_layout_ones_do(spec):
    t = eid(spec, cls="title")
    assert not apply_ops(spec, [SetStyleOp(eid=t, style={"color": "#123456"})]).qa_recommended
    assert apply_ops(spec, [SetStyleOp(eid=t, style={"padding": "0 24px"})]).qa_recommended


# ---------------------------------------------------------------- atomicity + plumbing
def test_a_failing_op_rolls_the_whole_batch_back(spec):
    ops = [
        SetTextOp(eid=eid(spec, cls="title"), text="Changed"),
        DeleteOp(eid=outline(spec)[3].eid),
        SetStyleOp(eid=eid(spec, cls="eyebrow"), style={"position": "absolute"}),
    ]
    r = apply_ops(spec, ops)
    assert not r.ok and r.failed_index == 2 and r.error_code == "style-prop"
    assert r.spec.html == spec.html and r.spec.css == spec.css and not r.changed
    assert [x.ok for x in r.results] == [True, True, False]
    assert apply_ops(spec, ops[:2]).ok  # the first two are fine on their own


def test_ops_parse_from_the_json_a_browser_sends(spec):
    ops = parse_ops([
        {"op": "set_text", "eid": "e1", "text": "hi"},
        {"op": "set_style", "eid": "e2", "style": {"color": "red"}},
        {"op": "reorder", "eid": "e3", "index": 0},
        {"op": "delete", "eid": "e13"},
    ])
    assert [o.op for o in ops] == ["set_text", "set_style", "reorder", "delete"]
    assert EditRequest(ops=[{"op": "delete", "eid": "e1"}]).ops[0].eid == "e1"
    with pytest.raises(Exception):
        parse_ops([{"op": "drop_table", "eid": "e1"}])


def test_script_hooks_cover_selector_and_helper_use():
    js = "function mount(r){ H.$$('.card .lab', r); H.segmented(H.$('[data-seg]', r)); r.querySelector('#hero'); H.tabs(r); }"
    assert script_hooks(js) >= {".card", ".lab", "[data-seg]", "#hero", "[data-v]", "[data-tab]", "[data-panel]"}
    assert script_hooks("") == set()


def test_outline_describes_what_the_editor_may_touch(spec):
    out = outline(spec)
    top = [e for e in out if e.parent is None]
    assert [e.tag for e in top] == ["div", "h1", "div", "div"]
    assert [e.index for e in top] == [0, 1, 2, 3]
    grid = next(e for e in out if "grid" in e.classes)
    assert grid.has_children and not grid.deletable and any(l.startswith("script:") for l in grid.locks)
    assert next(e for e in out if "eyebrow" in e.classes).deletable


# ---------------------------------------------------------------- css contract
def test_editing_leaves_css_scoping_and_keyframes_intact(spec):
    assert ".s-x1 .card{padding:10px}" in spec.css and "@keyframes pop-s-x1" in spec.css
    r = apply_ops(spec, [
        SetTextOp(eid=eid(spec, cls="title"), text="Shorter"),
        SetStyleOp(eid=eid(spec, cls="title"), style={"font-size": "44px"}),
        DeleteOp(eid=outline(spec)[3].eid),
        ReorderOp(eid=eid(spec, cls="eyebrow"), index=1),
    ])
    assert r.ok
    assert r.spec.css == spec.css == scope_css(RAW_CSS, "x1")  # edits never rewrite CSS
    assert "@keyframes pop-s-x1{from{opacity:0}to{opacity:1}}" in r.spec.css
    assert ".s-x1 .card.appear{animation:pop-s-x1 .3s}" in r.spec.css
    assert "font-size:44px" in r.spec.html and "font-size" not in r.spec.css
    # a second scoping pass over the edited slide's source CSS is still correct
    assert scope_css(RAW_CSS, "x1") == r.spec.css
