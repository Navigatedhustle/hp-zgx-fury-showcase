"""Independent checks execute actual generated code through existing sandbox."""
import uuid,asyncio
from datetime import date,timedelta
from devteam_sandbox import execute

class RoutingContractError(AssertionError):
 def __init__(self,message,files):super().__init__(message);self.files=files

def check_product(code,data,stop=None):
 results=[];last_request=['']
 def call(method,path,body=None,token=None):
  if stop is not None and stop.is_set():raise asyncio.CancelledError()
  last_request[0]=method+' '+path+' '+repr({} if path in ('/register','/login') else (body or {}))
  return execute(code,data,'api',{'method':method,'path':path,'body':body or {},'headers':{'authorization':'Bearer '+token} if token else {}})
 def expect(response,status):
  assert response.get('status')==status, f'{last_request[0]}: expected status {status}; actual {response}'
  assert isinstance(response.get('body'),dict), 'Response body must be a dictionary'
  return response['body']
 def group(key,fn):
  try:fn();results.append({'id':key,'passed':True})
  except Exception as e:
   item={'id':key,'passed':False,'error':str(e)[:2500]}
   if key=='auth' and 'No item with that key' in str(e):
    item['error']+=' SQLite Row lookup failed: compare SELECT projections with every later row[key] access. The login response reads user id, email and role; its query must include email as well as the password/salt fields (or use the validated email value). Preserve the exact schema and expected statuses.'
   if isinstance(e,RoutingContractError):item['repair_files']=e.files
   results.append(item)
 context={}
 def catalog():
  expect(call('GET','/health'),200)
  b=expect(call('GET','/listings'),200);assert b['total']>=18 and len(b['listings'])==6
  context['listing']=b['listings'][0]
  assert expect(call('GET','/listings'),200)['total']==b['total'], 'Inventory grows on repeated initialization: seed explicit stable primary IDs with INSERT OR IGNORE, never insert auto IDs each request'
  city=b['listings'][0]['city'];filtered=expect(call('GET','/listings',{'city':city}),200)
  assert filtered['listings'] and all(x['city']==city for x in filtered['listings'])
  for sort in ('price_asc','price_desc'):
   rows=expect(call('GET','/listings',{'sort':sort,'page_size':12}),200)['listings'];prices=[x['price'] for x in rows];assert prices==sorted(prices,reverse=sort=='price_desc')
  assert expect(call('GET','/listings',{'q':'zzzznonexistent'}),200)['listings']==[]
  assert not set(x['id'] for x in b['listings']) & set(x['id'] for x in expect(call('GET','/listings',{'page':2}),200)['listings'])
  expect(call('GET','/listings/'+str(context['listing']['id'])),200)
  expect(call('GET','/listings',{'party':0}),400)
  for price in (-1,True,float('inf'),float('nan')):expect(call('GET','/listings',{'max_price':price}),400)
 def routing():
  for method,path in [('GET','/nonexistent'),('POST','/listings')]:
   reply=call(method,path)
   if reply.get('status')!=404:
    probe=execute(code,data/'route-probe','travelroutes',{'method':method,'path':path,'body':{},'headers':{}})
    owners=[item['file'] for item in probe.get('interceptors',[])]
    raise RoutingContractError(method+' '+path+' must return404; actual '+str(reply.get('status'))+'. Modules intercepting an unrelated path/method: '+str(owners)+'. Check path AND method before authentication and return None when unrelated. Generated QA expecting404 is correct; do not weaken it.',owners or ['backend.py'])
 def auth():
  suffix=uuid.uuid4().hex[:10];context['email']='user'+suffix+'@example.test'
  expect(call('POST','/register',{'email':'bad','password':'x'}),400)
  for key in ('a','b'):
   credentials={'email':key+context['email'],'password':'ExamplePass2028!'}
   b=expect(call('POST','/register',credentials),201);assert b['user']['role']=='user';context[key]=b['token']
   expect(call('POST','/register',credentials),409)
   logged=expect(call('POST','/login',credentials),200);expect(call('GET','/me',token=logged['token']),200)
  # Verify revocation itself across new sandbox processes; repeat-logout
  # idempotency does not determine whether a session is actually revoked.
  revoked=expect(call('POST','/login',{'email':'a'+context['email'],'password':'ExamplePass2028!'}),200)['token']
  expect(call('POST','/logout',token=revoked),200)
  expect(call('GET','/me',token=revoked),401)
  expect(call('GET','/favorites',token=revoked),401)
  repeated=call('POST','/logout',token=revoked)
  assert repeated.get('status') in (200,401), 'Repeated logout must be idempotent200 or unauthorized401'
  expect(call('GET','/me'),401)
  expect(call('POST','/login',{'email':'a'+context['email'],'password':'incorrect'}),401)
  context['admin']=expect(call('POST','/login',{'email':'admin@example.test','password':'DemoAdmin2028!'}),200)['token']
 def private():
  a,b=context['a'],context['b'];lid=context['listing']['id']
  expect(call('GET','/favorites'),401)
  saved=call('POST','/favorites',{'listing_id':lid},a);assert saved.get('status') in (200,201), saved
  assert expect(call('GET','/favorites',token=a),200)['favorites'];assert not expect(call('GET','/favorites',token=b),200)['favorites']
  expect(call('DELETE','/favorites/'+str(lid),token=a),200)
  i=expect(call('POST','/itineraries',{'title':'Coastal discovery','notes':'Train and gardens'},a),201)['itinerary']['id']
  expect(call('PUT',f'/itineraries/{i}',{'title':'Edited journey','notes':'Museum'},b),404)
  expect(call('DELETE',f'/itineraries/{i}',token=b),404)
  expect(call('PUT',f'/itineraries/{i}',{'title':'Edited journey','notes':'Museum'},a),200)
  assert any(x['title']=='Edited journey' for x in expect(call('GET','/itineraries',token=a),200)['itineraries'])
  expect(call('DELETE',f'/itineraries/{i}',token=a),200)
 def reservation():
  a,b=context['a'],context['b'];start=date.today()+timedelta(days=90)
  details={'listing_id':context['listing']['id'],'check_in':str(start),'check_out':str(start+timedelta(days=3)),'party':1}
  q=expect(call('POST','/quote',details),200)['quote'];assert q['total']==context['listing']['price']*3 and q['nights']==3
  for change in ({'check_in':'2027-02-30'},{'check_in':str(date.today()-timedelta(days=1))},{'check_out':details['check_in']},{'party':0},{'party':True},{'party':99}):expect(call('POST','/quote',{**details,**change}),400)
  details.update(request_key=uuid.uuid4().hex,total=1)
  expect(call('POST','/reservations',details),401)
  r=expect(call('POST','/reservations',details,a),201)['reservation'];assert r['total']==q['total'];context['reservation']=r
  expect(call('POST','/reservations',details,a),409)
  expect(call('GET',f"/reservations/{r['id']}",token=b),404)
  assert any(x['id']==r['id'] for x in expect(call('GET','/reservations',token=a),200)['reservations'])
  context['persist']={'token':a,'reservation_id':r['id']}
 def admin():
  expect(call('GET','/admin/reservations'),401);expect(call('GET','/admin/reservations',token=context['a']),403)
  rows=expect(call('GET','/admin/reservations',token=context['admin']),200)['reservations'];assert isinstance(rows,list)
  if context.get('reservation'):assert any(x['id']==context['reservation']['id'] for x in rows), 'Admin cannot see the actual newly created reservation'
  assert all('password' not in x and 'token' not in x for x in rows)
  lid=context['listing']['id'];expect(call('PUT',f'/admin/listings/{lid}',{'price':222,'active':1},context['a']),403)
  expect(call('PUT',f'/admin/listings/{lid}',{'price':222,'active':1},context['admin']),200)
  assert expect(call('GET',f'/listings/{lid}'),200)['listing']['price']==222
  expect(call('PUT',f'/admin/listings/{lid}',{'price':context['listing']['price'],'active':1},context['admin']),200)
 for key,fn in [('catalog',catalog),('routing',routing),('auth',auth),('private',private),('reservation',reservation),('admin',admin)]:group(key,fn)
 return {'passed':all(x['passed'] for x in results),'checks':results,'persistence_probe':context.get('persist'),'log':'\n'.join(x['id']+': '+('PASS' if x['passed'] else x['error']) for x in results)}
