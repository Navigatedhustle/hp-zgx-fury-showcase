"""Trusted entrypoint executed ONLY inside the isolated namespace."""
import contextlib,importlib.util,io,json,os,resource,sys,unittest
resource.setrlimit(resource.RLIMIT_CPU,(6,6))
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
sys.path.insert(0,'/workspace');sys.dont_write_bytecode=True
payload=json.load(sys.stdin)
if sys.argv[1] in ('test','traveltest','travellist'):
 class Acceptance(unittest.TestCase):
  def test_frontend_navigation_targets(self):
   from pathlib import Path
   from html.parser import HTMLParser
   page=Path('/workspace/index.html')
   if not page.exists():return
   class Navigation(HTMLParser):
    def __init__(self):super().__init__();self.ids=set();self.fragments=[]
    def handle_starttag(self,tag,attrs):
     values=dict(attrs)
     if values.get('id'):self.ids.add(values['id'])
     if tag=='a' and values.get('href','').startswith('#'):self.fragments.append(values['href'][1:])
   parsed=Navigation();parsed.feed(page.read_text())
   for target in parsed.fragments:self.assertTrue(target and target in parsed.ids,'Navigation target missing: '+repr(target))
  def test_contract_and_conflict(self):
   import tempfile
   from backend import handle
   with tempfile.TemporaryDirectory() as folder:
    db=folder+'/acceptance.sqlite'
    hotels=handle({'method':'GET','path':'/hotels','body':{}},db)
    self.assertEqual(hotels['status'],200);self.assertGreater(len(hotels['body']['hotels']),0)
    hid=hotels['body']['hotels'][0]['id']
    invalid=handle({'method':'POST','path':'/bookings','body':{'hotel_id':hid,'date':'2027-01-05'}},db)
    self.assertGreaterEqual(invalid['status'],400)
    req={'method':'POST','path':'/bookings','body':{'hotel_id':hid,'guest':'Fictional Guest','date':'2027-01-05'}}
    self.assertIn(handle(req,db)['status'],(200,201));self.assertEqual(handle(req,db)['status'],409)
    self.assertEqual(handle({'method':'GET','path':'/bookings','body':{}},db)['status'],200)
  def test_exact_public_status_contract(self):
   import tempfile
   from backend import handle
   with tempfile.TemporaryDirectory() as folder:
    db=folder+'/status.sqlite'
    hotels=handle({'method':'GET','path':'/hotels','body':{}},db)
    self.assertEqual(hotels['status'],200);self.assertEqual(len(hotels['body']['hotels']),5)
    hid=hotels['body']['hotels'][0]['id']
    for unknown in (99,999):
     reply=handle({'method':'POST','path':'/bookings','body':{'hotel_id':unknown,'guest':'Fictional Guest','date':'2028-01-05'}},db)
     self.assertEqual(reply['status'],404,'Every unknown numeric hotel ID must return404')
    req={'method':'POST','path':'/bookings','body':{'hotel_id':hid,'guest':'Fictional Guest','date':'2028-01-05'}}
    self.assertEqual(handle(req,db)['status'],201,'New bookings return201')
    self.assertEqual(handle(req,db)['status'],409)
    for body in ({'hotel_id':hid,'guest':'','date':'2028-01-06'},{'hotel_id':hid,'guest':'Fictional Guest','date':'2027-02-30'}):
     self.assertEqual(handle({'method':'POST','path':'/bookings','body':body},db)['status'],400)
  def test_calendar_validation(self):
   import tempfile
   from backend import handle
   with tempfile.TemporaryDirectory() as folder:
    db=folder+'/calendar.sqlite'
    hid=handle({'method':'GET','path':'/hotels','body':{}},db)['body']['hotels'][0]['id']
    for day in ('2027-02-30','2027-02-29','2027-13-01','not-a-date'):
     reply=handle({'method':'POST','path':'/bookings','body':{'hotel_id':hid,'guest':'Fictional Guest','date':day}},db)
     self.assertGreaterEqual(reply['status'],400,day)
    valid=handle({'method':'POST','path':'/bookings','body':{'hotel_id':hid,'guest':'Fictional Guest','date':'2028-02-29'}},db)
    self.assertIn(valid['status'],(200,201))
 observed_rejections=[]
 if sys.argv[1]=='traveltest' and os.path.isfile('/workspace/backend.py'):
  import backend
  actual_handle=backend.handle
  def observed_handle(request,db_path):
   reply=actual_handle(request,db_path)
   if isinstance(request,dict) and isinstance(reply,dict) and reply.get('status',0)>=400:
    body=request.get('body');body=body if isinstance(body,dict) else {}
    observation={'method':request.get('method'),'path':request.get('path'),'status':reply.get('status'),'error':str(reply.get('body',{}).get('error',''))[:200],'input':{k:body[k] for k in ('listing_id','check_in','check_out','party') if k in body}}
    if request.get('path') in ('/quote','/reservations') and type(body.get('listing_id')) is int:
     listing=actual_handle({'method':'GET','path':'/listings/'+str(body['listing_id']),'body':{}},db_path).get('body',{}).get('listing',{})
     observation['actual_listing']={k:listing[k] for k in ('id','capacity','active') if k in listing}
    observed_rejections.append(observation);del observed_rejections[:-4]
   return reply
  backend.handle=observed_handle
 suite=unittest.defaultTestLoader.discover('/workspace',pattern='test_*.py')
 def flatten(suite):
  return [case for item in suite for case in (flatten(item) if isinstance(item,unittest.TestSuite) else [item])]
 if sys.argv[1] in ('traveltest','travellist'):
  # Plain zero-argument assertion functions need no pytest dependency. Execute
  # them as real unittest cases under the same resource/isolation limits.
  import inspect,importlib
  from pathlib import Path
  for file in Path('/workspace').glob('test_*.py'):
   module=importlib.import_module(file.stem)
   for name,value in vars(module).items():
    if name.startswith('test_') and inspect.isfunction(value) and not inspect.signature(value).parameters:suite.addTest(unittest.FunctionTestCase(value))
 if sys.argv[1]=='travellist':
  print(json.dumps({'tests':[case.id() for case in flatten(suite)]}));sys.exit(0)
 if sys.argv[1]=='traveltest' and payload.get('tests'):
  selected=set(payload['tests']);suite=unittest.TestSuite(case for case in flatten(suite) if case.id() in selected)
 if sys.argv[1]=='test':suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance))
 log=io.StringIO()
 with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
 diagnostic='\nActual rejected API calls (credentials omitted; invalid-input cases may be intentional): '+json.dumps(observed_rejections) if observed_rejections else ''
 if sys.argv[1]=='traveltest' and not result.wasSuccessful():
  import ast
  from pathlib import Path
  try:
   tree=ast.parse(Path('/workspace/test_backend.py').read_text());bad=[];past=[];oversized=[]
   from datetime import date
   for node in ast.walk(tree):
    if isinstance(node,ast.Dict):
     for key,value in zip(node.keys,node.values):
      if isinstance(key,ast.Constant) and key.value=='page_size' and isinstance(value,ast.Constant) and type(value.value) is int and value.value>12:oversized.append(value.value)
      if isinstance(key,ast.Constant) and key.value=='check_in' and isinstance(value,ast.Constant) and isinstance(value.value,str):
       try:
        if date.fromisoformat(value.value)<date.today():past.append(value.value)
       except ValueError:pass
      if isinstance(key,ast.Constant) and key.value=='request_key' and isinstance(value,ast.Constant) and isinstance(value.value,str) and len(value.value)<8:bad.append(value.value)
   if bad:diagnostic+='\nFixture diagnostic: generated QA supplies request_key strings shorter than the immutable minimum8: '+repr(sorted(set(bad)))+'. These inputs correctly return400. Use valid keys of8..100 characters for intended successful, duplicate and ownership scenarios; preserve assertions and all test cases.'
   if past:diagnostic+='\nDate fixture diagnostic: current date is '+str(date.today())+'; literal check-in dates '+repr(sorted(set(past)))+' are past. For intended successful quotes/reservations use date.today()+timedelta(days=90), preserving intentional past-date rejection tests.'
   if oversized:diagnostic+='\nPagination fixture diagnostic: successful listing requests require page_size1..12; observed larger literal fixtures '+repr(sorted(set(oversized)))+'. Preserve invalid-pagination rejection cases; do not use oversized pages for success/sorting tests.'
   try:
    from backend import handle
    observed={}
    for city in ('Lisbon','Kyoto','Copenhagen','Edinburgh','Porto','Ljubljana'):
     reply=handle({'method':'GET','path':'/listings','body':{'city':city,'page_size':12}},'/data/qa-diagnostic.sqlite')
     observed[city]={'status':reply.get('status'),'total':reply.get('body',{}).get('total')}
    diagnostic+='\nActual generated catalog filter observations (read-only API, not invented counts): '+json.dumps(observed)
   except Exception as e:diagnostic+='\nCatalog diagnostic unavailable: '+str(e)[:200]
   diagnostic+='\nCatalog contract reminder: seed >=18 properties across6 cities; exact per-city counts are not fixed at5. Verify filtered rows and actual bounded catalog values, not invented city totals.'
  except (OSError,SyntaxError):pass
 print(json.dumps({'passed':result.wasSuccessful() and result.testsRun>0,'tests':result.testsRun,'log':log.getvalue()[-12000:]+diagnostic}))
