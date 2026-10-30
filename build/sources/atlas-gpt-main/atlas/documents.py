"""Seeded synthetic corpus, real local vectors and passage-grounded retrieval."""
import asyncio,hashlib,json,re,time,uuid
from datetime import datetime,timezone
from pathlib import Path
import httpx,numpy as np
from atlas.config import ROOT,AS_OF
from atlas.analytics import rows,forecast_quarter,region_vs_plan,hiring_plan,enrollment_forecast,grant_forecast,source,result,bar
from atlas.knowledge import record_id,provenance
from atlas.grounding import check

STORE=ROOT/'data/knowledge';STORE.mkdir(exist_ok=True);INDEX=STORE/'index.json';VECTORS=STORE/'vectors.npy'
_lock=asyncio.Lock()

def passage_ids(table,records):return [record_id(table,r) for r in records]
def corpus():
    docs=[]
    def add(persona,kind,title,passages,ids):
        ident=hashlib.sha256((persona+title).encode()).hexdigest()[:16]
        docs.append({'id':ident,'persona':persona,'kind':kind,'title':title,'classification':'synthetic','created_at':AS_OF,'passages':[{'id':ident+':'+str(i),'text':text,'row_ids':ids} for i,text in enumerate(passages)]})
    f=forecast_quarter();worst=region_vs_plan()['values']['furthest_behind'];h=hiring_plan()['values']
    fids=provenance(f.copy(),'enterprise',{})['provenance']['row_ids']
    add('enterprise','board memo','Q4 board memo: margin concerns',[f"Synthetic board memo. Projected Q4 revenue is ${f['values']['revenue']:,}; operating profit is ${f['values']['profit']:,}. Contribution margin assumption is {f['values']['contribution_margin']*100:g}%. Fixed operating expense is ${f['values']['opex']:,}.","Board concern: discount pressure and late-stage concessions may reduce margin. Finance should review exceptions and protect renewal economics. These are synthetic management concerns, not measured causal effects."],fids)
    for region in ['West','Central','East','International']:
        rf=forecast_quarter(region);v=rf['values'];ids=provenance(rf.copy(),'enterprise',{'region':region})['provenance']['row_ids']
        add('enterprise','QBR notes',region+' QBR: regional risk',[f"Synthetic QBR. {region} projected Q4 revenue is ${v['revenue']:,}; projected operating profit is ${v['profit']:,}. The approved range is ${v['range']['p10']:,} to ${v['range']['p90']:,}.",f"The QBR flags late-stage deal slippage, inactive buying teams and unconfirmed champions. {worst['region']} is the weakest region against plan with a ${worst['shortfall']:,} shortfall. Prioritize sponsor confirmation and a dated recovery plan."],ids)
    accounts=rows("SELECT a.*,SUM(p.amount) AS open_pipeline FROM accounts a JOIN pipeline p ON a.id=p.account_id WHERE p.snapshot=? GROUP BY a.id ORDER BY open_pipeline DESC,a.id LIMIT 10",(AS_OF,))
    for a in accounts[:5]:
        ds=rows('SELECT * FROM pipeline WHERE snapshot=? AND account_id=?',(AS_OF,a['id']))
        add('enterprise','account plan',a['name']+' account plan',[f"Synthetic account plan. {a['name']} ({a['id']}) is in {a['region']}. Its annual contract is ${a['annual_contract']:,}; open pipeline on {AS_OF} is ${a['open_pipeline']:,}.","Confirm the buying sponsor, protect renewal scope and resolve margin exceptions before commercial approval."],[record_id('accounts',a)]+passage_ids('pipeline',ds))
    threshold=rows("SELECT value FROM knowledge_policies WHERE id='discount_approval'")[0]['value']
    add('enterprise','pricing policy','Pricing policy: discount approval',[f"Synthetic pricing policy. Finance approval is required when an account's total open quoted pipeline exceeds ${threshold:,}. This seeded policy is a scenario assumption, not an actual business policy.","Flagged accounts from the largest exposures: "+'; '.join(f"{a['name']} ({a['id']}): ${a['open_pipeline']:,}" for a in accounts if a['open_pipeline']>threshold)+'.'],[record_id('accounts',a) for a in accounts]+['knowledge_policies:discount_approval'])
    add('enterprise','hiring plan','Sales capacity and hiring plan',[f"Synthetic hiring plan. Plan {h['hires']} hires: {h['growth_hires']} growth and {h['replacement_hires']} attrition replacement. Current reps: {h['current_reps']}. Annual revenue target: ${h['annual_target']:,}.","Recruit early enough for onboarding. The plan relies on the disclosed ramp, quota productivity and attrition assumptions."],provenance(hiring_plan(),'enterprise',{})['provenance']['row_ids'])
    gf=grant_forecast()['values'];ef=enrollment_forecast()['values']
    add('university','board memo','Research board funding memo',[f"Synthetic memo. FY27 projected research funding is ${gf['funding']:,}, including ${gf['awarded_funding']:,} awarded. Expected pipeline awards are ${gf['weighted_pipeline']:,}.","Research leaders should diversify sponsor dependencies and protect bridge capacity."],provenance(grant_forecast(),'university',{})['provenance']['row_ids'])
    add('university','sponsor guidelines','Sponsor guidance: cost sharing',["Synthetic sponsor guidance. Cost sharing is not mandatory unless the solicitation explicitly requires it. The seeded default required share is 0%. Document any exception and obtain research finance approval.","Sponsor guidance does not guarantee an award. Check eligibility, allowable costs and institutional commitments before submission."],['knowledge_policies:cost_share'])
    add('university','enrollment strategy','Enrollment strategy: yield risks',[f"Synthetic enrollment strategy. Projected entrants: {ef['enrolled']:,}; admitted students: {ef['admitted']:,}; deposits: {ef['deposited']:,}. Projected yield is {ef['yield']*100:.1f}%.","Risks: historical deposit retention may not persist, aid timing can delay decisions, and housing capacity can constrain yield. Prioritize outreach in colleges with the lowest projected yield."],provenance(enrollment_forecast(),'university',{})['provenance']['row_ids'])
    pirows=rows("SELECT pi.id,pi.name,pi.college,COUNT(*) AS applications,SUM(g.awarded) AS awards,SUM(CASE WHEN g.awarded THEN g.amount ELSE 0 END) AS awarded_amount FROM principal_investigators pi JOIN grant_investigators gi ON gi.pi_id=pi.id JOIN grant_history g ON g.id=gi.grant_id WHERE g.sponsor='NIH' GROUP BY pi.id ORDER BY awarded_amount DESC,pi.id")
    for p in pirows:
        actual=rows("SELECT g.* FROM grant_history g JOIN grant_investigators gi ON g.id=gi.grant_id WHERE gi.pi_id=? AND g.sponsor='NIH'",(p['id'],))
        add('university','grant abstract',p['name']+' NIH track record',[f"Synthetic grant history and abstract. {p['name']} ({p['id']}), {p['college']}: {p['applications']} NIH applications, {p['awards']} awards, ${p['awarded_amount']:,} awarded. Ranking is based on awarded value, not predicted scientific quality.","The synthetic research program addresses resilient infrastructure, precision health, clean energy and learning futures. Prior performance does not ensure future awards."],[record_id('principal_investigators',p)]+passage_ids('grant_history',actual))
    for p in rows('SELECT * FROM programs'):
        add('university','program strategy',p['name']+' strategy',[f"Synthetic program strategy for {p['name']}. The program is connected to {p['college']} enrollment cohorts.","Monitor aid turnaround, deposit retention and teaching capacity. Escalate resource bottlenecks to college leadership."],[record_id('programs',p)])
    return docs

