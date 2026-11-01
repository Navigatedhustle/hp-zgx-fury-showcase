"""Small durable extension of Factory, retaining its gateway and namespace runner."""
import asyncio,ast,copy,json,logging,threading,time,hashlib,re
import httpx
import devteam
from devteam import DevRun,LEAD,SPECIALIST,copy_workspace,parse_patch
from devteam_sandbox import available,check_javascript,execute
from travel_spec import CONTRACT,CRITERIA,TASKS
from travel_checks import check_product

# Explicit bounded source ownership; no generated shell commands or host tools.
FILE_SCOPES={};READ_SCOPES={}
for title,name,_ in TASKS:
 devteam.ALLOWED.add(name);FILE_SCOPES[title]={name}
 READ_SCOPES[title]={'architecture.md','db.py','auth.py','backend.py'} if name.endswith('.py') else {'index.html','styles.css','architecture.md'}
for name in ('backend.py','auth.py','catalog.py','private.py','reservations.py','db.py','app.js','index.html','styles.css','test_backend.py'):
 title='Repair '+name;FILE_SCOPES[title]={name};READ_SCOPES[title]={'index.html'} if name in ('app.js','styles.css') else {'app.js'} if name=='index.html' else set()

FILE_SCOPES['Travel frontend diagnosis']={'contract_review.md'}
READ_SCOPES['Travel frontend diagnosis']={'app.js','index.html'}
READ_SCOPES['Repair app.js'].add('contract_review.md')
# Authentication failures can originate in an earlier dispatcher module.
for name in ('private.py','reservations.py'):
 READ_SCOPES['Repair '+name].update({'backend.py','auth.py','private.py','reservations.py'}-{name})

def qa_contract_diagnostics(source):
 """Observations, not verdicts: invalid-method tests may intentionally expect404."""
 try:tree=ast.parse(source)
 except SyntaxError:return ''
 lines=[]
 for node in ast.walk(tree):
  if not isinstance(node,ast.Call) or not node.args:continue
  if isinstance(node.args[0],ast.Dict):
   fields={key.value:value for key,value in zip(node.args[0].keys,node.args[0].values) if isinstance(key,ast.Constant)}
   method,path=fields.get('method'),fields.get('path')
  elif len(node.args)>=2:method,path=node.args[:2]
  else:continue
  if not all(isinstance(n,ast.Constant) and isinstance(n.value,str) for n in (method,path)):continue
  if path.value=='/listings' and method.value in {'POST','PUT','PATCH','DELETE'}:lines.append('line '+str(node.lineno)+': '+method.value+' /listings is not a public route (404). Successful filtering/search/sort/pagination MUST call GET /listings with a native dict body, even though method is GET. Preserve intentionally invalid-method tests expecting404.')
 return '\n'.join(lines)


def repair_targets(failure):
 if failure['id']=='routing':return [name for name in failure.get('repair_files',[]) if name in {'auth.py','catalog.py','private.py','reservations.py','backend.py'}] or ['backend.py']
 if failure['id']=='reservation' and '/quote' in str(failure.get('error','')) and "'status': 401" in str(failure.get('error','')):
  return ['private.py','reservations.py','backend.py','auth.py']
 return []


def acceptance_signature(failures):
 """Ignore traceback location/timing churn while retaining failure semantics."""
 stable=[]
 for failure in failures:
  error=str(failure.get('error',''))
  if failure['id']=='qa':
   tests=re.findall(r'^(?:FAIL|ERROR): (.+)$',error,re.M)
   causes=re.findall(r'^(?:AssertionError|[A-Za-z_]+Error): (.+)$',error,re.M)
   if tests and causes:error=json.dumps([sorted(tests),sorted(causes)])
  error=error.split(' Recent actual API execution:')[0].split(' Console:')[0].split('Call log:')[0]
  error=re.sub(r'File "[^"\n]+", line \d+', 'File [source], line [location]',error)
  error=re.sub(r'Ran \d+ tests? in [0-9.]+s','Ran [tests] in [elapsed]',error)
  stable.append((failure['id'],error))
 return hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()

