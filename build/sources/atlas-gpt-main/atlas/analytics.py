"""All executive arithmetic lives here. Pure Python, reproducible and auditable."""
import math
import random
import sqlite3
from datetime import date
from functools import lru_cache
from atlas.config import DB, AS_OF, SEED
from atlas.data.generate import REGIONS, STAGES, COLLEGES

def money(n):
    sign='−' if n<0 else ''
    n=abs(n)
    return f'{sign}${n/1e9:,.2f}B' if n>=1e9 else f'{sign}${n/1e6:,.1f}M' if n>=1e6 else f'{sign}${n:,.0f}'
def percent(n):return f'{n*100:.1f}%'
def rows(sql, params=()):
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute(sql,params)]
def source(table, count, filters, grain):
    return {'table':table,'rows':count,'filters':filters,'grain':grain,'path':f'data/csv/{table}.csv','classification':'synthetic','as_of':AS_OF}
def result(tool,values,formula,inputs,sources,chart,title,headline,label,answer,assumptions=None):
    return {'tool':tool,'values':values,'method':{'formula':formula,'inputs':inputs,'assumptions':assumptions or [],'seed':SEED,'as_of':AS_OF},'sources':sources,'chart':chart,'title':title,'headline':headline,'headline_label':label,'answer':answer,'classification':'synthetic','estimate':True}
def bar(labels,values,unit='currency',title='',series=None):
    return {'type':'bar','labels':labels,'values':values,'unit':unit,'title':title,'series':series or [],'zero_baseline':True}

@lru_cache(maxsize=8)
def _history():return rows('SELECT * FROM closed_deals')
@lru_cache(maxsize=8)
def rates(region=None):
    h=[d for d in _history() if not region or d['region']==region]
    result={}
    for i,stage in enumerate(STAGES):
        cohort=[d for d in h if d['max_stage']>=i]
        won=sum(d['outcome']=='Won' for d in cohort)
        result[stage]={'won':won,'reached':len(cohort),'rate':won/len(cohort)}
    return result
def _pipeline(snapshot=AS_OF,region=None):
    return rows('SELECT * FROM pipeline WHERE snapshot=? AND (? IS NULL OR region=?) ORDER BY id',(snapshot,region,region))
def _plans(year=2026,region=None):return rows('SELECT * FROM plans WHERE year=? AND quarter=4 AND (? IS NULL OR region=?)',(year,region,region))
def _weighted(region=None,drop=0):
    pipe=_pipeline(region=region); plans=_plans(region=region)
    pairs=[]
    for d in pipe:
        p=rates(d['region'])[d['stage']]['rate']
        if d['stage']=='Commit':p=max(0,min(1,p-drop))
        pairs.append((d,p))
    base=sum(p['booked_revenue']+p['recurring_revenue'] for p in plans)
    return pipe,plans,pairs,base
def _quantile(sorted_values,p):
    index=(len(sorted_values)-1)*p;lo=math.floor(index);hi=math.ceil(index)
    return round(sorted_values[lo]+(sorted_values[hi]-sorted_values[lo])*(index-lo))

