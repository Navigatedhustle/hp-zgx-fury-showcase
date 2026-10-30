"""Typed judgments on supplied evidence; numerical analytics stay in Python."""
import json,time
import httpx
class Decisions:
 def __init__(self):self.loaded=False;self.last_ms=None;self.last_model_ms=None;self.tokens=0;self.inventory={};self.cache={}
 async def health(self):
  try:
   async with httpx.AsyncClient(timeout=.7,trust_env=False) as c:
    r=await c.get('http://127.0.0.1:8203/v1/models');r.raise_for_status();self.inventory=r.json()['models'][0];self.loaded=True
  except (httpx.HTTPError,ValueError,KeyError,IndexError):self.loaded=False
  return self.loaded
 async def judge(self,output):
  if output['tool'] not in ['deal_risk','score_sites']:return None
  if not self.loaded:return None
  if output['tool']=='deal_risk':
   deals=output['values']['deals'][:3]
   state={'policy':'Flag an executive recovery intervention if the buying champion is unconfirmed, inactivity exceeds 21 days, or any prior quarter slip is recorded. Use the supplied day counts. Do not calculate.','deals':[{'id':d['id'],'name':d['name'],'days_inactive':d['days_inactive'],'champion':d['champion'],'prior_quarter_slips':d['slipped_quarters'],'reasons':d['reasons']} for d in deals]}
   questions={d['id']:{'type':'noul','instructions':'Does deal '+d['id']+' meet the executive recovery policy?'} for d in deals}
  else:
   v=output['values'];state={'policy':'Choose the site the supplied evidence ranking favors. Scores are computed preferences, not probabilities of success. Do not recompute scores.','preferred_site':v['recommended'],'ranking':[{'city':r['city'],'weighted_score':r['score'],'annual_role_cost':r['rep_cost'],'attrition_assumption':r['attrition']} for r in v['ranking']],'assumptions':output['method']['assumptions']}
   questions={'site':{'type':'choice','instructions':'Which site is most supported by the stated evidence ranking?','criteria':{r['city']:'Candidate research center' if v['persona']=='university' else 'Candidate sales center' for r in v['ranking']}}}
  payload={'state':state,'questions':questions};key=json.dumps(payload,sort_keys=True)
  started=time.perf_counter()
  try:
   if key in self.cache:data=self.cache[key];hit=True
   else:
    async with httpx.AsyncClient(timeout=3.5,trust_env=False) as c:
     r=await c.post('http://127.0.0.1:8203/v1/systemone',json=payload);r.raise_for_status();data=r.json()
    self.cache[key]=data;self.tokens+=data.get('usage',{}).get('input_tokens',0)+data.get('usage',{}).get('output_tokens',0);hit=False
   self.last_ms=(time.perf_counter()-started)*1000
   self.last_model_ms=data['latency_ms']
   bars=[]
   for name,a in data['answers'].items():
    if 'probabilities' in a:bars.extend({'label':label,'probability':p} for label,p in a['probabilities'].items())
    else:bars.append({'label':name+' · recovery policy','probability':a['noul']})
   return {'kind':'typed judgment','engine':'System One decisions, on device.','bars':bars,'latency_ms':self.last_ms,'model_latency_ms':data['latency_ms'],'cached':hit,'temperature':self.inventory.get('temperature'),'calibration':'Checkpoint temperature calibration; business-domain calibration has not been evaluated.','meaning':'Confidence in the evidence-based judgment; not a probability of deal loss or site success.','raw_answers':data['answers']}
  except (httpx.HTTPError,ValueError,KeyError,TypeError):return None
