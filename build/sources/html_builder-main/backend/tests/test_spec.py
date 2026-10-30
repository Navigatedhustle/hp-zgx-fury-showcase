import re

import pytest

from app.assemble import DeckInput, DeckSlide, assemble
from app.skillpack import examples
from app.spec import extract_json, parse_spec, scope_css, to_tagged

GOOD = """<think>planning the layout…</think>
<meta>{"pattern":"cards","title":"T","steps":2,"notes":["a","b"],}</meta>
<html><div class="eyebrow">E</div><h1 class="title">T</h1><div class="grid-2"><div class="card appear">1</div><div class="card appear">2</div></div></html>
<css>.card{padding:10px} @media (max-width:10px){ .card{padding:0} } @keyframes pop{from{opacity:0}to{opacity:1}} body{color:red}</css>
<script>function go(root, step){ H.$('.card', root); }</script>"""


def test_parse_good_output_with_think_and_trailing_comma():
    spec, issues = parse_spec(GOOD, "x1")
    assert spec.meta.steps == 2 and spec.meta.notes == ["a", "b"]
    assert ".s-x1 .card{padding:10px}" in spec.css
    assert "@media (max-width:10px){.s-x1 .card{padding:0}}" in spec.css
    assert "@keyframes pop-s-x1{from{opacity:0}to{opacity:1}}" in spec.css  # keyframe names are per slide
    assert ".s-x1{color:red}" in spec.css  # body -> slide root
    assert not [i for i in issues if i.severity == "error"]


def test_missing_html_raises():
    with pytest.raises(ValueError):
        parse_spec("<meta>{}</meta>", "x")


def test_fenced_sections_and_outer_slide_wrapper_are_unwrapped():
    txt = '<meta>```json\n{"title":"a"}\n```</meta><html>```html\n<section class="slide"><p>hi</p></section>\n```</html><css></css><script></script>'
    spec, _ = parse_spec(txt, "y")
    assert spec.html == "<p>hi</p>" and spec.meta.title == "a"


def test_inline_style_and_script_are_moved_or_removed():
    spec, issues = parse_spec('<html><style>.a{color:red}</style><p class="a">x</p><script>alert(1)</script></html>', "z")
    assert "<script" not in spec.html and ".s-z .a{color:red}" in spec.css
    assert {i.code for i in issues} >= {"inline-style", "inline-script", "meta"}


def test_external_resources_flagged_but_links_allowed():
    _, issues = parse_spec('<html><img src="https://x.com/a.png"></html>', "e")
    assert any(i.code == "external" for i in issues)
    _, issues = parse_spec('<html><a href="https://hp.com">hp</a></html>', "e")
    assert not any(i.code == "external" for i in issues)


def test_scope_css_roots_and_already_scoped():
    css = scope_css(":root{--x:1} .slide-root .a, .s-q .b{x:y}", "q")
    assert ".s-q{--x:1}" in css and ".s-q .a,.s-q .b{x:y}" in css


def test_extract_json_lenient():
    assert extract_json('<think>x</think> here: ```json\n{"a": [1,2,],}\n```') == {"a": [1, 2]}


def test_truncated_section_raises_but_absent_section_is_fine():
    with pytest.raises(ValueError, match="css"):  # cut off inside <css>
        parse_spec('<meta>{}</meta>\n<html>\n<p>hi</p>\n</html>\n<css>.a{col', "x")
    with pytest.raises(ValueError, match="script"):
        parse_spec("<meta>{}</meta><html><p>hi</p></html><css></css><script>function go(", "x")
    with pytest.raises(ValueError, match="html"):
        parse_spec("<meta>{}</meta><html><p>hi", "x")
    spec, issues = parse_spec("<meta>{}</meta><html><p>hi</p></html><css>.a{color:red}</css>", "x")
    assert spec.js == "" and spec.css == ".s-x .a{color:red}"
    assert not [i for i in issues if i.severity == "error"]


def test_html_tag_with_attributes_parses_and_last_script_wins():
    txt = ('<meta>{}</meta><html lang="en"><p>hi</p><script>alert(1)</script></html\n>'
           "<css></css><script>function go(root, step){}</script>")
    spec, _ = parse_spec(txt, "x")
    assert spec.html == "<p>hi</p>"
    assert spec.js == "function go(root, step){}"


