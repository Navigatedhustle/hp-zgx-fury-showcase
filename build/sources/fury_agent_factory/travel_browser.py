"""Real Chromium acceptance using generated JS and real sandboxed SQLite backend."""
import asyncio,json,time,uuid,re
from datetime import date,timedelta
from devteam_sandbox import execute
def action_probe_script(source):
 # Observe actual delegated selector matches without changing application handlers.
 selectors=list(dict.fromkeys(re.findall(r"\.target\.closest\(\s*['\"]([^'\"]+)['\"]\s*\)",source)))[:16]
 return """window.__factoryActionTrace=[];document.addEventListener('click',e=>{
 const attrs=['data-view','data-detail','data-favorite','data-unfavorite','data-edit-itinerary','data-delete-itinerary'];
 const action=e.target.closest('button,'+attrs.map(a=>'['+a+']').join(','));
 if(!action)return;
 const record={tag:action.tagName,id:action.id,attributes:Object.fromEntries(attrs.filter(a=>action.hasAttribute(a)).map(a=>[a,action.getAttribute(a)])),delegated_matches:[]};
 for(const selector of SELECTORS){try{record.delegated_matches.push({selector,matched:!!e.target.closest(selector)})}catch{}}
 window.__factoryActionTrace.push(record);if(window.__factoryActionTrace.length>12)window.__factoryActionTrace.shift();
 },true);""".replace('SELECTORS',json.dumps(selectors))