@lru_cache(maxsize=24)
def forecast_quarter(region=None,commit_drop=0.0):
    pipe,plans,pairs,base=_weighted(region,commit_drop)
    expected=round(base+sum(d['amount']*p for d,p in pairs))
    opex=sum(p['remaining_opex'] for p in plans);margin=plans[0]['variable_margin']
    profit=round(expected*margin-opex)
    rng=random.Random(SEED)
    sims=sorted(base+sum(d['amount'] for d,p in pairs if rng.random()<p) for _ in range(2000))
    interval={f'p{int(p*100)}':_quantile(sims,p) for p in [.1,.5,.9]}
    variance=sorted([{'id':d['id'],'name':d['name'],'amount':d['amount'],'probability':p,'variance':round(d['amount']**2*p*(1-p)),'region':d['region']} for d,p in pairs],key=lambda d:d['variance'],reverse=True)[:5]
    region_values=[]
    for r in REGIONS:
        if region and r!=region:continue
        sub=[p for p in plans if p['region']==r]
        region_values.append({'region':r,'revenue':round(sum(p['booked_revenue']+p['recurring_revenue'] for p in sub)+sum(d['amount']*p for d,p in pairs if d['region']==r)),'plan':sum(p['revenue_target'] for p in sub)})
    values={'revenue':expected,'profit':profit,'operating_margin':profit/expected,'base_revenue':base,'weighted_pipeline':expected-base,'opex':opex,'contribution_margin':margin,'range':interval,'profit_range':{k:round(v*margin-opex) for k,v in interval.items()},'top_variance_deals':variance,'regions':region_values,'stage_rates':{r:rates(r) for r in REGIONS},'open_deals':len(pipe),'quarter':4,'year':2026,'simulations':2000,'percentiles':[10,50,90]}
    return result('forecast_quarter',values,'Revenue = booked + recurring + Σ(open amount × historical stage win rate); profit = revenue × contribution margin − fixed operating expense.',{'booked_and_recurring':base,'open_pipeline':sum(d['amount'] for d in pipe),'fixed_opex':opex,'contribution_margin':margin,'commit_drop':commit_drop,'simulation_count':2000},[source('pipeline',len(pipe),f'snapshot={AS_OF}; Q4 close dates; region={region or "all"}','deal'),source('closed_deals',len(_history()),'2023–2025; stage reached cohorts','closed deal'),source('plans',len(plans),'2026 Q4','region-quarter')],bar([r['region'] for r in region_values],[r['revenue'] for r in region_values],title='Forecast and plan by region',series=[{'name':'Plan','values':[r['plan'] for r in region_values]}]),'Quarter outlook',money(expected),'Q4 REVENUE · ESTIMATE',f'Projected Q4 revenue is {money(expected)}, with operating profit of {money(profit)}. The modeled revenue range runs from {money(interval["p10"])} to {money(interval["p90"])}. The biggest swing comes from {variance[0]["name"]}.',['Independent Bernoulli deal outcomes; historical stage rates are estimates, not promises.','Booked and recurring revenue assumed retained; fixed expense held constant.','Intervals exclude correlated losses, timing slippage and macroeconomic shocks.'])

def what_if(commit_drop=.10,region=None):
    base=forecast_quarter(region,0);scenario=forecast_quarter(region,commit_drop)
    delta=scenario['values']['profit']-base['values']['profit']
    revdelta=scenario['values']['revenue']-base['values']['revenue']
    values={'base_revenue':base['values']['revenue'],'scenario_revenue':scenario['values']['revenue'],'base_profit':base['values']['profit'],'scenario_profit':scenario['values']['profit'],'profit_change':delta,'revenue_change':revdelta,'profit_decline':abs(delta),'revenue_decline':abs(revdelta),'win_rate_drop_points':commit_drop*100,'scenario_range':scenario['values']['range'],'quarter':4,'year':2026}
    return result('what_if',values,'Revenue change = Σ(Commit amount × [max(0, historical win rate − point drop) − historical win rate]); profit change = revenue change × contribution margin.',{'commit_drop':commit_drop,'contribution_margin':base['values']['contribution_margin'],'commit_pipeline':sum(d['amount'] for d in _pipeline(region=region) if d['stage']=='Commit')},base['sources'],bar(['Baseline','Lower Commit win rate'],[values['base_profit'],values['scenario_profit']],title='Q4 operating profit scenario'),'Stress-test the quarter',money(delta),'PROFIT CHANGE · SCENARIO',f'A {commit_drop*100:g} percentage point drop in Commit win rate lowers projected Q4 profit by {money(abs(delta))}, to {money(values["scenario_profit"])}. Revenue falls by {money(abs(revdelta))}. The model holds operating expense constant.',scenario['method']['assumptions']+['Commit win rates are floored at zero; a large requested point drop can exceed the available probability.'])

