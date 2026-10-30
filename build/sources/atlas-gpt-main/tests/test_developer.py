from atlas.developer import function_source,test_reference as build_test_reference,intent
from atlas.sandbox import run
from pathlib import Path
from atlas.config import ROOT,UPGRADE_GOLDEN

def test_own_code_is_exact_and_key_lines_real():
    source=function_source('forecast_quarter');actual=(ROOT/source['path']).read_text().splitlines(keepends=True)
    assert ''.join(actual[source['start_line']-1:source['start_line']-1+len(source['code'].splitlines())])==source['code']
    assert source['highlight_lines'] and all(source['start_line']<=line<source['start_line']+len(source['code'].splitlines()) for line in source['highlight_lines'])

def test_real_site_scoring_unit_tests_execute():
    r=run(build_test_reference());assert r['success'],r['stderr']
    assert r['table']==[{'tests_run':3,'failures':0,'errors':0}]

def test_developer_golden_intents():
    for persona,expected,question in UPGRADE_GOLDEN:
        if persona=='developer':assert 'developer_'+intent(question)==expected
