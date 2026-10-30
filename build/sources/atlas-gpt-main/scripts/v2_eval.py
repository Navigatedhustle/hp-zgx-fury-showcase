"""Measure every golden route, numerical/citation check and real Developer execution."""
import asyncio,json,time
from pathlib import Path
import httpx
from atlas.config import ROOT,GOLDEN,UPGRADE_GOLDEN
from atlas.documents import citation_check
async def main():
    results=[]
    async with httpx.AsyncClient(timeout=90,trust_env=False) as c:
        for persona,expected,question in GOLDEN+UPGRADE_GOLDEN:
            start=time.perf_counter();r=await c.post('http://127.0.0.1:8200/api/query',json={'question':question,'persona':persona});d=r.json();entry={'persona':persona,'question':question,'expected':expected,'http_status':r.status_code,'wall_ms':(time.perf_counter()-start)*1000,'response':d}
            if r.status_code==200:
                actual='developer_'+d['developer']['task'] if 'developer' in d else d.get('tool');entry['routing_passed']=actual==expected;entry['grounding_passed']=d.get('grounding',{}).get('passed',False)
                if d.get('citations'):entry['citations']=citation_check(d['answer'],d['citations'])
                if d.get('developer',{}).get('job_id'):
                    execution=(await c.post('http://127.0.0.1:8200/api/developer/run',json={'job_id':d['developer']['job_id']})).json();entry['execution']=execution;entry['execution_passed']=execution['success'] and execution['grounding']['passed']
            results.append(entry);print(persona,expected,entry.get('routing_passed'),entry.get('grounding_passed'),entry.get('execution_passed','info'),flush=True)
    report={'measured_at':time.time(),'questions':results,'routing':sum(e.get('routing_passed',False) for e in results),'grounding':sum(e.get('grounding_passed',False) for e in results),'numeric_claims_checked':sum(e['response'].get('grounding',{}).get('checked',0) for e in results),'citation_questions':sum('citations' in e for e in results),'citation_passed':sum(e.get('citations',{}).get('passed',False) for e in results),'developer_executed':sum(e.get('execution_passed',False) for e in results),'developer_informational':sum(e['persona']=='developer' and 'execution' not in e for e in results),'repairs':sum(bool(e.get('execution',{}).get('repair')) for e in results)}
    (ROOT/'eval/v2/golden-results.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='questions'}));assert report['routing']==len(results)==26 and report['grounding']==26 and report['citation_passed']==6 and report['developer_executed']==6
asyncio.run(main())