def deal_risk(limit=5,region=None):
    pipe=_pipeline(region=region);ranked=[]
    for d in pipe:
        days=(date.fromisoformat(AS_OF)-date.fromisoformat(d['last_activity'])).days
        p=rates(d['region'])[d['stage']]['rate']
        adjustment=min(.55,max(0,days-14)*.005+d['slipped_quarters']*.065+(.12 if d['champion']=='Unconfirmed' else 0))
        win=max(.03,p-adjustment)
        reasons=[]
        if days>21:reasons.append(f'No activity for {days} days')
        if d['slipped_quarters']:reasons.append(f'Slipped {d["slipped_quarters"]} quarter(s)')
        if d['champion']=='Unconfirmed':reasons.append('Champion unconfirmed')
        if not reasons:reasons.append('Early stage conversion risk')
        ranked.append({**d,'days_inactive':days,'historical_win_rate':p,'modeled_loss_risk':1-win,'revenue_at_risk':round(d['amount']*(1-win)),'reasons':reasons})
    ranked.sort(key=lambda d:d['revenue_at_risk'],reverse=True);top=ranked[:limit]
    values={'deals':top,'count':len(top),'total_at_risk':sum(d['revenue_at_risk'] for d in top),'quarter':4,'year':2026}
    return result('deal_risk',values,'Risk-adjusted win rate = historical stage rate − inactivity/slippage/champion penalties; revenue at risk = amount × modeled loss risk.',{'inactive_penalty_per_day':.005,'inactivity_grace_days':14,'slip_penalty':.065,'champion_penalty':.12,'max_penalty':.55,'min_win_rate':.03,'ranking':'revenue at risk, not amount alone'},[source('pipeline',len(pipe),f'snapshot={AS_OF}; region={region or "all"}','deal'),source('closed_deals',len(_history()),'historical stage conversion','deal')],bar([d['name'] for d in top],[d['revenue_at_risk'] for d in top],title='Largest revenue exposures'),'Protect the quarter',money(values['total_at_risk']),'REVENUE AT RISK · ESTIMATE',f'The {len(top)} highest exposure deals put {money(values["total_at_risk"])} of modeled revenue at risk. {top[0]["name"]} leads the list: {"; ".join(top[0]["reasons"])}. Confirm the buying sponsor and recovery plan before the next forecast.', ['Heuristic risk adjustments are explicit assumptions, not calibrated model probabilities.','Ranking uses amount times estimated loss risk; it does not predict a realized loss.'])

def region_vs_plan():
    f=forecast_quarter();items=[]
    for r in f['values']['regions']:
        gap=r['revenue']-r['plan'];items.append({**r,'gap':gap,'shortfall':abs(min(0,gap)),'gap_percent':gap/r['plan'],'shortfall_percent':abs(min(0,gap/r['plan'])),'attainment':r['revenue']/r['plan']})
    items.sort(key=lambda x:x['gap']);worst=items[0]
    return result('region_vs_plan',{'regions':items,'furthest_behind':worst,'quarter':4,'year':2026},'Gap = projected revenue − revenue plan; attainment = projected revenue / plan.',{'comparison':'Q4 2026 forecast versus Q4 2026 plan'},f['sources'],bar([r['region'] for r in items],[r['gap'] for r in items],title='Forecast gap to plan'),'Close the regional gap',money(abs(worst['gap'])),'LARGEST PLAN SHORTFALL · ESTIMATE',f'{worst["region"]} is furthest behind plan, by {money(abs(worst["gap"]))}, or {percent(abs(worst["gap_percent"]))}. Its projected revenue is {money(worst["revenue"])} against a plan of {money(worst["plan"])}. Focus on its recoverable late-stage deals.',f['method']['assumptions'])

