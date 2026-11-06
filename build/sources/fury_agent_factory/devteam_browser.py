"""Real generated-backend/browser contract check before publishing model output."""
import asyncio,html,io,re,uuid
from pathlib import Path
from playwright.async_api import async_playwright,expect
from devteam_sandbox import execute
from frontend_artwork import artwork_script

async def check_frontend(code:Path,data:Path,stop=None,*,interactions=True,inventory_checks=True,visual=False,seed_reservation=True):
 required=('index.html','styles.css','app.js','backend.py')
 if not all((code/n).is_file() for n in required):return
 inventory=await asyncio.to_thread(execute,code,data,'api',{'method':'GET','path':'/hotels','body':{}})
 hotels=inventory.get('body',{}).get('hotels',[])
 if inventory.get('status')!=200 or not hotels:raise ValueError('Browser contract check needs real hotel inventory')
 hotel=hotels[0];guest='Fictional Browser Contract '+uuid.uuid4().hex[:8]
 booked=await asyncio.to_thread(execute,code,data,'api',{'method':'POST','path':'/bookings','body':{'hotel_id':hotel['id'],'guest':guest,'date':'2028-12-15'}}) if seed_reservation else {'status':201}
 # Every validation attempt uses its own data directory. No fixture or fabricated response.
 if booked.get('status') not in (200,201):raise ValueError('Generated backend could not seed a real browser test reservation')
 seen=set();errors=[];posted=[];write_enabled=False
 async def api(method,path=None,body=None):
  if not ((method=='GET' and path in ('/hotels','/bookings')) or (write_enabled and method=='POST' and path=='/bookings')):raise ValueError('The application must not create bookings during initial load')
  response=await asyncio.to_thread(execute,code,data,'api',{'method':method,'path':path,'body':body or {}})
  # Force the scheduling order that exposed the real race. The payload itself
  # always comes from the generated backend, never a mock hotel/booking object.
  if path=='/hotels':await asyncio.sleep(.35)
  if method=='POST':posted.append(response)
  seen.add(path);return response
 async with async_playwright() as playwright:
  browser=await playwright.chromium.launch(args=['--no-sandbox','--disable-gpu'])
  try:
   context=await browser.new_context();page=await context.new_page();await context.route('**/*',lambda route:route.abort())
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.on('console',lambda e:errors.append(e.text) if e.type=='error' else None)
   await page.expose_function('__furyBrowserRequest',api)
   source=re.sub(r'<script\b[^>]*>[\s\S]*?</script>','',(code/'index.html').read_text(),flags=re.I)
   source=re.sub(r'<link\b[^>]*>','',source,flags=re.I)
   bridge='window.furyApi=(...args)=>window.__furyBrowserRequest(...args);'
   js=(bridge+'\n'+artwork_script(code)+'\n'+(code/'app.js').read_text()).replace('</script','<\\/script')
   document='<meta http-equiv="Content-Security-Policy" content="default-src \'none\';script-src \'unsafe-inline\';style-src \'unsafe-inline\';img-src data:;connect-src \'none\';form-action \'none\'">'+'<style>'+(code/'styles.css').read_text()+'</style>'+source+'<script>'+js+'</script>'
   await page.set_content('<iframe sandbox="allow-scripts allow-forms" style="width:1200px;height:900px" srcdoc="'+html.escape(document,quote=True)+'"></iframe>')
   frame=page.frame_locator('iframe');deadline=asyncio.get_running_loop().time()+8
   while seen!={'/hotels','/bookings'}:
    if stop and stop.is_set():raise asyncio.CancelledError()
    if errors:raise ValueError('Generated browser execution failed: '+errors[0][:400])
    if asyncio.get_running_loop().time()>deadline:raise ValueError('Generated site did not load real hotel and reservation data; use await window.furyApi("GET", "/hotels") and await window.furyApi("GET", "/bookings"), not .get/.post; loaded paths: '+repr(sorted(seen)))
    await asyncio.sleep(.1)
   await asyncio.sleep(.5)
   text=await frame.locator('body').inner_text()
   # Include hidden tab text: reservations must bind to inventory regardless of
   # which tab is initially shown, and must remain correct after refresh.
   full=await frame.locator('body').evaluate('(el)=>{const copy=el.cloneNode(true);copy.querySelectorAll("script,style,noscript").forEach(n=>n.remove());return copy.textContent}')
   if seed_reservation and guest not in full:raise ValueError('Existing reservations are absent from the generated page')
   if re.search(r'unknown\s+(hotel|property)',full,re.I):raise ValueError('Hotel/reservation loading race: load hotel inventory before rendering bookings, or rerender reservations after both requests settle; a real persisted reservation displayed Unknown Hotel')
   if errors:raise ValueError('Generated browser execution failed: '+errors[0][:400])
   if visual:await audit_visual(page,frame)
   if not interactions:return
   # Exercise actual generated booking and conflict controls, including the
   # delayed-success timer that erased a later real409 during the long soak.
   controls=frame.get_by_label(re.compile('guest|your name|full name',re.I)).first
   if not await controls.count():raise ValueError('Generated booking form lacks an accessible guest field')
   await reveal_control(frame,controls)
   form=frame.locator('form').filter(has=controls).first
   selector=form.locator('select').first;day=form.locator('input[type=date]').first
   submit=form.locator('button[type=submit],button:not([type]),input[type=submit]').first
   fresh_guest='Fictional Interaction '+uuid.uuid4().hex[:8]
   async def fill():
    await controls.fill(fresh_guest);await day.fill('2028-12-16');await selector.select_option(str(hotel['id']))
   write_enabled=True;await fill();await submit.click()
   try:await expect(frame.locator('body')).to_contain_text(fresh_guest,use_inner_text=True,timeout=8000)
   except AssertionError as error:raise ValueError('Successful form booking must render its real persisted reservation; responses='+repr(posted[-1:])+'; errors='+repr(errors)+'; visible='+ (await frame.locator('body').inner_text())[-900:]) from error
   if not posted or posted[-1].get('status') not in (200,201):raise ValueError('Generated booking form did not create a real reservation')
   await asyncio.sleep(2.5);await fill();before_posts=len(posted);await submit.click()
   deadline=asyncio.get_running_loop().time()+8
   while len(posted)==before_posts:
    if errors:raise ValueError('Generated browser execution failed: '+errors[0][:400])
    if asyncio.get_running_loop().time()>deadline:raise ValueError('Duplicate form submission did not reach the real backend')
    await asyncio.sleep(.05)
   conflict=re.compile(r'\b(?:conflict|already|409|duplicate|reserved)\b',re.I)
   try:await expect(frame.locator('body')).to_contain_text(conflict,use_inner_text=True,timeout=8000)
   except AssertionError as error:raise ValueError('Duplicate form booking must visibly explain the real409 conflict') from error
   if posted[-1].get('status')!=409:raise ValueError('Repeated hotel/date must return409')
   await asyncio.sleep(1.1)
   if not conflict.search(await frame.locator('body').inner_text()):raise ValueError('An old success timer erased newer conflict feedback. Cancel prior feedback timers whenever a new message is set; error/conflict messages must remain until the next user action.')
   if errors:raise ValueError('Generated browser execution failed: '+errors[0][:400])
   if inventory_checks:await check_inventory(frame,hotels)
  finally:await browser.close()