def test_commas_inside_functional_pseudo_and_attribute_selectors_are_kept():
    assert scope_css(".card:is(.a, .b){color:red}", "x") == ".s-x .card:is(.a, .b){color:red}"
    assert scope_css('[data-k="a,b"]{color:red}', "x") == '.s-x [data-k="a,b"]{color:red}'
    assert scope_css(".a:has(> .b, .c), .d{x:y}", "x") == ".s-x .a:has(> .b, .c),.s-x .d{x:y}"


def test_keyframes_are_namespaced_per_slide():
    css = scope_css(
        "@keyframes pop{from{opacity:0}to{opacity:1}} .a{animation:pop .3s ease-out both}"
        " @-webkit-keyframes pop{from{opacity:0}} .b{animation-name:pop,spin}"
        " @media (min-width:1px){.c{animation:pop 1s}}",
        "x",
    )
    assert "@keyframes pop-s-x{from{opacity:0}to{opacity:1}}" in css
    assert "@-webkit-keyframes pop-s-x{" in css
    assert ".s-x .a{animation:pop-s-x .3s ease-out both}" in css
    assert ".s-x .b{animation-name:pop-s-x,spin}" in css  # undefined names are left alone
    assert "@media (min-width:1px){.s-x .c{animation:pop-s-x 1s}}" in css
    assert not re.search(r"(?<![\w-])pop(?![\w-])", css)  # no bare "pop" survives anywhere
    nested = scope_css("@media print{@keyframes fade{to{opacity:1}}} .d{animation:fade 2s}", "x")
    assert "@keyframes fade-s-x{" in nested and ".s-x .d{animation:fade-s-x 2s}" in nested


def test_brace_inside_css_string_does_not_leak_following_rules():
    css = scope_css('.a::after{content:"{"} .b{color:red}', "x")
    assert css == '.s-x .a::after{content:"{"}\n.s-x .b{color:red}'
    assert scope_css(".a::after{content:'}'} .b{color:red}", "x").count(".s-x ") == 2


def test_font_face_and_import_are_dropped_without_eating_the_next_rule():
    css = scope_css('@import url("x.css"); @font-face{font-family:"F";src:url(f.woff2)} .a{color:red}', "x")
    assert css == ".s-x .a{color:red}"
    assert scope_css('@import "x.css"; .a{color:red}', "x") == ".s-x .a{color:red}"


def test_unbalanced_braces_drop_the_unterminated_rule_only():
    css = scope_css(".a{color:red} .b{color:blue", "x")
    assert css == ".s-x .a{color:red}"
    assert scope_css(".a{color:red}} .b{color:blue}", "x") == ".s-x .a{color:red}\n.s-x .b{color:blue}"


def test_two_slides_with_colliding_css_stay_isolated():
    src = ('<meta>{"title":"t"}</meta><html><div class="card">x</div></html>'
           "<css>.card{animation:pop 1s} @keyframes pop{from{opacity:0}to{opacity:1}}</css>")
    a, _ = parse_spec(src, "a1")
    b, _ = parse_spec(src, "b2")
    html = assemble(DeckInput(title="t", slides=[DeckSlide(id="a1", spec=a), DeckSlide(id="b2", spec=b)]))
    style = html.split('<style id="slide-css">')[1].split("</style>")[0]
    assert "@keyframes pop-s-a1{" in style and "@keyframes pop-s-b2{" in style
    assert "keyframes pop{" not in style
    assert ".s-a1 .card{animation:pop-s-a1 1s}" in style and ".s-b2 .card{animation:pop-s-b2 1s}" in style
    assert style.count(".card{") == 2  # never an unscoped, deck-wide .card rule


def test_all_gold_examples_parse_and_roundtrip():
    exs = examples()
    assert len(exs) >= 12
    for ex in exs:
        spec, issues = parse_spec(ex.output, "g")
        assert not [i for i in issues if i.severity == "error"], ex.name
        again, _ = parse_spec(to_tagged(spec), "g")
        assert again.meta.title == spec.meta.title
