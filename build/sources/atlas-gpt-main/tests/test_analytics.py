import math
import pytest
from atlas import analytics as a
from atlas.config import GOLDEN
from atlas.router import route
from atlas.grounding import check,grounded_answer

def test_all_golden_questions_route_and_ground():
    for persona,expected,q in GOLDEN:
        tool,kwargs=route(q,persona)
        assert tool==expected,(q,tool)
        output=a.execute(tool,kwargs)
        assert check(output['answer'],output)['passed'],(tool,check(output['answer'],output))
        assert {'values','method','sources','chart'}<=output.keys()

def test_forecast_reconciles_and_is_reproducible():
    f=a.forecast_quarter()['values']
    assert f['revenue']==sum(r['revenue'] for r in f['regions'])
    assert f['profit']==round(f['revenue']*f['contribution_margin']-f['opex'])
    assert f['range']['p10']<=f['range']['p50']<=f['range']['p90']
    before=f['range'];a.forecast_quarter.cache_clear()
    assert before==a.forecast_quarter()['values']['range']

def test_scenario_delta_matches_exposed_commit_amount():
    r=a.what_if()['values']
    commit=sum(d['amount'] for d in a._pipeline() if d['stage']=='Commit')
    assert abs(r['revenue_change']+commit*.10)<=1
    assert abs(r['profit_change']-r['revenue_change']*.57)<=1

def test_large_scenario_drop_stops_at_zero_probability():
    baseline=a.forecast_quarter()['values']
    scenario=a.what_if(commit_drop=1)['values']
    expected_loss=sum(d['amount']*a.rates(d['region'])['Commit']['rate'] for d in a._pipeline() if d['stage']=='Commit')
    assert abs(scenario['revenue_change']+expected_loss)<=1
    assert scenario['scenario_revenue']>=baseline['base_revenue']
    assert scenario['profit_decline']==-scenario['profit_change']

def test_historical_rates_use_stage_cohorts():
    rates=a.rates()
    assert all(0<r['rate']<1 for r in rates.values())
    assert rates['Commit']['reached']<rates['Prospect']['reached']
    assert rates['Commit']['rate']>rates['Prospect']['rate']

def test_site_scores_and_sensitivity_are_not_probabilities():
    r=a.score_sites()['values']
    assert abs(sum(r['weights'].values())-1)<1e-10
    assert sum(x['wins'] for x in r['sensitivity'])==500
    assert all(0<=x['score']<=100 for x in r['ranking'])
    assert r['recommended']==r['ranking'][0]['city']

def test_enrollment_is_weighted_at_student_grain():
    v=a.enrollment_forecast()['values']
    assert v['enrolled']==sum(c['projected_enrolled'] for c in v['colleges'])
    assert v['yield']==v['enrolled']/v['admitted']

def test_grounding_rejects_hallucinations_and_accepts_scaled_rounding():
    result=a.forecast_quarter()
    assert not check('Revenue is $999.99B.',result)['passed']
    text,report=grounded_answer('Revenue is $999.99B.',result)
    assert report['fallback'] and text==result['answer']
    assert check('Revenue is $724.3 million.',result)['passed']
    assert not check('Revenue is nine hundred ninety nine billion dollars.',result)['passed']
    assert check('Revenue is seven hundred twenty four point three million dollars.',result)['passed']

def test_hiring_capacity_reconciles_without_double_counting_attrition():
    v=a.hiring_plan()['values']
    assert v['hires']==v['growth_hires']+v['replacement_hires']
    capacity=v['retained_capacity']+v['hires']*v['average_quota']*v['quota_productivity']*v['first_year_ramp_factor']
    assert capacity>=v['new_sales_target']
    assert capacity-v['average_quota']*v['quota_productivity']*v['first_year_ramp_factor']<v['new_sales_target']

def test_unknown_intents_do_not_invent_answers():
    assert route('What is the weather tomorrow?')[0] is None

def test_grounding_preserves_sign_entity_ids_and_metric_bindings():
    output=a.forecast_quarter()
    assert not check('Projected revenue is '+a.money(output['values']['profit'])+'.',output)['passed']
    assert not check('Projected profit is '+a.money(output['values']['revenue'])+'.',output)['passed']
    assert not check(output['answer'].replace('Cloud modernization · 140','Cloud modernization at 140'),output)['passed']
    assert not check('Projected Q4 revenue is −'+a.money(output['values']['revenue'])+'. '+output['answer'],output)['passed']

def test_runtime_network_guard_accepts_only_loopback():
    from atlas.offline_guard import is_local
    assert is_local(('127.0.0.1',8201)) and is_local(('::1',8200))
    assert not is_local(('192.168.1.1',443))
    assert not is_local(('api.example.com',443))