async def check_artwork_visibility(embedded):
 """Measure supplied artwork's rendered contribution, restoring exact inline styles."""
 from PIL import Image, ImageChops
 candidates=await embedded.evaluate("""async () => {
  const uri=window.furyArtwork?.hero;
  if (!uri) return null;
  const loaded=new Image();loaded.src=uri;await loaded.decode();
  return [...document.querySelectorAll('body *')].flatMap((el,index)=>{
   const cs=getComputedStyle(el),r=el.getBoundingClientRect();
   const image=el.tagName==='IMG' && el.currentSrc===uri && el.complete && el.naturalWidth>0;
   const background=cs.backgroundImage.includes(uri);
   return (image||background)&&r.width>=160&&r.height>=80 ? [{index,image,primary:Boolean(el.closest('header,.hero,#hero,[class*=hero]')),selector:el.id?'#'+el.id:el.tagName.toLowerCase()+'.'+[...el.classList].join('.')}] : [];
  }).slice(0,8);
 }""")
 if candidates is None:return
 if candidates and any(item['primary'] for item in candidates):candidates=[item for item in candidates if item['primary']]
 if not candidates:raise ValueError('Supplied hero artwork has no loaded image or CSS image area at least 160 by 80 pixels; use the supplied artwork visibly, preserving content.')
 diagnostics=[]
 for candidate in candidates:
  target=embedded.locator('body *').nth(candidate['index'])
  await target.scroll_into_view_if_needed()
  box=await target.bounding_box()
  if not box:continue
  before=await target.screenshot(animations='disabled',timeout=5000)
  saved=await target.get_attribute('style')
  try:
   await target.evaluate("(el,image)=>el.style.setProperty(image?'opacity':'background-image',image?'0':'none','important')",candidate['image'])
   after=await target.screenshot(animations='disabled',timeout=5000)
  finally:
   await target.evaluate("(el,s)=>s===null?el.removeAttribute('style'):el.setAttribute('style',s)",saved)
  first=Image.open(io.BytesIO(before)).convert('RGB');second=Image.open(io.BytesIO(after)).convert('RGB')
  difference=ImageChops.difference(first,second).convert('L')
  changed=sum(difference.histogram()[9:])/(first.width*first.height)
  if changed>=.005:return
  overlays=await target.evaluate("el=>{const r=el.getBoundingClientRect();return document.elementsFromPoint(r.x+r.width/2,r.y+r.height/2).slice(0,5).map(e=>({tag:e.tagName,classes:e.className,z:getComputedStyle(e).zIndex,background:getComputedStyle(e).backgroundColor}))}")
  diagnostics.append({'selector':candidate['selector'],'changed_fraction':round(changed,6),'overlays':overlays})
 raise ValueError('Loaded supplied hero contributes no visible artwork (under 0.5% changed crop pixels). Repair actual image positioning/z-index or the opaque .hero-fallback overlay; translucent gradients may remain. '+str(diagnostics))