def pipeline_coverage():
    years=[]
    for year,snapshot in [(2025,'2025-10-07'),(2026,AS_OF)]:
        pipe=_pipeline(snapshot);plans=_plans(year);gap=sum(p['revenue_target']-p['booked_revenue']-p['recurring_revenue'] for p in plans)
        total=sum(d['amount'] for d in pipe);weighted=sum(d['amount']*rates(d['region'])[d['stage']]['rate'] for d in pipe)
        years.append({'year':year,'snapshot':snapshot,'open_pipeline':total,'remaining_target':gap,'coverage':total/gap,'weighted_coverage':weighted/gap,'deals':len(pipe)})
    change=years[1]['coverage']-years[0]['coverage']
    return result('pipeline_coverage',{'years':years,'coverage_change':change,'quarter':4},'Coverage = open pipeline / (quarter target − booked − recurring); compare the same calendar-date snapshots.',{'snapshot_dates':[y['snapshot'] for y in years],'same_quarter':True},[source('pipeline',sum(y['deals'] for y in years),'2025-10-07 and 2026-10-07 snapshots','deal-snapshot'),source('plans',8,'2025 and 2026 Q4','region-quarter')],bar([str(y['year']) for y in years],[y['coverage'] for y in years],unit='ratio',title='Pipeline coverage on the same date',series=[{'name':'Probability weighted','values':[y['weighted_coverage'] for y in years]}]),'Coverage, with context',f'{years[1]["coverage"]:.2f}×','OPEN PIPELINE / REMAINING TARGET',f'Pipeline coverage is {years[1]["coverage"]:.2f} times the remaining target, compared with {years[0]["coverage"]:.2f} times at the same point last year. Probability-weighted coverage is {years[1]["weighted_coverage"]:.2f} times. Coverage measures available pipeline, not guaranteed revenue.',['Both snapshots use the same historical rate basis; this avoids a shifting conversion-rate comparison.'])

def hiring_plan():
    reps=rows('SELECT * FROM reps');plans=rows('SELECT * FROM plans WHERE year=2027');current=rows('SELECT * FROM plans WHERE year=2026')
    target=sum(p['revenue_target'] for p in plans);base=sum(p['booked_revenue']+p['recurring_revenue'] for p in current)
    new_target=target-base;quota=sum(r['annual_quota'] for r in reps)/len(reps);attrition=sum(r['attrition'] for r in reps)/len(reps)
    productivity=.82;ramp=.75;retained_capacity=len(reps)*(1-attrition)*quota*productivity
    hires=max(0,math.ceil((new_target-retained_capacity)/(quota*productivity*ramp)));replacement=min(hires,math.ceil(len(reps)*attrition));growth=hires-replacement
    values={'hires':hires,'growth_hires':growth,'replacement_hires':replacement,'current_reps':len(reps),'annual_target':target,'retained_base_revenue':base,'new_sales_target':new_target,'average_quota':quota,'attrition':attrition,'quota_productivity':productivity,'first_year_ramp_factor':ramp,'retained_capacity':retained_capacity,'year':2027}
    return result('hiring_plan',values,'Total hires = ceil(max(0, new-sales target − retained rep capacity) / ramped new-rep capacity); split into attrition replacement and growth.',{'quota':quota,'productivity':productivity,'ramp_factor':ramp,'attrition':attrition,'retained_base':base},[source('reps',len(reps),'active synthetic reps','rep'),source('plans',len(plans)+len(current),'2026 retained base; 2027 annual target','region-quarter')],bar(['Growth capacity','Attrition replacement'],[growth,replacement],unit='count',title='Sales hiring requirement'),'Build next year’s capacity',str(hires),'REPS TO HIRE · ESTIMATE',f'Plan to hire {hires} reps: {growth} for growth and {replacement} to replace expected attrition. This supports a {money(target)} annual target, assuming {percent(productivity)} quota productivity and {percent(ramp)} first-year capacity. Hire early enough to complete the ramp.',['Retained booked and recurring base equals the current annual planned base.','First-year ramp applies to all new hires; attrition replacement is included in the total, never added twice.','No causal hiring forecast; scenario assumptions must be reviewed by the executive.'])

