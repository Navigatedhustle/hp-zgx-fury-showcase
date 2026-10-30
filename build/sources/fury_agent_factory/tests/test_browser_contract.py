"""Synthetic code fixtures through real bubblewrap and Chromium; not GPU acceptance."""
import asyncio,tempfile,unittest
from pathlib import Path
from devteam_sandbox import available
from devteam_browser import check_frontend
BACKEND='''import sqlite3
def handle(request,db_path):
 with sqlite3.connect(db_path) as c:
  c.execute('CREATE TABLE IF NOT EXISTS bookings(hotel_id INTEGER,guest TEXT,date TEXT)')
  if request['path']=='/hotels':return {'status':200,'body':{'hotels':[{'id':1,'name':'Fictional Fixture Hotel','city':'Frankfurt','price':100}]}}
  if request['method']=='POST':
   b=request['body'];c.execute('INSERT INTO bookings VALUES(?,?,?)',(b['hotel_id'],b['guest'],b['date']));return {'status':201,'body':{'id':1}}
  return {'status':200,'body':{'bookings':[{'hotel_id':r[0],'guest':r[1],'date':r[2]} for r in c.execute('SELECT * FROM bookings')]}}
'''
@unittest.skipUnless(available(),'Actual Linux isolation unavailable')
class BrowserContractTests(unittest.TestCase):
 def fixture(self,root,ordered):
  code=root/'code';code.mkdir();(code/'backend.py').write_text(BACKEND);(code/'index.html').write_text('<html><body><div id="reservations"></div></body></html>');(code/'styles.css').write_text('body{color:black;background:white}')
  prefix='let hotels=[];async function loadHotels(){const r=await window.furyApi("GET","/hotels");hotels=r.body.hotels}async function loadBookings(){const r=await window.furyApi("GET","/bookings");document.getElementById("reservations").textContent=r.body.bookings.map(b=>(hotels.find(h=>h.id===b.hotel_id)?.name||"Unknown Hotel")+" "+b.guest).join(" ")}'
  script=prefix+('(async()=>{await loadHotels();await loadBookings()})();' if ordered else 'loadHotels();loadBookings();')
  (code/'app.js').write_text(script);return code
 def test_real_backend_reply_race_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=self.fixture(root,False)
   with self.assertRaisesRegex(ValueError,'loading race'):asyncio.run(check_frontend(code,root/'data',interactions=False))
 def test_ordered_real_backend_load_passes(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);asyncio.run(check_frontend(self.fixture(root,True),root/'data',interactions=False))

 def test_caught_invalid_http_client_signature_is_actionable(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=self.fixture(root,True)
   (code/'app.js').write_text('try { window.furyApi.get("/hotels") } catch(e) { console.error("Failed to load",e.message) }')
   with self.assertRaisesRegex(ValueError,'furyApi.get'):
    asyncio.run(check_frontend(code,root/'data',interactions=False))
