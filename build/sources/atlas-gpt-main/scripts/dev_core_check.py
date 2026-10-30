import asyncio,json,httpx
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
async def main():
    results=[]
    async with httpx.AsyncClient(timeout=60) as c:
        for question in ['Write a SQL query for the top ten accounts by open pipeline, and run it.','Write a Python script that exports the Q4 forecast by region to CSV, then run it.']:
            d=(await c.post('http://127.0.0.1:8200/api/query',json={'persona':'developer','question':question})).json()
            job=d['developer'];r=(await c.post('http://127.0.0.1:8200/api/developer/run',json={'job_id':job['job_id']})).json();results.append({'question':question,'generated':d,'execution':r});print(question,job['engine'],r['success'],r['grounding'],flush=True)
            assert r['success'] and r['grounding']['passed']
    (ROOT/'eval/v2/developer-core.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
