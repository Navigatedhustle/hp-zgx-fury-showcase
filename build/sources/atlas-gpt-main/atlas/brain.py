"""Local LLM delegation with bounded tool arguments and deterministic fallback."""
import os
import json
import time
from pathlib import Path
from atlas.config import ROOT
import httpx
from atlas.router import route
from atlas.analytics import TOOLS
from atlas.grounding import grounded_answer

class Brain:
    def __init__(self):
        self.base=os.getenv('ATLAS_LLM_BASE','http://127.0.0.1:8001/atlas');self.tokens=0;self.loaded=False;self.last_ms=None;self.name=os.getenv('ATLAS_MODEL','unsloth/Qwen3.6-27B-NVFP4');self.failures=0;self.narration_cache={};self.last_narration_ms=None
        self.cache_path=ROOT/'artifacts/narration-cache.json'
        try:self.narration_cache=json.loads(self.cache_path.read_text())
        except (OSError,ValueError):pass
    async def health(self):
        try:
            async with httpx.AsyncClient(timeout=.5,trust_env=False) as client:
                r=await client.get(self.base+'/health');self.loaded=r.status_code==200
        except httpx.HTTPError:self.loaded=False
        return self.loaded
    async def select(self,question,persona):
        fallback,args=route(question,persona)
        if fallback=='export_brief':return fallback,args,{'engine':'deterministic command','route_ms':0}
        if not self.loaded:return fallback,args,{'engine':'deterministic fallback','route_ms':0}
        names=['grant_forecast','sponsor_concentration','enrollment_forecast','score_sites'] if persona=='university' else ['forecast_quarter','what_if','deal_risk','region_vs_plan','pipeline_coverage','hiring_plan','score_sites','board_summary']
        start=time.perf_counter()
        try:
            payload={'messages':[{'role':'system','content':'Select the one local analytics tool that answers the question. Output JSON only: {"tool": "name"}. Tool names: '+', '.join(names)+'. If unrelated output {"tool":"unsupported"}. Do no math. No explanation.'},{'role':'user','content':question}], 'temperature':0,'max_tokens':32,'response_format':{'type':'json_object'},'chat_template_kwargs':{'enable_thinking':False}}
            async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
                response=await client.post(self.base+'/v1/chat/completions',json=payload,headers={'X-Fury-Role':'routing'});response.raise_for_status();data=response.json()
            self.tokens+=data.get('usage',{}).get('total_tokens',0)
            tool=json.loads(data['choices'][0]['message']['content']).get('tool')
            if tool not in names:tool=fallback
            # Explicit scoped scenario arguments always come from deterministic parsing.
            args=args if tool==fallback else ({'persona':persona} if tool=='score_sites' else {})
            ms=(time.perf_counter()-start)*1000;self.last_ms=ms
            return tool,args,{'engine':'local language model','route_ms':ms}
        except (httpx.HTTPError,KeyError,ValueError):
            self.failures+=1
            return fallback,args,{'engine':'deterministic fallback','route_ms':(time.perf_counter()-start)*1000}
    async def narrate(self,tool_output,use_llm=False):
        # Deterministic narration is the fast, always verified voice path.
        # Optional local LLM narration is checked before it can be displayed/spoken.
        candidate=tool_output['answer'];ms=0
        cache_key=candidate
        if use_llm and cache_key in self.narration_cache:
            answer,report=grounded_answer(self.narration_cache[cache_key],tool_output)
            return answer,{**report,'narrator':'local language model · cached' if not report['fallback'] and answer!=tool_output['answer'] else 'approved tool template · cached'},0
        if use_llm and self.loaded:
            start=time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
                    r=await client.post(self.base+'/v1/chat/completions',json={'messages':[{'role':'system','content':'You are an executive narrator. Restate the approved answer clearly in at most three sentences. Copy numerical facts exactly. Preserve deal names with their identifiers verbatim; identifiers are not counts. Do not calculate or introduce facts.'},{'role':'user','content':candidate}],'temperature':0,'max_tokens':110,'chat_template_kwargs':{'enable_thinking':False}},headers={'X-Fury-Role':'narration'})
                    r.raise_for_status();d=r.json();candidate=d['choices'][0]['message']['content'];self.tokens+=d.get('usage',{}).get('total_tokens',0)
            except (httpx.HTTPError,KeyError):pass
            ms=(time.perf_counter()-start)*1000
        answer,report=grounded_answer(candidate,tool_output)
        if use_llm and self.loaded and ms:self.narration_cache[cache_key]=answer;self.cache_path.write_text(json.dumps(self.narration_cache))
        self.last_narration_ms=ms
        return answer,{**report,'narrator':'local language model' if candidate!=tool_output['answer'] and not report['fallback'] else 'approved tool template'},ms