else:
 spec=importlib.util.spec_from_file_location('generated_backend','/workspace/backend.py');module=importlib.util.module_from_spec(spec)
 log=io.StringIO()
 with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
  spec.loader.exec_module(module)
  if sys.argv[1]=='travelroutes':
   import importlib
   database=importlib.import_module('db')
   owners=[]
   with contextlib.closing(database.connect('/data/route-probe.sqlite')) as conn:
    for name in ('auth','catalog','private','reservations'):
     candidate=importlib.import_module(name).routes(conn,payload)
     if candidate is not None:owners.append({'file':name+'.py','status':candidate.get('status') if isinstance(candidate,dict) else 'invalid'})
   reply={'interceptors':owners}
  elif sys.argv[1]=='resources':
   import gc
   gc.collect();enabled=gc.isenabled();gc.disable()
   try:
    before=len(os.listdir('/proc/self/fd'))
    for index in range(8):
     for path in ('/hotels','/bookings'):module.handle({'method':'GET','path':path,'body':{}},'/data/bookings.sqlite')
    opened=len(os.listdir('/proc/self/fd'))-before
   finally:
    if enabled:gc.enable()
    gc.collect()
   reply={'passed':opened<=2,'opened_fds':opened,'calls':16}
  else:reply=module.handle(payload,'/data/bookings.sqlite')
 print(json.dumps(reply))
