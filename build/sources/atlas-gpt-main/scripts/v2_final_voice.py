import asyncio,json
from scripts.v2_voice import sample
from playwright.async_api import async_playwright
from atlas.config import ROOT
async def main():
    results=[]
    async with async_playwright() as p:
        for persona,q in [('enterprise',"What's our projected Q4 revenue and profit?"),('university',"Based on our grant pipeline, what's projected research funding for FY27?"),('developer','Write a SQL query for the top ten accounts by open pipeline, and run it.')]:
            d=await sample(p,persona,q,True);results.append(d);print(persona,d['metrics'][0]['ttfa_ms'],d['result']['grounding']['passed'],d.get('executed_status'),flush=True)
    (ROOT/'eval/v2/final-voice.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