class TravelRun(DevRun):
 travel=True;contract=CONTRACT;file_scopes=FILE_SCOPES;read_scopes=READ_SCOPES
 design='Premium editorial travel product, warm ivory and deep teal, destination illustrations, strong typography and mobile-first accessible forms. Follow every acceptance hook in the immutable contract.'
 def __init__(self,**kwargs):
  super().__init__(automatic=True,**{k:v for k,v in kwargs.items() if k!='automatic'})
  self.tasks=[{'id':'travel-'+str(i),'title':title,'actor':'daniel' if name.endswith('.py') or name.endswith('.md') else 'maya','model':LEAD if name.endswith('.py') or name.endswith('.md') else SPECIALIST,'dependencies':[],'owns':[name],'reads':sorted(READ_SCOPES[title]),'status':'pending'} for i,(title,name,_) in enumerate(TASKS)]
  self.product={'specification':CONTRACT,'criteria':[{'id':k,'description':v,'passed':False} for k,v in CRITERIA],'next_action':self.tasks[0]['title'],'decisions':['Single SQLite database per run; networkless Python backend; same-origin bridge; no external infrastructure'],'failures':[],'repair_pass':0}
  from travel_ui import install_frontend
  foundation=install_frontend(self.candidate)
  if foundation:
   self.product['frontend_foundation']=foundation
   for task in self.tasks:
    if task['owns'][0] in foundation['files']:task.update(status='merged',source='maintained frontend foundation')
   self.event('frontend foundation installed',**foundation)
  previous=None
  for task in self.tasks:
   if task.get('source'):continue
   task['dependencies']=[previous] if previous else []
   previous=task['title']
  self.save()
 def save(self):
  super().save()
  if hasattr(self,'product'):
   tmp=self.root/'project-state.tmp';tmp.write_text(json.dumps({'product':self.product,'tasks':self.tasks,'started':self.started,'travel':True},indent=2));tmp.replace(self.root/'project-state.json')
   (self.root/'SPEC.md').write_text(CONTRACT)
 def publish_development_preview(self,smoke):
  if not smoke.get('passed') or not self.tests or not self.tests.get('passed'):return
  if any(v.get('stage')=='accepted' or v.get('title')=='Full travel acceptance' for v in self.versions):return
  digest=hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sorted(self.candidate.iterdir()) if p.is_file() and p.name in devteam.ALLOWED)).hexdigest()
  if self.versions and self.versions[-1]['hash']==digest:return
  self.promote('Development preview: API tests and browser bootstrap passed')
  self.versions[-1]['stage']='development';self.event('development preview available',version=self.versions[-1]['version'],full_acceptance=False)
 def snapshot(self,compact=False):
  data=super().snapshot(compact=compact);data['travel']=True;data['product']=copy.deepcopy(getattr(self,'product',{}));data['application_url']='/travel/'+self.id
  if self.started and self.state in ('finished','blocked','stopped'):
   ended=max((e['time'] for e in self.events if e.get('kind')=='terminal' and e.get('state')==self.state),default=time.time());data['elapsed_s']=ended-self.started
  data['cumulative_tokens']=sum(c['usage'].get('total_tokens',0) for c in self.calls if c.get('usage'))
  return devteam.json_safe(data)
 def stop(self):
  self.recover_after_restart=False;super().stop()
  self.product['next_action']='Stopped: progress saved. Resume retained run to continue.';self.save()
 def interrupt(self):
  self.recover_after_restart=True;super().stop()
 def start(self):
  self.recover_after_restart=False;self.stop_event.clear();self.error='';self.started=self.started or time.time();self.state='running';self.save();self.thread=threading.Thread(target=self._thread,daemon=True);self.thread.start()
 def _thread(self):
  try:asyncio.run(self.work())
  except asyncio.CancelledError:self.state='interrupted' if getattr(self,'recover_after_restart',False) else 'stopped'
  except Exception as e:
   if self.stop_event.is_set():self.state='interrupted' if getattr(self,'recover_after_restart',False) else 'stopped';self.error=''
   else:self.state='blocked';self.error=str(e)[:3000];logging.exception('Travel development blocked %s',self.id)
  finally:self.event('terminal',state=self.state,error=self.error)
 async def ticket(self,client,title,name,prompt,task):
  if self.stop_event.is_set():raise asyncio.CancelledError()
  if name=='app.js':prompt+=' Return complete app.js compactly within22000 characters: remove redundant comments/blank lines before editing logic, without removing any behavior.'
  task.update(status='generating');self.product['next_action']=title;self.event('task handoff',task_id=task['id'],title=title,files=[name])
  feedback='';repair_source=self.candidate
  for attempt in range(3):
   try:
    patch=await self.call(client,title,task['actor'],task['model'],prompt+'\n'+feedback,source=repair_source,task_id=task['id'])
    if set(patch['files'])!={name}:raise ValueError('Return exactly the owned file '+name)
    content=patch['files'][name]
    staging=self.root/('ticket-candidate-'+task['id']+'-'+devteam.uuid.uuid4().hex[:8])
    devteam.copy_workspace(self.candidate,staging);(staging/name).write_text(content)
    repair_source=staging
    if name.endswith('.py'):ast.parse(content,filename=name)
    if name=='app.js':await asyncio.to_thread(check_javascript,staging)
    if name=='backend.py':
     probe=await asyncio.to_thread(execute,staging,self.root/('integration-check-'+devteam.uuid.uuid4().hex[:8]),'api',{'method':'GET','path':'/health','body':{},'headers':{}})
     if probe.get('status')!=200:raise ValueError('Backend integration must import its declared modules and answer GET /health with status200 before merge; actual '+str(probe))
     self.event('backend bootstrap checked',task_id=task['id'],passed=True,summary='Backend starts and answers its health check')
    self.apply(patch,actor=task['actor'],task_id=task['id'],call_id=self.calls[-1]['id']);task['status']='merged';self.event('task merged',title=title,task_id=task['id']);return
   except (ValueError,RuntimeError,SyntaxError,httpx.HTTPError,TimeoutError) as e:
    feedback='Previous attempt failed: '+str(e)[:2500]+'. Change approach: simplify and keep complete file compact; preserve all requirements.'
    self.event('repair required',title=title,attempt=attempt+1,error=feedback)
  task['status']='blocked';raise RuntimeError(title+' failed after three different repair requests: '+feedback)
 async def generated_qa(self,n):
  if self.stop_event.is_set():raise asyncio.CancelledError()
  try:names=(await asyncio.to_thread(execute,self.candidate,self.root/('qa-'+str(n)),'travellist')).get('tests',[])
  except (RuntimeError,ValueError) as e:return {'passed':False,'tests':0,'log':'Generated QA discovery failed; repair its imports/setup: '+str(e)[-7000:]}
  if not 1<=len(names)<=64:return {'passed':False,'tests':0,'log':'Generated QA must contain1..64 bounded test cases'}
  rows=[]
  for index,name in enumerate(names,1):
   self.product['next_action']='Running generated test '+str(index)+'/'+str(len(names))+': '+name
   self.event('test case started',name=name,index=index,total=len(names))
   if self.stop_event.is_set():raise asyncio.CancelledError()
   try:result=await asyncio.to_thread(execute,self.candidate,self.root/('qa-'+str(n)),'traveltest',{'tests':[name]})
   except RuntimeError as e:result={'passed':False,'tests':1,'log':str(e)}
   rows.append(result);self.event('test case executed',name=name,**result)
  return {'passed':all(x.get('passed') for x in rows),'tests':sum(x.get('tests',0) for x in rows),'log':'\n'.join(x.get('log','').split('Date fixture diagnostic:')[0].split('Actual generated catalog filter observations')[0].strip() for x in rows if not x.get('passed'))[-8000:]}
 async def work(self):
  revision=hashlib.sha256(b''.join((__import__('pathlib').Path(__file__).with_name(n)).read_bytes() for n in ('travel_run.py','travel_browser.py','travel_spec.py','travel_checks.py','devteam.py'))).hexdigest()
  if self.product.get('orchestration_revision')!=revision:
   if self.product.get('stagnant_passes',0)>=2 and any(x['id']=='browser' for x in self.product.get('failures',[])) and self.product.get('lead_frontend_reviews',0)<2:self.product['pending_lead_review']=True
   self.product.update(orchestration_revision=revision,stagnant_passes=0,failure_signature=None);self.event('orchestration revision',sha256=revision,reason='Re-evaluate retained project after controller or acceptance repair; completed files remain intact')
  if self.product.get('specification')!=self.contract:
   self.product['specification']=self.contract;self.event('specification clarified',reason='Observed implementation defects clarified existing acceptance; no weaker criteria')
  if not available():raise RuntimeError('Linux bubblewrap unavailable; generated code cannot execute')
  async with httpx.AsyncClient(timeout=360,trust_env=False) as client:
   for task,(title,name,prompt) in zip(self.tasks,TASKS):
    if task['status']=='merged' and (self.candidate/name).is_file():continue
    await self.ticket(client,title,name,prompt,task)
   # Independent acceptance, then selective repairs from actual failures. No token budget.
   while True:
    if self.stop_event.is_set():raise asyncio.CancelledError()
    if __import__('shutil').disk_usage(self.root).free<20*1024**3:raise RuntimeError('Development blocked: less than20GiB storage headroom; project and preview retained')
    n=self.product['repair_pass'];self.product['next_action']='Independent backend and browser acceptance';self.event('checks started',pass_number=n)
    import importlib,travel_checks
    importlib.reload(travel_checks)
    self.tests=await asyncio.to_thread(travel_checks.check_product,self.candidate,self.root/('acceptance-'+str(n)),self.stop_event)
    if self.stop_event.is_set():raise asyncio.CancelledError()
    generated=await self.generated_qa(n)
    self.tests['generated_qa']=generated
    self.event('generated tests executed',**generated)
    if not generated.get('passed'):self.tests['checks'].append({'id':'qa','passed':False,'error':generated.get('log','')[-3500:]})
    self.tests['passed']=self.tests['passed'] and generated.get('passed',False)
    self.product['failures']=[x for x in self.tests['checks'] if not x['passed']]
    for c in self.product['criteria']:
     match=next((x for x in self.tests['checks'] if x['id']==c['id']),None)
     if match:c['passed']=match['passed']
    self.event('acceptance results',**self.tests)
    if self.tests['passed']:
     import travel_browser
     importlib.reload(travel_browser)
     if not any(v.get('stage')=='accepted' or v.get('title')=='Full travel acceptance' for v in self.versions):
      smoke=await travel_browser.check_browser(self.candidate,self.root/('preview-smoke-'+str(n)),self.stop_event,smoke=True)
      self.event('preview bootstrap checked',**smoke);self.publish_development_preview(smoke)
     browser=await travel_browser.check_browser(self.candidate,self.root/('browser-'+str(n)),self.stop_event)
     self.tests['browser']=browser;self.product['criteria'][5]['passed']=browser['passed']
     self.event('browser acceptance',**browser)
     if browser['passed']:
      # New sandbox processes on every API invocation are a stronger restart boundary
      # than a warmed generated app process. Verify persisted reservation explicitly.
      probe=self.tests['persistence_probe'];reply=await asyncio.to_thread(execute,self.candidate,self.root/('acceptance-'+str(n)),'api',{'method':'GET','path':'/reservations/'+str(probe['reservation_id']),'body':{},'headers':{'authorization':'Bearer '+probe['token']}})
      if reply.get('status')!=200:raise RuntimeError('Persistence across generated process restart failed')
      self.product['criteria'][6]['passed']=True;self.tests['passed']=True;self.promote('Full travel acceptance');self.versions[-1]['stage']='accepted';self.state='finished';self.product['next_action']='All acceptance criteria passed';self.save();return
     self.product['failures']=[{'id':'browser','error':browser['error']+' Console: '+json.dumps(browser.get('console_errors',[]))+' Body: '+browser.get('body','')[:1000]}]
    errors=json.dumps(self.product['failures'])
    signature=acceptance_signature(self.product['failures'])
    self.product['stagnant_passes']=self.product.get('stagnant_passes',0)+1 if signature==self.product.get('failure_signature') else 0
    self.product['failure_signature']=signature
    if self.product['stagnant_passes']>=2 or (self.product.get('pending_lead_review') and any(x['id']=='browser' for x in self.product['failures'])):
     self.product['pending_lead_review']=False
     if any(x['id']=='browser' for x in self.product['failures']) and self.product.get('lead_frontend_reviews',0)<2:
      review={'id':'lead-diagnosis-'+str(n),'title':'Travel frontend diagnosis','actor':'daniel','model':LEAD,'owns':['contract_review.md'],'dependencies':[],'status':'pending'};self.tasks.append(review)
      await self.ticket(client,'Travel frontend diagnosis','contract_review.md','Review the actual complete JavaScript, structural HTML and observed browser failures: '+errors[:2000]+'. If no request was observed after a click, trace the measured last action and delegated selector matches FIRST; do not guess backend response defects for an endpoint never called. Check that closest() includes EVERY action attribute and branch conditions distinguish data-view from other actions; convert dataset IDs to integers. Diagnose ALL integration defects, including hidden vs active CSS states, nested response.body.listing/quote records, numeric IDs, navigation/data loading, event binding and real form controls. Write concise actionable function-level fixes in contract_review.md, <=400 words. Do not change app code or tests or claim tests ran.',review)
      self.product['lead_frontend_reviews']=self.product.get('lead_frontend_reviews',0)+1;self.product['stagnant_passes']=0
     else:raise RuntimeError('The same acceptance failure persisted through three repair approaches: '+errors)
    self.product['repair_pass']+=1;self.save()
    # Only implicated modules; keep complete files out of unrelated model contexts.
    failed={x['id'] for x in self.product['failures']}
    files=[]
    for failure in self.product['failures']:files.extend(repair_targets(failure))
    for key,names in [('catalog',['db.py','catalog.py']),('auth',['db.py','auth.py']),('private',['private.py']),('reservation',['reservations.py']),('admin',['catalog.py','reservations.py']),('browser',['app.js']),('qa',['test_backend.py'])]:
     if key in failed:
      if key=='browser' and ('Product polish requirements' in errors or 'missing static HTML IDs' in errors):files.extend(['index.html','app.js'])
      elif key=='browser' and 'Mobile horizontal overflow' in errors:files.append('styles.css')
      elif key=='catalog':
       files.extend(['db.py'] if 'Inventory grows on repeated initialization' in errors else ['catalog.py'])
      else:files.extend(names)
    if not files:files=['backend.py']
    for name in dict.fromkeys(files):
     title='Repair '+name
     task={'id':'repair-'+str(n)+'-'+name,'title':title,'actor':'daniel' if name.endswith('.py') else 'maya','model':LEAD if name.endswith('.py') else SPECIALIST,'owns':[name],'dependencies':[],'status':'pending'}
     self.tasks.append(task)
     relevant=[x for x in self.product['failures'] if name in repair_targets(x) or (name=='db.py' and x['id'] in ('catalog','auth')) or (name=='catalog.py' and x['id'] in ('catalog','admin')) or (name=='auth.py' and x['id']=='auth') or (name=='private.py' and x['id']=='private') or (name=='reservations.py' and x['id'] in ('reservation','admin')) or (name in ('app.js','index.html','styles.css') and x['id']=='browser') or (name=='test_backend.py' and x['id']=='qa')]
     errors=json.dumps([{**x,'error':str(x.get('error',''))[:2000]} for x in relevant])
     if any(x['id']=='reservation' and name in repair_targets(x) for x in relevant):errors+=' Public POST /quote must not require login. Trace dispatcher order: each module returns None for unrelated path/method BEFORE any auth guard. Preserve401 for private/reservation routes and403 for non-admin users. Do not change acceptance or authenticate its public quote call.'
     if any(x['id']=='routing' for x in relevant):errors+=' Fix the named module: identify owned method/path before auth.user. Return None for unrelated requests including GET /nonexistent and POST /listings. Keep correct generated QA expectations unchanged.'
     if name=='index.html':errors+=' Keep existing working IDs. Add an actual header Sign in button id=auth-nav data-view=auth class=nav-link, a separate span id=user-display for account identity, and keep Logout separate. Make request-key a hidden input for compatibility; never show technical IDs to users. The JavaScript task will bind these exact elements. Default auth-section hidden; anonymous startup reveals it.'
     if name=='app.js':errors+=' When a click produces no API call, trace event target/closest selection and branch reachability FIRST. A target selected only by [data-view] cannot match a favorite/detail/itinerary action. Select a union of all action attributes, then branch by the actual attribute. Convert dataset IDs to integers for API bodies. Bind forms before initial asynchronous session lookup; supply all required data-detail/data-favorite/data-edit-itinerary/data-delete-itinerary hooks on actual rendered buttons. Each navigation must load its backend data. Generate request keys automatically (never require a visitor to fill a technical key) and reset only after confirmed success. Coerce all dataset IDs to integer API fields. Every required flow must genuinely work, not just the first failing action.'
     if name=='test_backend.py':errors=qa_contract_diagnostics((self.candidate/name).read_text())+'\nLogout revocation: POST /logout with an already revoked bearer may return200 or401; prove revocation using GET /me and GET /favorites returning401. Do not require repeat logout401.\n'+errors
     if name=='test_backend.py':errors+=' Test only documented routes. Itinerary retrieval is GET /itineraries, returning the owned list; GET /itineraries/{id} is not in the contract. Test ownership with list membership and cross-user PUT/DELETE returning404, then verify the owner can still read/edit/delete the record. Do not repeatedly change expected status on an undocumented route. Reminder: administrator is seeded; LOGIN admin@example.test rather than registering it (which correctly returns409). Preserve legitimate tests; compact comments/whitespace to fit output.'
     await self.ticket(client,title,name,'Repair approach '+str(n+1)+': '+('inspect boundary validation and transaction behavior' if n%2==0 else 'simplify the failing handler and trace request/response state end to end')+'. Repair actual implementation against immutable acceptance. Observed failures: '+errors+'\nChange only '+name+'. Inspect its complete source. Preserve working behavior. Return complete file.',task)
