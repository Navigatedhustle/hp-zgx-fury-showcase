"""Exact public contract fixtures through the real isolated runner, not GPU acceptance."""
import tempfile,unittest
from pathlib import Path
from devteam_sandbox import check_backend_contract,available
from test_devteam_frontend_acceptance import BACKEND
@unittest.skipUnless(available(),'Linux isolation unavailable')
class ExactStatusTests(unittest.TestCase):
 def run_contract(self,text):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=root/'code';code.mkdir();(code/'backend.py').write_text(text);check_backend_contract(code,root/'data')
 def test_consistent_contract_passes(self):self.run_contract(BACKEND)
 def test_ambiguous_unknown_id_status_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'must return404'):self.run_contract(BACKEND.replace("{'status':404","{'status':400"))
 def test_new_booking_status_is_enforced(self):
  with self.assertRaisesRegex(ValueError,'must return201'):self.run_contract(BACKEND.replace("{'status':201","{'status':200"))
 def test_leaked_sqlite_connections_are_rejected(self):
  with self.assertRaisesRegex(ValueError,'leaks database connections'):
   self.run_contract(BACKEND.replace('with closing(sqlite3.connect(db_path)) as db, db:','with sqlite3.connect(db_path) as db:'))
 def test_price_type_is_validated_before_frontend(self):
  with self.assertRaisesRegex(ValueError,'numeric price'):
   self.run_contract(BACKEND.replace("'price':100","'price':'100'"))
 def test_closing_without_committing_cannot_claim_success(self):
  with self.assertRaisesRegex(ValueError,'COMMIT'):
   self.run_contract(BACKEND.replace('with closing(sqlite3.connect(db_path)) as db, db:','with closing(sqlite3.connect(db_path)) as db:'))
 def test_python_global_state_cannot_replace_persistent_bookings(self):
  source="bookings=[]\ndef handle(request,db_path):\n if request['method']=='GET':return {'status':200,'body':{'hotels':[{'id':i,'name':'Fictional','city':'Frankfurt','price':100}for i in range(1,6)]}}if request['path']=='/hotels'else{'status':200,'body':{'bookings':bookings}}\n bookings.append(dict(request['body'],id=1));return {'status':201,'body':{'booking':bookings[-1]}}\n"
  with self.assertRaisesRegex(ValueError,'NEW process'):self.run_contract(source)

class QAMessageContractTests(unittest.TestCase):
 def test_exact_error_prose_is_rejected_before_merge(self):
  from devteam import validate_ticket_patch
  with self.assertRaisesRegex(ValueError,'error prose'):
   validate_ticket_patch({'files':{'test_backend.py':'self.assertEqual(reply["body"]["error"], "Hotel not found")'}})
 def test_status_and_nonempty_error_assertions_are_preserved(self):
  from devteam import validate_ticket_patch
  code='self.assertEqual(reply["status"],404)'+chr(10)+'self.assertIsInstance(reply["body"]["error"],str)'+chr(10)+'self.assertTrue(reply["body"]["error"])'
  validate_ticket_patch({'files':{'test_backend.py':code}})

@unittest.skipUnless(available(),'Linux isolation unavailable')
class ColdStartTests(unittest.TestCase):
 def test_post_cannot_depend_on_prior_inventory_get(self):
  source=BACKEND.replace(" if method=='GET' and path=='/hotels':return", " if method=='POST' and not __import__('pathlib').Path(db_path).exists():return {'status':404,'body':{'error':'Not seeded'}}\n if method=='GET' and path=='/hotels':__import__('pathlib').Path(db_path).touch();return")
  with self.assertRaisesRegex(ValueError,'fresh database'):ExactStatusTests.run_contract(self,source)