async def audit_visual(page,frame):
 embedded=page.frames[-1]
 await embedded.add_script_tag(path=str(Path(__file__).resolve().parent/'vendor/axe/axe.min.js'))
 problems=[];seen_issues=set()
 for width in (1366,375):
  await page.set_viewport_size({'width':width+24,'height':950})
  await page.locator('iframe').evaluate('(el,w)=>el.style.width=w+"px"',width)
  await asyncio.sleep(.1)
  geometry=await frame.locator('body').evaluate('()=>({viewport:innerWidth,content:document.documentElement.scrollWidth,offenders:[...document.querySelectorAll("body *")].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.right>innerWidth+1}).slice(0,3).map(e=>({tag:e.tagName,id:e.id,classes:e.className,parent:e.parentElement?{classes:e.parentElement.className,display:getComputedStyle(e.parentElement).display,wrap:getComputedStyle(e.parentElement).flexWrap}:null}))})')
  if geometry['content']>geometry['viewport']+1:problems.append('Fix actual responsive overflow in HTML/CSS, preserving controls: '+str(geometry))
  result=await frame.locator('body').evaluate('async body=>await axe.run(body,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]}})')
  for violation in result['violations']:
   for node in violation['nodes']:
    # Each violating element class matters: reporting only nodes[0] hid the
    # reservation-date defect behind hotel-price in the same axe violation.
    classes=re.search(r'class=[\"\']([^\"\']+)',node['html'])
    identity=classes.group(1) if classes else node['html'][:100]
    key=(violation['id'],identity)
    if key in seen_issues:continue
    seen_issues.add(key)
    problems.append('Accessibility '+violation['id']+': '+str({'html':node['html'][:120],'why':node.get('failureSummary','')[:300]}))
 try:await check_artwork_visibility(embedded)
 except ValueError as error:problems.append(str(error))
 if problems:
  # Keep the same criteria, but disclose mobile overflow before duplicated a11y details.
  problems.sort(key=lambda problem:0 if problem.startswith('Fix actual responsive overflow') else 1)
  raise ValueError('Fix all measured desktop/mobile visual defects, preserving every feature: '+' | '.join(problems))