async def check_browser(code,data,stop,smoke=False):
 from playwright.async_api import async_playwright
 events=[];errors=[];token=None;polish=[];details=[]
 source=(code/'app.js').read_text();markup=(code/'index.html').read_text()
 required=set(re.findall(r'''\$\(['"]#([A-Za-z0-9_-]+)['"]\)''',source));present=set(re.findall(r'''\bid=['"]([^'"]+)['"]''',markup))
 missing=sorted(required-present)
 async def api(method,path,body=None):
  nonlocal token
  if stop.is_set():raise RuntimeError('Cancelled')
  reply=await asyncio.to_thread(execute,code,data,'api',{'method':method,'path':path,'body':body or {},'headers':{'authorization':'Bearer '+token} if token else {}})
  if path in ('/login','/register') and reply.get('body',{}).get('token'):token=reply['body']['token']
  if path=='/logout':token=None
  if method=='GET' and re.fullmatch(r'/listings/\d+',path) and reply.get('status')==200 and isinstance(reply.get('body',{}).get('listing'),dict):details.append(reply['body']['listing'])
  events.append({'method':method,'path':path,'status':reply.get('status'),'body':{} if path in ('/register','/login') else (body or {}),'error':reply.get('body',{}).get('error'),'response_keys':list(reply.get('body',{}))});return reply
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
  async def cancel_browser():
   while not stop.is_set():await asyncio.sleep(.1)
   await browser.close()
  cancellation=asyncio.create_task(cancel_browser())
  page=await browser.new_page(viewport={'width':1440,'height':1000})
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
  page.on('requestfailed',lambda r:errors.append(r.url+': '+str(r.failure)))
  await page.expose_function('__factoryTestTransport',api)
  async def load():
   await page.goto('about:blank')
   html=(code/'index.html').read_text();import re
   html=re.sub(r'<script\b[^>]*>[\s\S]*?</script>','',html,flags=re.I);html=re.sub(r'<link\b[^>]*>','',html,flags=re.I)
   script='<script>'+action_probe_script(source)+'window.furyApi=(method,path,body={})=>window.__factoryTestTransport(method,path,JSON.parse(JSON.stringify(body)));'+(code/'app.js').read_text().replace('</script','<\\/script')+'</script>'
   html=html.replace('</body>',script+'</body>') if '</body>' in html else html+script
   await page.set_content("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'\">"+'<style>'+(code/'styles.css').read_text()+'</style>'+html)
  async def auth_form(kind):
   form=page.locator('#'+kind+'-form')
   if not await form.is_visible():
    nav=page.locator('#auth-nav')
    if await nav.count() and await nav.is_visible():await nav.click()
    tab=page.locator('[data-target="'+kind+'-form"]')
    if await tab.count() and await tab.first.is_visible():await tab.first.click()
    elif not await form.is_visible():
     button=page.get_by_role('button',name=re.compile('register|create account|sign up' if kind=='register' else 'login|sign in',re.I)).first
     if await button.count() and await button.is_visible():await button.click()
   await form.wait_for()
  async def wait_path(path,method='GET',since=0):
   for _ in range(100):
    if any(x['path']==path and x['method']==method and x['status']<300 for x in events[since:]):return
    await asyncio.sleep(.1)
   matching=[x for x in events[since:] if x['path']==path and x['method']==method]
   trace=await page.evaluate('window.__factoryActionTrace||[]')
   raise AssertionError('No successful '+method+' '+path+'; last action='+json.dumps(trace[-1] if trace else {})+'; observed='+json.dumps(matching[-1] if matching else {'last_calls':events[-3:]}))
  try:
   async with asyncio.timeout(110):
    await load();await wait_path('/listings')
    if await page.locator('#destination-grid').count():
     await page.locator('#listing-list .listing-card').first.wait_for()
     await page.wait_for_function("()=>Array.from(document.querySelectorAll('.hero-photo,#listing-list img')).every(i=>i.complete&&i.naturalWidth>0)")
     data.mkdir(parents=True,exist_ok=True)
     await page.screenshot(path=str(data/'portal-desktop.png'),full_page=True)
     await page.set_viewport_size({'width':375,'height':812})
     assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Mobile horizontal overflow in travel discovery'
     await page.screenshot(path=str(data/'portal-mobile.png'),full_page=True)
     await page.set_viewport_size({'width':1440,'height':1000})
    if smoke:
     await page.locator('.nav-link[data-view=listings]').first.click();await page.locator('#listing-list [data-detail]').first.wait_for()
     assert 'undefined' not in (await page.locator('#listing-list').inner_text()).lower(), 'Listing preview renders undefined values'
     assert not errors,'Browser bootstrap errors: '+json.dumps(errors)
     return {'passed':True,'scope':'development preview bootstrap only; full acceptance remains required','events':events,'console_errors':errors}
    await auth_form('register')
    if not await page.locator('[data-view=auth]').count():polish.append('Provide a visible Sign in/register navigation button for anonymous visitors who explore listings')
    email='browser'+uuid.uuid4().hex[:10]+'@example.test'
    await page.locator('#register-form [name=email]').fill(email);await page.locator('#register-form [name=password]').fill('BrowserPass2028!');await page.locator('#register-form button[type=submit]').click();await wait_path('/register','POST');await page.locator('[data-detail]').first.wait_for();assert await page.locator('[data-detail]').count()>0
    if email not in await page.locator('body').inner_text():polish.append('Show the signed-in email/account identity in the header after login/register')
    await page.locator('[data-favorite]').first.click();await wait_path('/favorites','POST')
    await page.locator('#search').fill('Lisbon');await page.locator('#search-button').click();await asyncio.sleep(1)
    assert 'lisbon' in (await page.locator('#listing-list').inner_text()).lower()
    await page.locator('#search').fill('');await page.locator('#search-button').click();await asyncio.sleep(.5)
    await page.locator('[data-detail]').first.click();await page.locator('#quote-form [name=listing_id]').wait_for(state='attached')
    for _ in range(50):
     if details:break
     await asyncio.sleep(.1)
    await asyncio.sleep(.2)
    assert details,'Listing detail API must return body.listing'
    selected=await page.locator('#quote-form [name=listing_id]').input_value()
    assert selected==str(details[-1]['id']) and details[-1]['name'] in await page.locator('#listing-detail').inner_text(), 'Listing detail must unwrap the actual response body.listing record before rendering name/city/price and setting the quote listing_id. Actual response keys=[listing], listing.id='+str(details[-1]['id'])+', quote form listing_id='+repr(selected)
    if await page.locator('.back-button').count():
     await page.locator('.back-button').click()
     assert await page.locator('#listing-list').is_visible(), 'Back to Listings button must work: bind every data-view navigation control, including .back-button'
     await page.locator('[data-detail]').first.click()
    start=date.today()+timedelta(days=100)
    await page.locator('#quote-form [name=check_in]').fill(str(start));await page.locator('#quote-form [name=check_out]').fill(str(start+timedelta(days=2)));await page.locator('#quote-form [name=party]').fill('1')
    await page.locator('#quote-button').click();await wait_path('/quote','POST')
    if await page.locator('#request-key').count() and await page.locator('#request-key').is_visible():polish.append('Hide/remove the unused technical request-key input; keys must be generated automatically')
    await page.locator('#reserve-button').click();await wait_path('/reservations','POST');await asyncio.sleep(.5)
    assert str(start) in await page.locator('#reservations').inner_text() or await page.locator('#reservations time[datetime="'+str(start)+'"]').count(), 'Reservation date must render in the actual reservations view'
    await page.locator('.nav-link[data-view=itineraries]').click()
    await page.locator('#itinerary-form [name=title]').fill('Browser journey');await page.locator('#itinerary-form [name=notes]').fill('Walk by the water');await page.locator('#itinerary-form button[type=submit]').click();await wait_path('/itineraries','POST');await page.locator('[data-edit-itinerary]').first.click();await page.locator('#itinerary-form [name=title]').fill('Edited browser journey');await page.locator('#itinerary-form button[type=submit]').click();await asyncio.sleep(.8)
    assert any(x['path'].startswith('/itineraries/') and x['method']=='PUT' and x['status']==200 for x in events)
    page.on('dialog',lambda dialog:dialog.accept());await page.locator('[data-delete-itinerary]').first.click();await asyncio.sleep(.5)
    assert 'Edited browser journey' not in await page.locator('#itineraries').inner_text(), 'Itinerary deletion must update the real server-backed list'
    await load();await wait_path('/me');await asyncio.sleep(1)
    await page.locator('.nav-link[data-view=reservations]').click();await asyncio.sleep(.5)
    assert str(start) in await page.locator('#reservations').inner_text() or await page.locator('#reservations time[datetime="'+str(start)+'"]').count(), 'Reservation date must render in the actual reservations view'
    await page.locator('#logout').click();await wait_path('/logout','POST')
    await auth_form('login')
    await page.locator('#login-form [name=email]').fill('admin@example.test');await page.locator('#login-form [name=password]').fill('DemoAdmin2028!');await page.locator('#login-form button[type=submit]').click();await page.locator('.nav-link[data-view=admin]').click();await wait_path('/admin/reservations')
    assert (await page.locator('#admin-reservations').inner_text()).strip()
    await page.set_viewport_size({'width':375,'height':812});await asyncio.sleep(.2)
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'Mobile horizontal overflow'
    clipped=await page.locator('.main-nav').evaluate('nav=>Array.from(nav.querySelectorAll(".nav-link")).filter(e=>getComputedStyle(e).display!=="none").some(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth+1})') if await page.locator('.main-nav').count() else False
    assert not clipped,'Mobile horizontal overflow or clipped navigation: all navigation buttons including Admin must be fully readable at375px. Wrap mobile navigation into rows with nonwrapping button labels, or supply a usable visible menu. Preserve desktop layout.'
    assert not errors,'Browser errors: '+json.dumps(errors)
    assert not polish,'Product polish requirements: '+json.dumps(polish)
    return {'passed':True,'events':events,'console_errors':errors,'viewports':[1440,375]}
  except Exception as e:
   if stop.is_set():raise asyncio.CancelledError()
   data.mkdir(parents=True,exist_ok=True);await page.screenshot(path=str(data/'failure.png'),full_page=True)
   trace=await page.evaluate('window.__factoryActionTrace||[]')
   diagnostic=''
   if errors and missing:diagnostic+=' Frontend integration: missing static HTML IDs referenced by actual app.js: '+', '.join(missing)+'. Repair index.html and JavaScript together so selectors match actual elements.'
   if any(x['method']=='POST' and x['path']=='/reservations' and x['status']==201 for x in events) and not any(x['method']=='GET' and x['path']=='/reservations' for x in events):diagnostic=' Observed POST /reservations201 but no GET /reservations. Navigation must actually call loadReservations() after showing that view; apply equivalent data loading to favorites, itineraries and admin navigation.'
   return {'passed':False,'error':(str(e)[:800]+diagnostic+' Recent actual API execution: '+json.dumps(events[-3:]))[:3500],'events':events,'action_trace':trace,'console_errors':errors,'body':(await page.locator('body').inner_text())[-5000:]}
  finally:
   cancellation.cancel();await asyncio.gather(cancellation,return_exceptions=True);await browser.close()