async def embed(texts,query=False):
    async with httpx.AsyncClient(timeout=90,trust_env=False) as c:
        r=await c.post('http://127.0.0.1:8206/embed',json={'texts':texts,'query':query});r.raise_for_status();return np.array(r.json()['vectors'],dtype=np.float32)

def load():
    if not INDEX.exists():return {'documents':[],'model':None,'refreshed_at':None}
    return json.loads(INDEX.read_text())
def chunks(index):return [{**p,'document_id':d['id'],'document':d['title'],'persona':d['persona'],'kind':d['kind']} for d in index['documents'] for p in d['passages']]
def stats(persona):
    index=load();docs=[d for d in index['documents'] if d['persona']==('enterprise' if persona=='developer' else persona)];passages=[p for d in docs for p in d['passages']]
    total=len(chunks(index));vectors=np.load(VECTORS,mmap_mode='r') if VECTORS.exists() else np.empty((0,0))
    assert len(vectors)==total,'Index/vector count mismatch'
    return {'documents':len(docs),'passages':len(passages),'vectors':sum(1 for p in chunks(index) if p['persona']==('enterprise' if persona=='developer' else persona)),'model':index['model'],'dimension':vectors.shape[1] if len(vectors) else 0,'refreshed_at':index['refreshed_at']}

