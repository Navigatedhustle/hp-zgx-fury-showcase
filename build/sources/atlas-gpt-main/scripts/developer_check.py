import asyncio,json,httpx
from pathlib import Path
from atlas.config import UPGRADE_GOLDEN
ROOT=Path(__file__).resolve().parents[1]
async def main():
    results=[]
    async with httpx.AsyncClient(timeout=90) as c:
        for persona,tool,question in UPGRADE_GOLDEN:
            if persona!='developer':continue
            r=await c.post('http://127.0.0.1:8200/api/query',json={'persona':persona,'question':question});d=r.json();assert r.status_code==200,d
            job=d['developer'];entry={'question':question,'generated':d};print(job['task'],job.get('engine'),job.get('generation_error'),flush=True)
            if job.get('job_id'):
                e=(await c.post('http://127.0.0.1:8200/api/developer/run',json={'job_id':job['job_id']})).json();entry['execution']=e;print(' executed',e['success'],e['grounding'],'repair',e['repair'],flush=True);assert e['success'] and e['grounding']['passed']
            else:assert job.get('source') or job.get('connection')
            results.append(entry)
    (ROOT/'eval/v2/developer-results.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