def _normalized(items,weights):
    scores={r['city']:0 for r in items};breakdown={r['city']:{} for r in items}
    for key,weight in weights.items():
        vs=[r[key] for r in items];lo=min(vs);hi=max(vs)
        for r in items:
            value=.5 if hi==lo else (r[key]-lo)/(hi-lo)
            if key in ['rep_cost','cost_per_seat','attrition','travel_hours']:value=1-value
            breakdown[r['city']][key]=value*weight*100;scores[r['city']]+=value*weight*100
    return scores,breakdown

def score_sites(persona='enterprise',cities=None):
    items=rows('SELECT * FROM sites WHERE persona=?',(persona,))
    if cities:items=[r for r in items if r['city'] in cities]
    weights={'rep_cost':.18,'talent_pool':.22,'cost_per_seat':.10,'nearby_pipeline':.28,'attrition':.12,'collaboration':.10} if persona=='enterprise' else {'rep_cost':.12,'talent_pool':.15,'cost_per_seat':.10,'nearby_pipeline':.20,'attrition':.08,'collaboration':.35}
    scores,drivers=_normalized(items,weights)
    ranked=sorted([{**r,'score':round(scores[r['city']],2),'drivers':drivers[r['city']]} for r in items],key=lambda r:r['score'],reverse=True)
    winner=ranked[0];wins={r['city']:0 for r in items};rng=random.Random(SEED)
    for _ in range(500):
        w={k:v*rng.uniform(.75,1.25) for k,v in weights.items()};s=sum(w.values());w={k:v/s for k,v in w.items()}
        result_scores,_=_normalized(items,w);wins[max(result_scores,key=result_scores.get)]+=1
    sensitivity=[{'city':r['city'],'wins':wins[r['city']],'share':wins[r['city']]/500} for r in ranked]
    values={'ranking':ranked,'recommended':winner['city'],'recommended_score':winner['score'],'weights':weights,'sensitivity':sensitivity,'sensitivity_trials':500,'score_scale':100,'candidate_count':len(ranked),'persona':persona}
    driver_labels={'rep_cost':'annual role cost','talent_pool':'talent pool','cost_per_seat':'facility cost','nearby_pipeline':'nearby opportunity','attrition':'retention','collaboration':'collaboration'}
    leaders=sorted(winner['drivers'],key=winner['drivers'].get,reverse=True)[:2]
    low_cost=min(r['rep_cost'] for r in ranked)
    values['decision_brief']={'drivers':[{'criterion':driver_labels[k],'contribution_points':winner['drivers'][k]} for k in leaders],'role_cost_above_lowest':winner['rep_cost']-low_cost,'lowest_role_cost':low_cost}
    driver_text=' and '.join(driver_labels[k] for k in leaders)
    tradeoff=f'{winner["city"]} costs {money(winner["rep_cost"])} per role annually, with {percent(winner["attrition"])} assumed attrition; its role cost is {money(winner["rep_cost"]-low_cost)} above the lowest cost option.'
    return result('score_sites',values,'Min–max normalize each criterion across selected sites, invert cost/attrition measures, then sum weight × normalized criterion × 100; perturb weights independently ±25%.',{'weights':weights,'sensitivity_weight_range':.25,'trials':500,'candidates':[r['city'] for r in items]},[source('sites',len(items),f'persona={persona}; selected cities','candidate site')],bar([r['city'] for r in ranked],[r['score'] for r in ranked],unit='score',title='Evidence-weighted site score'),'A decision you can defend',winner['city'],'PREFERRED SITE · SCENARIO',f'The evidence favors {winner["city"]}, scoring {winner["score"]:.1f} out of 100. It leads in {percent(sensitivity[0]["share"])} of weight-sensitivity trials. {driver_text.capitalize()} are the strongest weighted drivers. {tradeoff} Validate the talent pool and facility quotes before committing capital.',['Site inputs and weights are synthetic assumptions. Scores are preferences, not success probabilities.','Sensitivity share measures ranking stability, not calibrated decision confidence.','Changing the candidate set changes min–max normalization; compare only within the displayed set.'])