async def check_visual_frontend(code,data,stop=None):
 problems=[]
 for name,options in [('empty',{'interactions':False,'seed_reservation':False}),('reserved',{})]:
  try:await check_frontend(code,data/name,stop,visual=True,**options)
  except ValueError as error:problems.append(name+' state: '+str(error))
 if problems:raise ValueError(' | '.join(problems))


async def reveal_control(frame,control):
 if not await control.count():raise ValueError('Generated application lacks a required accessible control')
 if await control.is_visible():return
 ancestors=await control.evaluate('(x)=>{const ids=[];for(let p=x.parentElement;p;p=p.parentElement)if(p.id)ids.push(p.id);return ids}')
 for target in ancestors:
  link=frame.locator('a[href="#'+target+'"]')
  if await link.count():
   await link.first.focus();await link.first.press('Enter')
   if await control.is_visible():return
 # Button and tab navigation is as valid as an anchor; exercise the actual UI.
 for link in await frame.locator('nav button, nav [role=tab], [role=tablist] [role=tab]').all():
  if await link.is_visible():
   await link.focus();await link.press('Enter')
   if await control.is_visible():return
 raise ValueError('Generated navigation cannot reveal the requested control')

async def inventory_cards(listing):
 cards=listing.locator('article:visible,.hotel-card:visible,.property-card:visible,[role="listitem"]:visible')
 if not await cards.count():cards=listing.locator(':scope > *:visible')
 return await cards.evaluate_all('(xs)=>xs.filter(x=>!xs.some(y=>y!==x&&y.contains(x))).map(x=>({text:x.innerText,price:x.querySelector("[class*=price],[data-price]")?.textContent||""}))')

async def check_inventory(frame,hotels):
 city=frame.get_by_role('combobox',name=re.compile('city|destination|location',re.I),include_hidden=True).first
 sort=frame.get_by_role('combobox',name=re.compile('sort|order|price',re.I),include_hidden=True).first
 await reveal_control(frame,city)
 listing=frame.locator('#hotel-list,#hotels-list,#hotels-grid,#hotel-grid,.hotel-list,.hotels-grid').first
 if not await listing.count():raise ValueError('Generated inventory has no identifiable hotel-card list')
 options=await city.locator('option').evaluate_all('(xs)=>xs.map(x=>({value:x.value,text:x.textContent.trim()}))')
 chosen=next((o for o in reversed(options) if any(h['city'].lower()==o['text'].lower() or h['city'].lower()==o['value'].lower() for h in hotels)),None)
 if chosen is None:raise ValueError('City filter options must come from actual hotel inventory')
 selected=next(h['city'] for h in hotels if h['city'].lower() in (chosen['text'].lower(),chosen['value'].lower()))
 await city.select_option(chosen['value']);await asyncio.sleep(.2);cards=await inventory_cards(listing)
 if len(cards)!=sum(h['city']==selected for h in hotels) or not all(selected.lower() in c['text'].lower() for c in cards):raise ValueError('City filtering does not match actual hotel inventory')
 await city.select_option(options[0]['value']);await reveal_control(frame,sort)
 choices=await sort.locator('option').evaluate_all('(xs)=>xs.map(x=>({value:x.value,text:x.textContent}))')
 chosen=next((o for o in choices if re.search(r'desc|high.*low|highest|decreas',o['value']+' '+o['text'],re.I)),None)
 if chosen is None:raise ValueError('Price sorting must provide an accessible descending option')
 await sort.select_option(chosen['value']);await asyncio.sleep(.2);cards=await inventory_cards(listing)
 if len(cards)!=len(hotels):raise ValueError('Sorting lost hotel cards')
 prices=[]
 for card in cards:
  match=re.search(r'\d[\d,]*(?:\.\d+)?',card['price']) or re.search(r'[$€£]\s*(\d[\d,]*(?:\.\d+)?)',card['text'])
  if not match:raise ValueError('Rendered hotel price is missing. Prices are numbers: convert values with String(value) before HTML escaping; do not erase numeric values in escapeHtml. Preserve real inventory amounts and design.')
  prices.append(float((match.group(1) if match.lastindex else match.group(0)).replace(',','')))
 expected=sorted((float(h['price']) for h in hotels),reverse=True)
 if prices!=expected:raise ValueError('Rendered prices or descending sorting do not match the actual hotel prices')