async def initialize():
    async with _lock:
        if INDEX.exists():return stats('enterprise')
        documents=corpus();allpass=[p['text'] for d in documents for p in d['passages']];vectors=[]
        for i in range(0,len(allpass),32):vectors.extend(await embed(allpass[i:i+32]))
        np.save(VECTORS,np.array(vectors,dtype=np.float32));descriptor=json.loads((ROOT/'models/embed.json').read_text());index={'documents':documents,'model':descriptor['id'],'revision':descriptor['revision'],'refreshed_at':datetime.now(timezone.utc).isoformat()};INDEX.write_text(json.dumps(index));return stats('enterprise')

def knowledge_intent(question):return bool(re.search(r'\b(qbr|board.{0,20}concerns|margin.{0,20}(concerns|memo)|pricing policy|discount approval|nih track record|sponsor (guidance|guidelines)|cost sharing|enrollment strategy|action phrase|newest.{0,20}memo)\b',question,re.I))

async def search(question,persona):
    index=load();passages=chunks(index)
    if not passages:raise ValueError('Document index is not ready')
    pool=[(i,p) for i,p in enumerate(passages) if p['persona']==persona]
    q=question.lower();kind=None
    if 'qbr' in q:kind='QBR notes';region=region_vs_plan()['values']['furthest_behind']['region'];pool=[(i,p) for i,p in pool if p['kind']==kind and p['document'].startswith(region)]
    elif 'pricing' in q or 'discount' in q:kind='pricing policy'
    elif 'nih' in q:kind='grant abstract'
    elif 'cost shar' in q or 'guidance' in q:kind='sponsor guidelines'
    elif 'enrollment strategy' in q:kind='enrollment strategy'
    elif 'action phrase' in q or 'newest' in q:kind='live memo'
    elif 'board' in q or 'margin' in q:kind='board memo'
    if kind and kind!='QBR notes':pool=[(i,p) for i,p in pool if p['kind']==kind]
    target_memo=re.search(r'\bmemo ([0-9a-f]{16})\b',q)
    if kind=='live memo' and target_memo:pool=[(i,p) for i,p in pool if p['document_id']==target_memo.group(1)]
    if kind=='live memo' and pool and not target_memo:
        newest=max((d for d in index['documents'] if d['persona']==persona and d['kind']=='live memo'),key=lambda d:d['created_at'])
        pool=[(i,p) for i,p in pool if p['document_id']==newest['id']]
    if not pool:
        output=result('search_knowledge',{'matches':0},'No cited passage contains the requested fact.',{'query':question},[],bar([],[],unit='count',title='No matching passage'),'Knowledge search','—','NO CITED EVIDENCE','No indexed passage contains that fact yet. Feed the brain to connect a new synthetic memo.')
        output['citations']=[];output['grounding']=check(output['answer'],output);output['provenance']={'node_ids':[],'row_ids':[],'passage_ids':[],'rows':0};return output
    vector=(await embed([question],True))[0];matrix=np.load(VECTORS);ranked=sorted([(float(matrix[i]@vector),p) for i,p in pool],key=lambda pair:pair[0],reverse=True)
    if kind=='grant abstract':
        # Exact award-value rank is tool arithmetic; semantic search finds relevant passages.
        allowed={p['document_id'] for score,p in ranked};documents=[d for d in index['documents'] if d['id'] in allowed];documents.sort(key=lambda d:int(re.search(r'\$([\d,]+)',d['passages'][0]['text']).group(1).replace(',','')),reverse=True);wanted={d['passages'][0]['id'] for d in documents[:3]};selected=[next(p for score,p in ranked if p['id']==d['passages'][0]['id']) for d in documents[:3]]
    else:selected=[p for score,p in ranked[:2]]
    citations=[{'document_id':p['document_id'],'document':p['document'],'passage_id':p['id'],'passage':p['text']} for p in selected]
    answer=' '.join(p['text'] for p in selected);ids=sorted({r for p in selected for r in p['row_ids']});node_ids=ids+['document:'+p['document_id'] for p in selected]+['passage:'+p['id'] for p in selected]
    output=result('search_knowledge',{'matches':len(selected),'passages':[p['text'] for p in selected],'quarter':forecast_quarter()['values']['quarter'],'fiscal_year':grant_forecast()['values']['fiscal_year'],'short_year':grant_forecast()['values']['short_year']},'Local vector similarity ranks passages within persona and document type. Answer quotes retrieved evidence; all numbers must appear in cited passages.',{'query':question,'embedding_model':index['model'],'scope':persona},[{'table':'documents','rows':len(selected),'filters':question,'grain':'passage','row_ids':[p['id'] for p in selected]}],bar([p['document'] for p in selected],[len(p['row_ids']) for p in selected],unit='count',title='Rows connected to cited passages'),'Grounded in the Second Brain',str(len(selected)),'CITED PASSAGES',answer,['All documents and policy assumptions are synthetic. Retrieval is indexing, not domain model training.'])
    output['citations']=citations;output['provenance']={'node_ids':node_ids,'row_ids':ids,'passage_ids':[p['id'] for p in selected],'rows':len(ids)}
    report=check(answer,output);citations_report=citation_check(answer,citations,index);report.update(citations_passed=citations_report['passed'],narrator='verbatim indexed passages');report['passed']=report['passed'] and citations_report['passed'];output['grounding']=report;return output