@lru_cache(maxsize=4)
def grant_forecast():
    history=rows('SELECT * FROM grant_history');pipeline=rows('SELECT * FROM grant_pipeline WHERE fiscal_year=2027');budget=rows('SELECT * FROM university_budget WHERE fiscal_year=2027')[0]
    rates_={}
    for stage in ['Drafting','Submitted','Under Review','Awarded pending']:
        cohort=[g for g in history if g['stage']==stage];rates_[stage]={'awarded':sum(g['awarded'] for g in cohort),'applications':len(cohort),'rate':sum(g['awarded'] for g in cohort)/len(cohort)}
    weighted=sum(g['amount']*rates_[g['stage']]['rate'] for g in pipeline);base=budget['awarded_research'];expected=round(base+weighted);rng=random.Random(SEED)
    sims=sorted(base+sum(g['amount'] for g in pipeline if rng.random()<rates_[g['stage']]['rate']) for _ in range(2000));interval={f'p{int(p*100)}':_quantile(sims,p) for p in [.1,.5,.9]}
    colleges=[{'college':c,'weighted_pipeline':round(sum(g['amount']*rates_[g['stage']]['rate'] for g in pipeline if g['college']==c))} for c in COLLEGES]
    values={'funding':expected,'awarded_funding':base,'weighted_pipeline':round(weighted),'range':interval,'stage_rates':rates_,'colleges':colleges,'target':budget['research_target'],'budget':budget['operating_budget'],'grants':len(pipeline),'fiscal_year':2027,'short_year':27,'simulations':2000,'percentiles':[10,50,90]}
    return result('grant_forecast',values,'Funding = awarded research + Σ(grant amount × historical award rate by stage); Bernoulli award simulations produce the interval.',{'awarded':base,'stage_rates':rates_,'simulations':2000},[source('grant_pipeline',len(pipeline),'FY27 open grant pipeline','grant'),source('grant_history',len(history),'2024–2026 stage cohorts','grant application'),source('university_budget',1,'FY27','fiscal year')],bar([c['college'] for c in colleges],[c['weighted_pipeline'] for c in colleges],title='Expected pipeline awards by college'),'Research, projected',money(expected),'FY27 RESEARCH FUNDING · ESTIMATE',f'Projected FY27 research funding is {money(expected)}, including {money(base)} already awarded. The modeled range is {money(interval["p10"])} to {money(interval["p90"])}. Expected new awards contribute {money(weighted)}.',['Independent award decisions; sponsor-level correlation and policy changes are excluded.','FY27 modeled funding is award value, not cash receipts or expense recognition.'])

def sponsor_concentration():
    hist=rows('SELECT * FROM grant_history WHERE year=2026 AND awarded=1');total=sum(g['amount'] for g in hist)
    amounts={s:sum(g['amount'] for g in hist if g['sponsor']==s) for s in ['NSF','NIH','DOE','DoD','Industry']}
    sponsors=sorted([{'sponsor':s,'amount':a,'share':a/total} for s,a in amounts.items()],key=lambda s:s['amount'],reverse=True)
    hhi=sum(s['share']**2 for s in sponsors);top=sponsors[0];cut=.20;exposure=round(top['amount']*cut)
    values={'sponsors':sponsors,'total_awards':total,'largest':top,'hhi':hhi,'stress_cut':cut,'stress_exposure':exposure,'year':2026}
    return result('sponsor_concentration',values,'Sponsor share = awarded amount / total awards; concentration = Σ(share²); stress exposure = largest sponsor awards × assumed cut.',{'stress_cut':cut,'period':2026},[source('grant_history',len(hist),'2026 awarded=1','awarded grant')],bar([s['sponsor'] for s in sponsors],[s['amount'] for s in sponsors],title='Award value by sponsor'),'Understand the dependency',percent(top['share']),'LARGEST SPONSOR SHARE · ACTUAL SYNTHETIC',f'{top["sponsor"]} supplies {percent(top["share"])} of the latest year’s awarded funding, or {money(top["amount"])}. A {percent(cut)} cut to that sponsor would expose {money(exposure)} of funding under this stress scenario. Broaden the sponsor mix and protect bridge funding.',['Stress exposure is an illustrative cut to award value; it is not a forecast of sponsor policy.'])

