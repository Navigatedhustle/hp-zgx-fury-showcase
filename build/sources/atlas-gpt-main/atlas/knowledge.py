"""Live graph, canonical row IDs and exact deterministic-tool provenance."""
import hashlib,json,sqlite3,time
from collections import Counter
from datetime import datetime,timezone
from atlas.analytics import rows,source
from atlas.config import DB,ROOT,AS_OF

TABLES={'enterprise':['accounts','reps','pipeline','closed_deals','pnl','plans','sites','products','deal_products','knowledge_policies'],'university':['grant_history','grant_pipeline','enrollment','enrollment_current','university_budget','sites','principal_investigators','grant_investigators','programs','knowledge_policies']}
_cache={}
def record_id(table,row):
    if 'id' in row:key=row['id']
    elif table=='deal_products':key=row['deal_id']
    elif table=='grant_investigators':key=row['grant_id']
    elif table=='sites':key=row['persona']+':'+row['city']
    elif table in ['plans','pnl']:key=f"{row['year']}:{row['quarter']}:{row['region']}"
    elif table.startswith('enrollment'):key=f"{row['year']}:{row['college']}"
    elif table=='university_budget':key=str(row['fiscal_year'])
    else:key=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()[:16]
    return table+':'+str(key)

def graph(persona):
    persona='enterprise' if persona=='developer' else persona
    signature=(DB.stat().st_mtime_ns,persona)
    if signature in _cache:return _cache[signature]
    nodes={};edges=set();counts={};dates=[]
    def node(ident,kind,label,record,value=1,table=None):
        nodes.setdefault(ident,{'id':ident,'type':kind,'label':label,'record':record,'value':value,'table':table})
        return ident
    def entity(kind,label):return node(kind+':'+str(label),kind,str(label),{'name':label,'classification':'synthetic'})
    def link(a,b,kind):edges.add((a,b,kind))
    datasets={}
    for table in TABLES[persona]:
        data=rows('SELECT * FROM '+table+(' WHERE persona=?' if table=='sites' else ''),(persona,) if table=='sites' else ())
        datasets[table]=data;counts[table]=len(data)
        for r in data:
            for k,v in r.items():
                if k.endswith('date') or k in ['snapshot','deadline','last_activity']:dates.append(v)
            kind={'pipeline':'deal','closed_deals':'deal','accounts':'account','reps':'rep','sites':'sales center' if persona=='enterprise' else 'research center','plans':'quarter plan','pnl':'quarter actual','grant_pipeline':'grant','grant_history':'grant','principal_investigators':'PI','programs':'program','enrollment':'enrollment cohort','enrollment_current':'enrollment cohort','university_budget':'budget','products':'product'}.get(table,'relationship')
            ident=record_id(table,r);label=r.get('name',r.get('title',r.get('city',r.get('id',str(r.get('year',r.get('fiscal_year','Record')))))))
            amount=r.get('amount',r.get('annual_contract',r.get('annual_quota',r.get('revenue',r.get('revenue_target',r.get('admitted',r.get('nearby_pipeline',1)))))))
            node(ident,kind,label,r,amount,table)
            for key,kind in [('region','region'),('college','college'),('sponsor','sponsor'),('stage','stage')]:
                if key in r:link(ident,entity(kind,r[key]),'belongs to')
            if 'year' in r:link(ident,entity('quarter' if 'quarter' in r else 'year',str(r['year'])+(':Q'+str(r['quarter']) if 'quarter' in r else '')),'period')
            if 'fiscal_year' in r:link(ident,entity('year','FY'+str(r['fiscal_year'])),'period')
            for key,target in [('account_id','accounts'),('owner_id','reps'),('deal_id',None),('product_id','products'),('pi_id','principal_investigators'),('grant_id',None)]:
                if key in r:
                    if target:other=target+':'+r[key]
                    elif key=='deal_id':other=('closed_deals' if r[key].startswith('H') else 'pipeline')+':'+r[key]
                    else:other=('grant_pipeline' if r[key].startswith('GP') else 'grant_history')+':'+r[key]
                    link(ident,other,'references')
    if persona=='enterprise':
        for item in rows("SELECT dp.product_id,SUM(d.amount) AS value FROM deal_products dp JOIN (SELECT id,amount FROM pipeline UNION ALL SELECT id,amount FROM closed_deals) d ON d.id=dp.deal_id GROUP BY dp.product_id"):
            nodes['products:'+item['product_id']]['value']=item['value']
            nodes['products:'+item['product_id']]['value_unit']='USD linked deal volume'
    else:
        for pi in datasets['principal_investigators']:
            amount=rows("SELECT COALESCE(SUM(g.amount),0) AS value FROM grant_history g JOIN grant_investigators gi ON gi.grant_id=g.id WHERE gi.pi_id=? AND g.awarded=1",(pi['id'],))[0]['value']
            nodes['principal_investigators:'+pi['id']]['value']=amount
            nodes['principal_investigators:'+pi['id']]['value_unit']='USD awarded grant history'
    # Entity aggregate sizes are exact sums of adjacent actual row dollar/volume values.
    for ident,n in nodes.items():
        if n['table'] is None:n['value']=sum(nodes[a]['value'] for a,b,k in edges if b==ident and a in nodes)
    valid=[{'source':a,'target':b,'type':k} for a,b,k in sorted(edges) if a in nodes and b in nodes]
    output={'persona':persona,'nodes':list(nodes.values()),'edges':valid,'counts':{'nodes':len(nodes),'edges':len(valid),'node_types':dict(Counter(n['type'] for n in nodes.values())),'edge_types':dict(Counter(e['type'] for e in valid))},'data':{'tables':counts,'rows':sum(counts.values()),'date_range':[min(dates),max(dates)] if dates else [],'classification':'synthetic'},'refreshed_at':datetime.now(timezone.utc).isoformat()}
    path=ROOT/'data'/f'graph-{persona}.json';path.write_text(json.dumps(output));_cache.clear() if len(_cache)>4 else None;_cache[signature]=output;return output