def citation_check(answer,citations,index=None):
    index=index or load();lookup={p['id']:(d,p) for d in index['documents'] for p in d['passages']}
    errors=[]
    for c in citations:
        actual=lookup.get(c['passage_id'])
        if not actual or actual[0]['id']!=c['document_id'] or actual[0]['title']!=c['document'] or actual[1]['text']!=c['passage']:errors.append(c['passage_id'])
    numerical=check(answer,{'values':{'passages':[c['passage'] for c in citations]}})
    # Quarter/fiscal identifiers must also occur literally in a cited passage.
    literal_periods=all(any(n in c['passage'] for c in citations) for n in re.findall(r'\b(?:Q|FY)\d+\b',answer))
    unsupported=[n for n in numerical['unsupported'] if not re.fullmatch(r'(?:Q|FY)\d+',n)]
    return {'passed':not errors and not unsupported and literal_periods,'invalid_passages':errors,'unsupported':unsupported,'checked':numerical['checked']}

async def feed(persona,brain):
    if not await brain.health():raise ValueError('Local language model is unavailable; no document generated')
    started=time.perf_counter();ident=uuid.uuid4().hex[:16];phrase='margin-'+''.join(chr(97+int(c,16)) for c in uuid.uuid4().hex[:8]) if persona=='enterprise' else 'science-'+''.join(chr(97+int(c,16)) for c in uuid.uuid4().hex[:8]);question='What is the action phrase in the new '+('margin' if persona=='enterprise' else 'research')+' memo '+ident+'?'
    before=await search(question,persona);fact_document=corpus()[0] if persona=='enterprise' else next(d for d in corpus() if d['persona']=='university' and d['kind']=='board memo');facts=fact_document['passages'][0]['text'];fact_rows=fact_document['passages'][0]['row_ids']
    async with httpx.AsyncClient(timeout=25,trust_env=False) as c:
        r=await c.post(brain.base+'/v1/chat/completions',json={'messages':[{'role':'system','content':'Write a short synthetic board memo with no numerical claims, dates or quantities. Return JSON {"memo":"..."}. Qualitative prose only; the application will append database facts. Include this exact line: Action phrase: '+phrase+'. Explain margin review or research sponsor diversification. Do not include digits or number words.'},{'role':'user','content':'Generate the new synthetic memo.'}],'temperature':0,'max_tokens':300,'response_format':{'type':'json_object'},'chat_template_kwargs':{'enable_thinking':False}});r.raise_for_status();d=r.json();text=json.loads(d['choices'][0]['message']['content'])['memo']+'\nVerified synthetic database facts: '+facts;brain.tokens+=d.get('usage',{}).get('total_tokens',0)
    # The action phrase's identifier digits are metadata, not numerical claims.
    evidence={'values':{'facts':facts,'phrase':phrase,'quarter':forecast_quarter()['values']['quarter'],'fiscal_year':grant_forecast()['values']['fiscal_year'],'short_year':grant_forecast()['values']['short_year']}};report=check(text,evidence)
    if not report['passed'] or phrase not in text:raise ValueError('Generated memo failed grounding; nothing ingested')
    doc={'id':ident,'persona':persona,'kind':'live memo','title':'Synthetic live '+('margin' if persona=='enterprise' else 'research')+' memo '+ident,'created_at':datetime.now(timezone.utc).isoformat(),'classification':'synthetic','generator':'local language model prose + deterministic database fact appendix','passages':[{'id':ident+':0','text':text,'row_ids':fact_rows} ]}
    vectors=await embed([text])
    async with _lock:
        index=load();matrix=np.load(VECTORS);index['documents'].append(doc);index['refreshed_at']=datetime.now(timezone.utc).isoformat();np.save(VECTORS,np.concatenate([matrix,vectors]));INDEX.write_text(json.dumps(index))
    after=await search(question,persona);proof={'before_matches':before['values']['matches'],'before_contains_new_phrase':phrase in before['answer'],'after_contains_new_phrase':phrase in after['answer'],'citation_passed':after['grounding']['passed']}
    return {'document':doc,'ingest_ms':(time.perf_counter()-started)*1000,'question':question,'phrase':phrase,'proof':proof,'answer':after,'grounding':report,'stats':stats(persona)}
