import re,uuid
from playwright.async_api import expect

async def reveal(frame,control):
 if await control.is_visible():return
 ancestors=await control.evaluate('(x)=>{const ids=[];for(let p=x.parentElement;p;p=p.parentElement)if(p.id)ids.push(p.id);return ids}')
 for target in ancestors:
  link=frame.locator('a[href="#'+target+'"]')
  if await link.count():
   await link.first.focus();await link.first.press('Enter')
   if await control.is_visible():return
 for link in await frame.locator('nav button, nav [role=tab], [role=tablist] [role=tab]').all():
  if await link.is_visible():
   await link.focus();await link.press('Enter')
   if await control.is_visible():return
 raise AssertionError('No working navigation reveals the requested control')

async def rendered_cards(listing):
 items=listing.locator('article:visible,.hotel-card:visible,.property-card:visible,[role="listitem"]:visible')
 if not await items.count():items=listing.locator(':scope > *:visible')
 return await items.evaluate_all('(xs)=>xs.filter(x=>!xs.some(y=>y!==x&&y.contains(x))).map(x=>({text:x.innerText,price:x.querySelector("[class*=price],[data-price]")?.textContent||""}))')

async def verify_travel(page,row,cycle):
 await page.locator('#technical-details').evaluate('(el)=>el.open=true');await page.click('[data-tab="build"]');await page.click('#preview-refresh');await page.wait_for_timeout(1800)
 frame=page.frame_locator('#preview');await frame.locator('body').wait_for();row['site_text']=(await frame.locator('body').inner_text())[:12000]
 row['controls']=await frame.locator('input,select,button').evaluate_all('(xs)=>xs.map(x=>({tag:x.tagName,id:x.id,type:x.type,text:x.textContent.slice(0,100)}))')
 assert len(row['site_text'])>100;assert await frame.locator('form').count()>0
 # Exercise the generated application via its real controls and isolated backend.
 bookings_link=frame.locator('a[href="#bookings"]')
 if await bookings_link.count():await bookings_link.first.click()
 guest='Fictional Acceptance '+uuid.uuid4().hex[:8]
 existing=await page.evaluate("async()=>{const s=await fetch('/api/devteam/run').then(r=>r.json());return fetch('/api/devteam/backend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'GET',path:'/bookings',body:{},run_id:s.id,version:s.versions.at(-1).version})}).then(r=>r.json())}")
 occupied={b.get('date') for b in existing.get('body',{}).get('bookings',[])}
 date=next(f'{year}-{month:02d}-{day:02d}' for year in range(2028,2031) for month in range(1,13) for day in range(1,29) if f'{year}-{month:02d}-{day:02d}' not in occupied)
 await reveal(frame,frame.get_by_role('textbox',name=re.compile('guest|your name|full name',re.I),include_hidden=True).first)
 await frame.get_by_role('textbox',name=re.compile('guest|your name|full name',re.I),include_hidden=True).first.fill(guest)
 await frame.locator('input[type=date]').first.fill(date)
 hotel=frame.locator('form select');
 if await hotel.count():
  options=await hotel.first.locator('option').evaluate_all('(xs)=>xs.map(x=>({value:x.value,disabled:x.disabled}))')
  option=next(o['value'] for o in options if o['value'] and not o['disabled']);await hotel.first.select_option(option)
 submit=frame.locator('form button[type=submit],form button:not([type]),form input[type=submit]').first
 def booking_response(r):
  try:return '/api/devteam/backend' in r.url and r.request.post_data_json.get('method')=='POST'
  except:return False
 async with page.expect_response(booking_response,timeout=30000) as response:await submit.click()
 booked=await (await response.value).json();assert booked['status'] in (200,201),booked
 await expect(frame.locator('body')).to_contain_text(guest,use_inner_text=True,timeout=15000)
 # Re-submit the same property and date. A real conflict must remain visible.
 await reveal(frame,frame.get_by_role('textbox',name=re.compile('guest|your name|full name',re.I),include_hidden=True).first)
 await frame.get_by_role('textbox',name=re.compile('guest|your name|full name',re.I),include_hidden=True).first.fill(guest)
 await frame.locator('input[type=date]').first.fill(date)
 if await hotel.count():await hotel.first.select_option(option)
 async with page.expect_response(booking_response,timeout=30000) as response:await submit.click()
 conflict=await (await response.value).json();assert conflict['status']==409,conflict
 await expect(frame.locator('body')).to_contain_text(re.compile(r'conflict|already|409|duplicate|reserved',re.I),use_inner_text=True,timeout=15000)
 row['booking']={'guest':guest,'date':date,'success':booked,'duplicate':conflict}
 # Reloading the tested product must retain the reservation in its own SQLite DB.
 await page.click('#preview-refresh');await page.wait_for_timeout(1000);bookings_link=frame.locator('a[href="#bookings"]');
 if await bookings_link.count():await bookings_link.first.click()
 await reveal(frame,frame.get_by_role('textbox',name=re.compile('guest|your name|full name',re.I),include_hidden=True).first)
 await expect(frame.locator('body')).to_contain_text(guest,use_inner_text=True,timeout=15000)
 assert not re.search(r'unknown\s+(hotel|property)',await frame.locator('body').inner_text(),re.I),'Persisted reservation lost its hotel name after refresh'
 row['persistent_booking']=True
 inventory_link=frame.locator('a[href="#inventory"]')
 if await inventory_link.count():await inventory_link.first.click()
 city=frame.get_by_role('combobox',name=re.compile('city|destination|location',re.I),include_hidden=True);sort=frame.get_by_role('combobox',name=re.compile('sort|order|price',re.I),include_hidden=True)
 if await city.count():await reveal(frame,city.first)
 if await city.count() and await city.first.evaluate('(x)=>x.tagName')=='SELECT':
  options=await city.first.locator('option').evaluate_all('(xs)=>xs.map(x=>x.value).filter(Boolean)');await city.first.select_option(options[-1]);row['city_filter_used']=options[-1]
 else:
  button=frame.get_by_role('button',name=re.compile('^(Frankfurt|Lisbon|Tokyo)$'))
  if await button.count():await button.first.click();row['city_filter_used']=await button.first.inner_text()
 assert row.get('city_filter_used'),'No usable city filtering control'
 inventory=await page.evaluate("async()=>{const s=await fetch('/api/devteam/run').then(r=>r.json());return fetch('/api/devteam/backend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'GET',path:'/hotels',body:{},run_id:s.id,version:s.versions.at(-1).version})}).then(r=>r.json())}")
 hotels=inventory['body']['hotels'];listing=frame.locator('#hotel-list,#hotels-list,#hotels-grid,#hotel-grid,.hotel-list,.hotels-grid').first;assert await listing.count(),'No hotel listing container'
 await page.wait_for_timeout(200);listing_text=await listing.inner_text();selected_city=row['city_filter_used']
 cards=await rendered_cards(listing);expected=[h for h in hotels if h['city'].lower()==selected_city.lower()]
 assert len(cards)==len(expected) and all(selected_city.lower() in c['text'].lower() for c in cards),'City filter did not match real inventory'
 row['filtered_card_count']=len(cards)
 row['city_filter_verified']=True
 if await city.count() and await city.first.evaluate('(x)=>x.tagName')=='SELECT':
  all_value=await city.first.locator('option').first.get_attribute('value');await city.first.select_option(all_value)
 else:
  all_button=frame.get_by_role('button',name=re.compile('^all( cities)?$',re.I));assert await all_button.count();await all_button.first.click()
 if await sort.count() and await sort.first.evaluate('(x)=>x.tagName')=='SELECT':
  options=await sort.first.locator('option').evaluate_all('(xs)=>xs.map(x=>({value:x.value,text:x.textContent}))');option=next((o['value'] for o in reversed(options) if re.search(r'price|high to low|low to high',o['value']+' '+o['text'],re.I)),None);assert option is not None,'No price sorting option';await sort.first.select_option(option);row['sort_used']=option;row['sort_label']=next(o['text'] for o in options if o['value']==option)
 else:
  button=frame.get_by_role('button',name=re.compile('price|sort',re.I));assert await button.count(),'No price sorting control';await button.first.click();row['sort_used']=True
 await page.wait_for_timeout(200);listing_text=await listing.inner_text();assert all(h['name'] in listing_text for h in hotels)
 cards=await rendered_cards(listing);assert len(cards)==len(hotels),'Sorted inventory lost hotel cards'
 prices=[]
 for card in cards:
  found=re.search(r'\d[\d,]*(?:\.\d+)?',card['price']) or re.search(r'[$€£]\s*(\d[\d,]*(?:\.\d+)?)',card['text'])
  assert found,'Rendered hotel price is missing'
  number=found.group(1) if found.lastindex else found.group(0);price=float(number.replace(',',''));assert price in [float(h['price']) for h in hotels],'Rendered price is not in the real inventory';prices.append(price)
 assert prices==sorted(prices,reverse=bool(re.search(r'desc|high.*low|highest|decreas',str(row['sort_used'])+' '+row.get('sort_label',''),re.I))),'Rendered hotel prices do not match the selected direction';row['sorted_prices_verified']=prices

 anchors=frame.locator('a[href^="#"]')
 for i in range(await anchors.count()):
  anchor=anchors.nth(i);target=await anchor.get_attribute('href');assert len(target)>1;assert await frame.locator('[id="'+target[1:]+'"]').count();await reveal(frame,anchor);await anchor.focus();await page.keyboard.press('Enter')
 row['navigation_tested']=await anchors.count()

