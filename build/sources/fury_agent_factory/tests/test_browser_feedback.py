"""Real sandbox/browser fixtures for feedback races; never acceptance output."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from devteam_browser import check_frontend
from devteam_sandbox import available
HTML='''<html><body><form><label for="guest">Guest Name</label><input id="guest"><label for="date">Date</label><input id="date" type="date"><select id="hotel"><option value="1">Fictional Hotel</option></select><button type="submit">Book</button></form><div id="feedback"></div><div id="reservations"></div></body></html>'''
JS='''let timer;async function refresh(){const r=await furyApi('GET','/bookings');document.getElementById('reservations').textContent=r.body.bookings.map(b=>'Fictional Hotel '+b.guest).join(' | ')}
function feedback(text,success){REPLACE document.getElementById('feedback').textContent=text;if(success)timer=setTimeout(()=>{document.getElementById('feedback').textContent=''},3000)}
document.querySelector('form').addEventListener('submit',async e=>{e.preventDefault();const r=await furyApi('POST','/bookings',{hotel_id:1,guest:document.getElementById('guest').value,date:document.getElementById('date').value});if(r.status===201){feedback('Confirmed',true);await refresh()}else if(r.status===409)feedback('Conflict: already booked',false)});
(async()=>{await furyApi('GET','/hotels');await refresh()})();'''
@unittest.skipUnless(available(),'Linux isolation unavailable')
class FeedbackTests(unittest.TestCase):
 def exercise(self,fixed,duplicate=False,navigation=False,broken=False):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=root/'code';code.mkdir()
   (code/'backend.py').write_text((Path(__file__).parents[1]/'devteam_reference.py').read_text())
   (code/'qa-reference.json').write_text(json.dumps({'hotels':[{'id':1,'name':'Fictional Hotel','city':'Frankfurt','price':100}],'error_fields':{str(status):['error'] for status in (400,404,409)}}))
   (code/'index.html').write_text(HTML.replace('<body>','<body><div id="hidden-history" hidden></div>') if duplicate else HTML);(code/'styles.css').write_text('body{color:black}')
   script=JS.replace('REPLACE','clearTimeout(timer);' if fixed else '')
   if duplicate:script=script.replace("document.getElementById('reservations').textContent=","document.getElementById('hidden-history').textContent=r.body.bookings.map(b=>b.guest).join(' ');document.getElementById('reservations').textContent=")
   if navigation:
    (code/'index.html').write_text(HTML.replace('<body>','<body><nav><button id=show>Bookings</button></nav><section id=pane hidden>').replace('</body>','</section></body>'))
    if not broken:script="document.getElementById('show').onclick=()=>document.getElementById('pane').hidden=false;\n"+script
   (code/'app.js').write_text(script)
   asyncio.run(check_frontend(code,root/'data',inventory_checks=False))
 def test_stale_success_timer_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'timer erased'):self.exercise(False)
 def test_cleared_prior_timer_preserves_conflict(self):self.exercise(True)

 def test_hidden_duplicate_does_not_hide_visible_reservation(self):self.exercise(True,duplicate=True)

 def test_functional_button_navigation_is_accepted(self):self.exercise(True,navigation=True)

 def test_broken_button_navigation_is_still_rejected(self):
  with self.assertRaisesRegex(ValueError,'navigation'):self.exercise(True,navigation=True,broken=True)
