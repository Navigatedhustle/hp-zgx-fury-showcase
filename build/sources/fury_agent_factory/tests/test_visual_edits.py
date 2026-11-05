import json
import pytest
from devteam import apply_visual_edits


def test_visual_patch_preserves_other_code_and_applies_sequential_owned_edits():
    source={'index.html':'<main><div role="table">Empty</div></main>','styles.css':'body{color:#111}','app.js':'window.working=true;'}
    response={'summary':'Use native semantics and a fluid layout','changes':[
        {'file':'index.html','old':' role="table"','new':''},
        {'file':'styles.css','old':'body{color:#111}','new':'body{color:#111;max-width:100%}'}]}
    result=apply_visual_edits(json.dumps(response),source)
    assert result['files']['index.html']=='<main><div>Empty</div></main>'
    assert 'app.js' not in result['files']
    assert source['index.html']=='<main><div role="table">Empty</div></main>'


def test_visual_patch_cannot_touch_backend_or_ambiguous_source():
    for change in [{'file':'backend.py','old':'x','new':'y'}, {'file':'styles.css','old':'x','new':'y'}]:
        with pytest.raises(ValueError):apply_visual_edits(json.dumps({'summary':'Edit','changes':[change]}),{'styles.css':'xx','backend.py':'x'})


def test_harmless_noop_does_not_discard_a_later_valid_fix():
    response={'summary':'Keep working styles and fix semantics','changes':[
        {'file':'styles.css','old':'body{}','new':'body{}'},
        {'file':'index.html','old':' role="table"','new':''}]}
    result=apply_visual_edits(json.dumps(response),{'styles.css':'body{}','index.html':'<div role="table">Empty</div>'})
    assert result['files']=={'index.html':'<div>Empty</div>'}


def test_passed_review_can_preserve_source_without_fabricating_a_change():
    result=apply_visual_edits(json.dumps({'summary':'Existing design passed independent checks','changes':[]}),{'styles.css':'body{color:#111}'})
    assert result['files']=={'styles.css':'body{color:#111}'}
