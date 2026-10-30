"""Deterministic read-only calculations over an entirely invented scenario."""
import json
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load_evidence():
    data=json.loads((ROOT/'data/suppliers.json').read_text())
    docs=json.loads((ROOT/'data/documents.json').read_text())['documents']
    scenario=data['scenario'];comparison=[]
    as_of=date.fromisoformat(scenario['as_of']);deadline=date.fromisoformat(scenario['needed_by'])
    for supplier in data['suppliers']:
        row=dict(supplier)
        goods=Decimal(str(row['unit_price_gbp']))*row['units']
        total=goods+Decimal(str(row['freight_gbp']))
        row.update(goods_cost_gbp=float(goods),delivered_cost_gbp=float(total),budget_headroom_gbp=float(Decimal(str(scenario['budget_gbp']))-total),delivery_date=(as_of+timedelta(days=row['delivery_days'])).isoformat())
        row['checks']={'deadline':date.fromisoformat(row['delivery_date'])<=deadline,'reliability':row['on_time_pct']>=scenario['min_on_time_pct'],'certificate_evidence':row['iso9001_evidence_supplied'],'delivered_budget':total<=scenario['budget_gbp'],'permitted_region':row['data_region'] in scenario['permitted_regions']}
        row['passes_all_supplied_checks']=all(row['checks'].values());comparison.append(row)
    return {'notice':data['notice'],'company':data['company'],'scenario':scenario,'documents':docs,'comparison':comparison}
