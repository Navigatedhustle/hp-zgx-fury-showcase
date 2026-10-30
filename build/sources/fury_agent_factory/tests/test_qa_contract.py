"""Generated QA checked against a fixture, never substituted for real output."""
import tempfile,unittest,json
from pathlib import Path
from devteam_sandbox import available,check_generated_qa

@unittest.skipUnless(available(),'Linux isolation unavailable')
class QAContractTests(unittest.TestCase):
 def check(self,source,error_fields=("error",),transform=None):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=root/'code';code.mkdir()
   backend=(Path(__file__).parents[1]/'devteam_reference.py').read_text()
   (code/'backend.py').write_text(transform(backend) if transform else backend)
   (code/'qa-reference.json').write_text(json.dumps({'hotels':[{'id':i,'name':'Fictional Hotel','city':'Frankfurt','price':100}for i in range(1,6)],'error_fields':{str(status):list(error_fields)for status in (400,404,409)}}))
   (code/'test_backend.py').write_text(source)
   check_generated_qa(code,root/'data')
 def test_false_invalid_leap_day_expectation_rejected(self):
  with self.assertRaisesRegex(ValueError,'contradicts.*public-contract'):
   self.check('''import tempfile,unittest
from backend import handle
class Test(unittest.TestCase):
 def test_date(self):
  with tempfile.TemporaryDirectory() as d:
   r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':1,'guest':'Fictional Guest','date':'2028-02-29'}},d+'/db')
   self.assertEqual(r['status'],400)
''')
 def test_real_calendar_expectations_pass(self):
  self.check('''import tempfile,unittest
from backend import handle
class Test(unittest.TestCase):
 def test_date(self):
  with tempfile.TemporaryDirectory() as d:
   for day,status in [('2028-02-29',201),('2027-02-29',400)]:
    r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':1,'guest':'Fictional Guest','date':day}},d+'/db')
    self.assertEqual(r['status'],status)
''')
 def test_supported_error_aliases_match_real_backend(self):
  for field in ('error','message'):
   self.check("import tempfile,unittest\nfrom backend import handle\nclass Test(unittest.TestCase):\n def test_error_alias(self):\n  with tempfile.TemporaryDirectory() as d:\n   r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':999,'guest':'Fictional Guest','date':'2028-01-01'}},d+'/db')\n   self.assertEqual(r['status'],404)\n   self.assertTrue(r['body'][FIELD])\n".replace('FIELD',repr(field)),(field,))
 def test_requesting_absent_alias_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'contradicts'):
   self.check("import tempfile,unittest\nfrom backend import handle\nclass Test(unittest.TestCase):\n def test_wrong_alias(self):\n  with tempfile.TemporaryDirectory() as d:\n   r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':999,'guest':'Fictional Guest','date':'2028-01-01'}},d+'/db')\n   self.assertIn('message',r['body'])\n")
 def test_malformed_nonobject_body_passes(self):
  self.check('''import tempfile,unittest
from backend import handle
class Test(unittest.TestCase):
 def test_invalid_body(self):
  with tempfile.TemporaryDirectory() as d:
   r=handle({'method':'POST','path':'/bookings','body':['invalid']},d+'/db')
   self.assertEqual(r['status'],400)
''')

 def test_boolean_assertion_calls_are_rejected_before_merge(self):
  from devteam import validate_ticket_patch
  with self.assertRaisesRegex(ValueError,'return None'):
   validate_ticket_patch({'files':{'test_backend.py':"self.assertIn('error', body) or self.assertIn('message', body)"}})

 def test_many_calls_do_not_exhaust_reference_descriptors(self):
  self.check("import tempfile,unittest,gc\nfrom backend import handle\nclass Test(unittest.TestCase):\n def test_many_requests(self):\n  with tempfile.TemporaryDirectory() as d:\n   gc.disable()\n   try:\n    for index in range(128):\n     r=handle({'method':'GET','path':'/hotels','body':{}},d+'/db')\n     self.assertEqual(r['status'],200)\n   finally:gc.enable()\n")

 def test_legitimate_extra_key_rejection_does_not_fail_oracle(self):
  def strict(backend):return backend.replace("  hid=body.get('hotel_id');", "  if isinstance(body,dict) and set(body)-{'hotel_id','guest','date'}:return reply(400,error='Extra keys')\n  hid=body.get('hotel_id');")
  self.check("import tempfile,unittest\nfrom backend import handle\nclass Test(unittest.TestCase):\n def test_extra_keys(self):\n  with tempfile.TemporaryDirectory() as d:\n   r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':1,'guest':'Fictional Guest','date':'2028-01-01','extra':'unused'}},d+'/db')\n   self.assertEqual(r['status'],400)\n",transform=strict)
 def test_wrong_backend_and_wrong_qa_cannot_agree_past_trusted_checks(self):
  def wrong(backend):return backend.replace("  try:date.fromisoformat(day)","  if day=='2028-02-29':return reply(400,error='Wrong leap day')\n  try:date.fromisoformat(day)")
  with self.assertRaisesRegex(ValueError,'contradicts'):
   self.check("import tempfile,unittest\nfrom backend import handle\nclass Test(unittest.TestCase):\n def test_wrong_leap_day(self):\n  with tempfile.TemporaryDirectory() as d:\n   r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':1,'guest':'Fictional Guest','date':'2028-02-29'}},d+'/db')\n   self.assertEqual(r['status'],400)\n",transform=wrong)
 def test_valid_qa_exposing_backend_cold_start_defect_is_accepted(self):
  def cold(backend):return backend.replace(" with closing(sqlite3.connect(db_path)) as db, db:"," if method=='POST' and not Path(db_path).exists():return reply(404,error='Not initialized')\n with closing(sqlite3.connect(db_path)) as db, db:")
  self.check('''import tempfile,unittest
from backend import handle
class Test(unittest.TestCase):
 def test_valid_cold_booking(self):
  with tempfile.TemporaryDirectory() as d:
   r=handle({'method':'POST','path':'/bookings','body':{'hotel_id':1,'guest':'Fictional Guest','date':'2028-01-01'}},d+'/db')
   self.assertEqual(r['status'],201)
''',transform=cold)
