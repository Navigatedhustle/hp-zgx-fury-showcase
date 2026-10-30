import asyncio,json,httpx
from pathlib import Path
from atlas.config import UPGRADE_GOLDEN
ROOT=Path(__file__).resolve().parents[1]
async def main():
    results=[]
    async with httpx.AsyncClient(timeout=90) as c:
        for persona,tool,question in UPGRADE_GOLDEN:
            if tool!='search_knowledge':continue
            r=await c.post('http://127.0.0.1:8200/api/query',json={'question':question,'persona':persona});d=r.json();print(persona,question,r.status_code,d.get('grounding'),flush=True);results.append(d);assert r.status_code==200 and d['grounding']['passed'] and d['grounding']['citations_passed']
        for persona in ['enterprise','university']:
            r=await c.post('http://127.0.0.1:8200/api/knowledge/feed',json={'persona':persona});d=r.json();print('Feed',persona,r.status_code,d.get('proof'),d.get('detail'),flush=True);assert r.status_code==200 and d['proof']['after_contains_new_phrase'] and not d['proof']['before_contains_new_phrase'] and d['proof']['before_matches']==0;results.append({'feed':d})
    (ROOT/'eval/v2/knowledge-results.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
