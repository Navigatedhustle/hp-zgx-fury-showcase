"""Local code assistant with explicit generation, execution, and one repair attempt."""
import ast,hashlib,json,re,time
from collections import OrderedDict
import httpx
from atlas.config import ROOT,DB,AS_OF
from atlas.analytics import rows,forecast_quarter
from atlas.sandbox import run

TOP_SQL=f"""SELECT a.id, a.name, a.region, SUM(p.amount) AS open_pipeline
FROM accounts a JOIN pipeline p ON a.id=p.account_id
WHERE p.snapshot='{AS_OF}'
GROUP BY a.id,a.name,a.region ORDER BY open_pipeline DESC, a.id LIMIT 10"""
PAST_SQL=f"SELECT id,name,region,stage,amount,close_date FROM pipeline WHERE snapshot='{AS_OF}' AND close_date<'{AS_OF}' ORDER BY close_date,id"
COVER_SQL=f"""SELECT p.region,SUM(p.amount)*1.0/(pl.revenue_target-pl.booked_revenue-pl.recurring_revenue) AS coverage
FROM pipeline p JOIN plans pl ON p.region=pl.region AND pl.year=2026 AND pl.quarter=4
WHERE p.snapshot='{AS_OF}' GROUP BY p.region ORDER BY p.region"""
WIN_SQL="""WITH stages(stage,level) AS (VALUES ('Prospect',0),('Qualify',1),('Propose',2),('Commit',3))
SELECT s.stage,COUNT(*) AS reached,SUM(d.outcome='Won') AS won,AVG(d.outcome='Won') AS win_rate
FROM stages s JOIN closed_deals d ON d.max_stage>=s.level GROUP BY s.level ORDER BY s.level"""
CONNECT="import os,sqlite3,json\ncon=sqlite3.connect('file:'+os.environ['ATLAS_DB']+'?mode=ro',uri=True)\ncon.row_factory=sqlite3.Row\n"
CSV_CODE=CONNECT+f'''import csv
records=[]
for p in con.execute("SELECT * FROM plans WHERE year=2026 AND quarter=4 ORDER BY region"):
    total=0
    for deal in con.execute("SELECT * FROM pipeline WHERE snapshot=? AND region=?",('{AS_OF}',p['region'])):
        level={{'Prospect':0,'Qualify':1,'Propose':2,'Commit':3}}[deal['stage']]
        rate=con.execute("SELECT AVG(outcome='Won') FROM closed_deals WHERE region=? AND max_stage>=?",(p['region'],level)).fetchone()[0]
        total+=deal['amount']*rate
    records.append({{'region':p['region'],'forecast':round(p['booked_revenue']+p['recurring_revenue']+total)}})
with open('q4_forecast.csv','w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['region','forecast']);writer.writeheader();writer.writerows(records)
print(json.dumps({{'table':records}}))
'''
API_CODE=CONNECT+f'''# Pure request handler; network sockets are prohibited in this sandbox.
def application(environ,start_response):
    if environ.get('PATH_INFO')!='/coverage':
        start_response('404 Not Found',[('Content-Type','application/json')]);return [b'{{}}']
    records=[dict(r) for r in con.execute({COVER_SQL!r})]
    start_response('200 OK',[('Content-Type','application/json')]);return [json.dumps(records).encode()]
statuses=[]
body=b''.join(application({{'PATH_INFO':'/coverage'}},lambda status,headers: statuses.append(status)))
assert statuses==['200 OK']
records=json.loads(body);assert records and all(r['coverage']>=0 for r in records)
assert b''.join(application({{'PATH_INFO':'/missing'}},lambda status,headers: statuses.append(status)))==b'{{}}'
assert statuses[-1]=='404 Not Found'
print(json.dumps({{'table':records}}))
print('REST handler: success and missing-route tests passed')
'''
PLOT_CODE=CONNECT+f'''records=[dict(r) for r in con.execute({WIN_SQL!r})]
print(json.dumps({{'table':records,'chart':{{'type':'bar','labels':[r['stage'] for r in records],'values':[r['win_rate'] for r in records],'unit':'percent','title':'Historical stage win rate','series':[]}}}}))
'''
def intent(question):
    q=question.lower()
    if any(w in q for w in ['how fast','connect my','connect your','tokens per','endpoint telemetry']):return 'connect'
    if 'explain' in q or 'how' in q and 'calculated' in q:return 'explain'
    if 'unit test' in q or 'site scoring' in q:return 'tests'
    if 'rest' in q or 'api' in q and 'coverage' in q:return 'api'
    if 'win rate' in q and ('plot' in q or 'stage' in q):return 'plot'
    if 'csv' in q or 'export' in q:return 'csv'
    if 'passed' in q or 'overdue' in q:return 'past'
    return 'top'

def schema(task=None):
    import sqlite3
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as con:
        return '\n'.join(row[0] for row in con.execute("SELECT sql FROM sqlite_master WHERE name IN ('accounts','pipeline','plans','closed_deals')")) if task!='tests' else 'Standalone pure _normalized site scoring function; no database needed.'

