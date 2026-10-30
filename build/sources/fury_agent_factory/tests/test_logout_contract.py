"""Actual reference backend in namespaces; simulated no-op logout must fail."""
from pathlib import Path
import pytest
import travel_checks
from devteam_sandbox import available
CODE=Path(__file__).resolve().parents[4]/'examples/reference-travel/app'
pytestmark=pytest.mark.skipif(not available(),reason='Linux namespaces required')
def test_real_reference_revokes_token_across_processes(tmp_path):
 result=travel_checks.check_product(CODE,tmp_path/'real')
 assert result['passed'],result['log']
def test_noop_logout_cannot_pass_independent_authentication(tmp_path,monkeypatch):
 real=travel_checks.execute
 def execute(code,data,mode,payload):
  if payload['method']=='POST' and payload['path']=='/logout':return {'status':200,'body':{}}
  return real(code,data,mode,payload)
 monkeypatch.setattr(travel_checks,'execute',execute)
 result=travel_checks.check_product(CODE,tmp_path/'broken')
 auth=next(c for c in result['checks'] if c['id']=='auth')
 assert not auth['passed'] and 'GET /me' in auth['error']

def test_literal_method_diagnostics_are_specific_and_do_not_change_tests():
 from travel_run import qa_contract_diagnostics
 source="response = handle(request('POST', '/listings', {'sort':'price_desc'}))"
 text=qa_contract_diagnostics(source)
 assert 'POST /listings' in text and 'GET /listings' in text and 'native dict body' in text
 assert not qa_contract_diagnostics("response = handle(request('GET', '/listings', {}))")
 assert not qa_contract_diagnostics("response = handle(request('POST', '/login', {}))")

def test_wrong_route_auth_guard_is_owned_by_backend_not_qa(tmp_path):
 from shutil import copytree
 from travel_run import repair_targets
 code=tmp_path/'source';copytree(CODE,code)
 p=code/'reservations.py';source=p.read_text();p.write_text(source.replace('def routes(', 'def original_routes(',1)+"\ndef routes(conn,request):\n if request.get('path')=='/nonexistent':return {'status':401,'body':{'error':'Wrong guard'}}\n return original_routes(conn,request)\n")
 result=travel_checks.check_product(code,tmp_path/'db')
 failure=next(c for c in result['checks'] if c['id']=='routing')
 assert not failure['passed']
 assert repair_targets(failure)==['reservations.py']
 assert 'do not weaken' in failure['error']


def test_literal_request_dictionary_diagnostic():
 from travel_run import qa_contract_diagnostics
 assert 'POST /listings' in qa_contract_diagnostics("handle({'method':'POST','path':'/listings','body':{}}, db_path)")
 assert not qa_contract_diagnostics("print('description','/listings')")
