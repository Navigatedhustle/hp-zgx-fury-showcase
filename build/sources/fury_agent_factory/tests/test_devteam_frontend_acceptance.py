"""Explicit synthetic code fixtures, executed through the actual sandbox."""
import tempfile,unittest
from pathlib import Path
from devteam_sandbox import execute,available
BACKEND='''import sqlite3,datetime
from contextlib import closing
def handle(request,db_path):
 body=request.get('body') or {};method=request['method'];path=request['path']
 if method=='GET' and path=='/hotels':return {'status':200,'body':{'hotels':[{'id':i,'name':'Fictional Fixture '+str(i),'city':'Frankfurt','price':100} for i in range(1,6)]}}
 with closing(sqlite3.connect(db_path)) as db, db:
  db.execute('CREATE TABLE IF NOT EXISTS bookings (hotel INTEGER, guest TEXT, day TEXT, UNIQUE(hotel,day))')
  if method=='GET':return {'status':200,'body':{'bookings':[dict(zip(('id','hotel_id','guest','date'),row)) for row in db.execute('SELECT rowid,hotel,guest,day FROM bookings').fetchall()]}}
  if body.get('hotel_id') not in range(1,6):return {'status':404,'body':{'error':'unknown hotel'}}
  try:
   assert body.get('guest')
   datetime.date.fromisoformat(body['date'])
  except (AssertionError,ValueError,KeyError):return {'status':400,'body':{'error':'invalid'}}
  try:db.execute('INSERT INTO bookings VALUES (?,?,?)',(body['hotel_id'],body['guest'],body['date']))
  except sqlite3.IntegrityError:return {'status':409,'body':{'error':'duplicate'}}
 return {'status':201,'body':{'id':1}}
'''
@unittest.skipUnless(available(),'Actual Linux sandbox prerequisite unavailable')
class FrontendAcceptanceTests(unittest.TestCase):
 def check_html(self,html):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=root/'code';code.mkdir();(code/'backend.py').write_text(BACKEND);(code/'index.html').write_text(html);return execute(code,root/'data','test')
 def test_dead_navigation_blocks_acceptance(self):
  r=self.check_html('<a href="#bookings">Bookings</a>');self.assertFalse(r['passed']);self.assertIn('Navigation target missing',r['log'])
 def test_real_fragment_targets_pass(self):
  r=self.check_html('<a href="#bookings">Bookings</a><section id="bookings">Fictional bookings</section>');self.assertTrue(r['passed'],r['log'])
