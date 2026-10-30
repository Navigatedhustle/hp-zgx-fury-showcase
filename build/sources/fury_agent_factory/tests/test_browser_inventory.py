"""Real browser/sandbox fixtures for numeric inventory rendering; no GPU evidence."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from devteam_browser import check_frontend
from devteam_sandbox import available
from test_browser_feedback import HTML,JS
@unittest.skipUnless(available(),'Linux isolation unavailable')
class InventoryBrowserTests(unittest.TestCase):
 def exercise(self,numeric):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);code=root/'code';code.mkdir()
   (code/'backend.py').write_text((Path(__file__).parents[1]/'devteam_reference.py').read_text())
   hotels=[{'id':i,'name':'Fictional Hotel '+str(i),'city':'Frankfurt'if i!=2 else'Tokyo','price':p}for i,p in [(1,100),(2,50),(3,150)]]
   (code/'qa-reference.json').write_text(json.dumps({'hotels':hotels,'error_fields':{str(s):['error']for s in(400,404,409)}}))
   inventory='<label for="city">City</label><select id="city"><option value="all">All Cities</option><option value="Frankfurt">Frankfurt</option><option value="Tokyo">Tokyo</option></select><label for="sort">Sort Price</label><select id="sort"><option value="asc">Low to High</option><option value="desc">High to Low</option></select><div id="hotel-list"></div>'
   (code/'index.html').write_text(HTML.replace('</body>',inventory+'</body>'));(code/'styles.css').write_text('body{color:black}')
   extra='''let hotels=[];function escapePrice(x){return CONVERT}function show(){let xs=hotels.filter(h=>document.getElementById('city').value==='all'||h.city===document.getElementById('city').value);xs.sort((a,b)=>document.getElementById('sort').value==='desc'?b.price-a.price:a.price-b.price);document.getElementById('hotel-list').innerHTML=xs.map(h=>'<article class="hotel-card">'+h.name+' '+h.city+'<span class="price">$'+escapePrice(h.price)+'</span></article>').join('')}document.getElementById('city').onchange=show;document.getElementById('sort').onchange=show;(async()=>{hotels=(await furyApi('GET','/hotels')).body.hotels;show()})();'''
   extra=extra.replace('CONVERT','String(x)'if numeric else'typeof x==="string"?x:""')
   (code/'app.js').write_text(JS.replace('REPLACE','clearTimeout(timer);')+'\n'+extra)
   asyncio.run(check_frontend(code,root/'data'))
 def test_numeric_values_cannot_disappear_during_escaping(self):
  with self.assertRaisesRegex(ValueError,'price is missing'):self.exercise(False)
 def test_actual_numeric_prices_filter_and_sort(self):self.exercise(True)