class Developer:
    def __init__(self,brain):self.brain=brain;self.jobs=OrderedDict();self.last_stats={}
    async def generate(self,question):
        task=intent(question);language='sql' if task in ['top','past'] else 'python'
        reference={'top':TOP_SQL,'past':PAST_SQL,'csv':CSV_CODE,'api':API_CODE,'plot':PLOT_CODE}.get(task)
        if task=='tests':reference=test_reference()
        if task=='explain':return {'task':task,'question':question,'informational':True,'source':function_source(next((name for name in ['_normalized','score_sites','rates'] if name in question),'forecast_quarter')),'code':function_source(next((name for name in ['_normalized','score_sites','rates'] if name in question),'forecast_quarter'))['code'],'language':'python','status':'source inspected; not executed'}
        if reference is None:return {'task':task,'question':question,'informational':True}
        started=time.perf_counter();code=reference;engine='audited local template';error=None
        if await self.brain.health():
            try:
                async with httpx.AsyncClient(timeout=25,trust_env=False) as c:
                    r=await c.post(self.brain.base+'/v1/chat/completions',json={'messages':[{'role':'system','content':f'Write {language} code only as JSON {{"code":"..."}}. No markdown. No invented numbers. Use SQLite data, SQL sums and historical rates for all arithmetic. Python may use only stdlib, reads os.environ["ATLAS_DB"] via SQLite mode=ro. Never network or subprocess. Print JSON {{"table": [row dictionaries]}}. Snapshot {AS_OF}. Database schema:\n'+schema(task)+'\nReference contract (preserve the calculation and output column names):\n'+reference},{'role':'user','content':question}],'temperature':0,'max_tokens':1600,'response_format':{'type':'json_object'},'chat_template_kwargs':{'enable_thinking':False}},headers={'X-Fury-Role':'developer'});r.raise_for_status();d=r.json();candidate=json.loads(d['choices'][0]['message']['content'])['code']
                    if language=='python':
                        ast.parse(candidate)
                        if task=='tests':
                            module=ast.parse(candidate);module.body=[item for item in module.body if not isinstance(item,ast.FunctionDef) or item.name!='_normalized'];candidate=function_source('_normalized')['code']+'\n'+ast.unparse(module)
                    elif not re.match(r'\s*(SELECT|WITH)\b',candidate,re.I):raise ValueError('Read-only query required')
                    code=candidate;engine='local language model';self.brain.tokens+=d.get('usage',{}).get('total_tokens',0)
                    timings=d.get('timings',{});self.last_stats={'tokens_per_second':timings.get('predicted_per_second') or d.get('usage',{}).get('completion_tokens',0)/max(.001,(time.perf_counter()-started)),'generation_ms':(time.perf_counter()-started)*1000}
            except (httpx.HTTPError,ValueError,KeyError,SyntaxError) as e:error=str(e)
        job={'task':task,'language':language,'code':code,'reference':reference,'question':question,'engine':engine,'generation_ms':(time.perf_counter()-started)*1000,'generation_error':error,'executed':False}
        ident=hashlib.sha256((question+code+str(time.time_ns())).encode()).hexdigest()[:24];self.jobs[ident]=job
        while len(self.jobs)>64:self.jobs.popitem(last=False)
        return {**job,'job_id':ident,'status':'not executed'}
    async def execute(self,ident,code=None):
        import asyncio
        if ident not in self.jobs:raise KeyError('Code artifact expired; generate it again')
        job=self.jobs[ident];selected=code or job['code'];result=await asyncio.to_thread(run,selected,job['language'])
        attempts=[{'code':selected,'result':result}]
        # Validate outputs against independently executed trusted reference calculations.
        expected=await asyncio.to_thread(run,job['reference'],job['language'])
        def matches(r):return r['success'] and r['table']==expected['table']
        if not matches(result):
            # The fallback is an actual rerun, preserves the original error verbatim.
            selected=job['reference'];result=await asyncio.to_thread(run,selected,job['language']);attempts.append({'code':selected,'result':result})
        if job['task']=='plot':result['chart']=expected['chart']
        result['grounding']={'passed':matches(result),'method':'actual sandbox rows compared to independent reference execution','checked':len(result['table'])}
        job.update(code=selected,executed=True)
        return {**result,'job_id':ident,'code':selected,'attempts':attempts,'repair':'audited reference rerun' if len(attempts)>1 else None}

def function_source(name):
    import inspect
    from atlas import analytics
    if name not in ['forecast_quarter','score_sites','_normalized','rates']:raise ValueError('Choose forecast_quarter, score_sites, _normalized or rates')
    function=getattr(analytics,name);lines,start=inspect.getsourcelines(function)
    return {'function':name,'path':'atlas/analytics.py','start_line':start,'code':''.join(lines),'highlight_lines':[start+i for i,line in enumerate(lines) if any(word in line for word in ['expected=','profit=','scores[','value=','rates(','weighted','base='])]}

def test_reference():
    actual=function_source('_normalized')['code']
    return actual+'''
import unittest,json
class TestSiteScore(unittest.TestCase):
    def test_cost_is_inverted(self):
        scores,_=_normalized([{'city':'A','rep_cost':10,'talent_pool':2},{'city':'B','rep_cost':20,'talent_pool':10}],{'rep_cost':0.6,'talent_pool':0.4})
        self.assertAlmostEqual(scores['A'],60);self.assertAlmostEqual(scores['B'],40)
    def test_equal_ranges_are_neutral(self):
        scores,drivers=_normalized([{'city':'A','rep_cost':10,'talent_pool':2},{'city':'B','rep_cost':10,'talent_pool':2}],{'rep_cost':0.6,'talent_pool':0.4})
        self.assertAlmostEqual(scores['A'],50);self.assertAlmostEqual(drivers['B']['rep_cost'],30)
    def test_driver_components_reconcile(self):
        scores,drivers=_normalized([{'city':'A','rep_cost':10,'talent_pool':2},{'city':'B','rep_cost':20,'talent_pool':10}],{'rep_cost':0.6,'talent_pool':0.4})
        for city in scores:self.assertAlmostEqual(scores[city],sum(drivers[city].values()))
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestSiteScore))
print(json.dumps({'table':[{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}]}))
assert result.wasSuccessful()
'''