def enrollment_forecast():
    history=rows('SELECT * FROM enrollment');current=rows('SELECT * FROM enrollment_current');colleges=[]
    for c in current:
        hist=[h for h in history if h['college']==c['college']];rate=sum(h['enrolled'] for h in hist)/sum(h['deposited'] for h in hist)
        count=round(c['deposited']*rate);colleges.append({**c,'retention_from_deposit':rate,'projected_enrolled':count,'yield':count/c['admitted']})
    enrolled=sum(c['projected_enrolled'] for c in colleges);admitted=sum(c['admitted'] for c in colleges);deposited=sum(c['deposited'] for c in colleges)
    yield_=enrolled/admitted;historical_yield=sum(h['enrolled'] for h in history)/sum(h['admitted'] for h in history)
    values={'enrolled':enrolled,'admitted':admitted,'deposited':deposited,'yield':yield_,'historical_yield':historical_yield,'colleges':colleges,'year':2027}
    return result('enrollment_forecast',values,'College projection = deposits × pooled historical enrolled/deposited; total enrollment yield = summed projected enrolled / summed admitted.',{'population':'2027 fall admitted cohort','historical_cohorts':[2024,2025,2026],'denominator':'admitted students'},[source('enrollment',len(history),'2024–2026 final cohorts','college-year'),source('enrollment_current',len(current),'fall 2027 admissions snapshot','college-year')],bar([c['college'] for c in colleges],[c['projected_enrolled'] for c in colleges],unit='count',title='Projected fall entrants by college'),'Plan the incoming class',percent(yield_),'FALL ENROLLMENT YIELD · ESTIMATE',f'Projected fall enrollment yield is {percent(yield_)}, equivalent to {enrolled:,} entrants from {admitted:,} admitted students. The estimate applies each college’s historical deposit-to-enrollment rate to current deposits. Prioritize admitted-student outreach where yield is lowest.',['Historical deposit retention is assumed stable; additional future deposits and attrition shocks are excluded.','Yield denominator is admitted students, not applicants or deposits.'])

def board_summary():
    f=forecast_quarter();r=region_vs_plan();risk=deal_risk();v=f['values'];worst=r['values']['furthest_behind']
    values={'revenue':v['revenue'],'profit':v['profit'],'range':v['range'],'plan_gap':worst['gap'],'plan_shortfall':abs(worst['gap']),'weakest_region':worst['region'],'risk_exposure':risk['values']['total_at_risk'],'quarter':4,'year':2026}
    return result('board_summary',values,'Consolidates forecast, region-to-plan comparison, and top-deal exposure without changing their definitions.',{'tools':['forecast_quarter','region_vs_plan','deal_risk']},f['sources'],f['chart'],'The board brief',money(v['revenue']),'Q4 REVENUE · ESTIMATE',f'We project Q4 revenue of {money(v["revenue"])} and operating profit of {money(v["profit"])}. {worst["region"]} has the largest plan shortfall at {money(abs(worst["gap"]))}. The leading deal exposures total {money(risk["values"]["total_at_risk"])}. Our priorities are late-stage recovery, sponsor confirmation, and protecting margin.',f['method']['assumptions'])

TOOLS={f.__name__:f for f in [forecast_quarter,what_if,deal_risk,region_vs_plan,pipeline_coverage,hiring_plan,score_sites,grant_forecast,sponsor_concentration,enrollment_forecast,board_summary]}
def execute(tool,kwargs=None):
    import copy
    return copy.deepcopy(TOOLS[tool](**(kwargs or {})))