def provenance(output,persona,kwargs):
    tool=output['tool'];queries={};region=kwargs.get('region')
    if tool in ['forecast_quarter','what_if','region_vs_plan','board_summary','deal_risk']:
        queries['pipeline']=("SELECT * FROM pipeline WHERE snapshot=? AND (? IS NULL OR region=?)",(AS_OF,region,region))
        queries['closed_deals']=("SELECT * FROM closed_deals WHERE (? IS NULL OR region=?)",(region,region))
        if tool!='deal_risk':queries['plans']=("SELECT * FROM plans WHERE year=2026 AND quarter=4 AND (? IS NULL OR region=?)",(region,region))
    elif tool=='pipeline_coverage':
        queries={'pipeline':('SELECT * FROM pipeline',()),'plans':('SELECT * FROM plans WHERE year IN (2025,2026) AND quarter=4',()),'closed_deals':('SELECT * FROM closed_deals',())}
    elif tool=='hiring_plan':queries={'reps':('SELECT * FROM reps',()),'plans':('SELECT * FROM plans WHERE year IN (2026,2027)',())}
    elif tool=='score_sites':
        data=rows('SELECT * FROM sites WHERE persona=?',(persona,));data=[r for r in data if not kwargs.get('cities') or r['city'] in kwargs['cities']]
        queries={'sites':data}
    elif tool=='grant_forecast':queries={'grant_pipeline':('SELECT * FROM grant_pipeline WHERE fiscal_year=2027',()),'grant_history':('SELECT * FROM grant_history',()),'university_budget':('SELECT * FROM university_budget WHERE fiscal_year=2027',())}
    elif tool=='sponsor_concentration':queries={'grant_history':('SELECT * FROM grant_history WHERE year=2026 AND awarded=1',())}
    elif tool=='enrollment_forecast':queries={'enrollment':('SELECT * FROM enrollment',()),'enrollment_current':('SELECT * FROM enrollment_current',())}
    sources=[];selected=[]
    g=graph(persona);nodes={n['id']:n for n in g['nodes']}
    for table,query in queries.items():
        records=query if isinstance(query,list) else rows(*query);ids=[record_id(table,r) for r in records];selected.extend(ids)
        original=next((s for s in output['sources'] if s['table']==table),source(table,len(records),'exact tool inputs','row'))
        sources.append({**original,'rows':len(records),'row_ids':ids})
    active=set(selected)
    active.update(e['target'] for e in g['edges'] if e['source'] in active)
    output['sources']=sources;output['provenance']={'node_ids':sorted(active),'row_ids':selected,'passage_ids':[],'rows':len(selected),'method':'Exact rows read by deterministic tool; canonical SQLite primary keys'}
    return output
