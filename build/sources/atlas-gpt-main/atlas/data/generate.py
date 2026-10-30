"""Reproducible fictional business data. No outside company data is used."""
import argparse
import csv
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from atlas.config import DB, AS_OF

REGIONS = ['West', 'Central', 'East', 'International']
STAGES = ['Prospect','Qualify','Propose','Commit']
COLLEGES = ['Engineering','Medicine','Science','Arts & Humanities','Business','Education']
SPONSORS = ['NSF','NIH','DOE','DoD','Industry']

def generate(seed=42, db=DB):
    rng = random.Random(seed)
    db.parent.mkdir(exist_ok=True,parents=True)
    con = sqlite3.connect(db)
    tables = {
        'metadata':'key TEXT PRIMARY KEY, value TEXT',
        'accounts':'id TEXT PRIMARY KEY, name TEXT, region TEXT, city TEXT, annual_contract INTEGER',
        'reps':'id TEXT PRIMARY KEY, name TEXT, region TEXT, annual_quota INTEGER, ramp_months INTEGER, attrition REAL',
        'closed_deals':'id TEXT PRIMARY KEY, account_id TEXT, owner_id TEXT, region TEXT, year INTEGER, amount INTEGER, outcome TEXT, max_stage INTEGER, close_date TEXT',
        'pipeline':'id TEXT PRIMARY KEY, name TEXT, account_id TEXT, owner_id TEXT, region TEXT, stage TEXT, amount INTEGER, close_date TEXT, last_activity TEXT, slipped_quarters INTEGER, champion TEXT, snapshot TEXT',
        'pnl':'year INTEGER, quarter INTEGER, region TEXT, revenue INTEGER, cogs INTEGER, sales_opex INTEGER, research_opex INTEGER, admin_opex INTEGER, PRIMARY KEY(year,quarter,region)',
        'plans':'year INTEGER, quarter INTEGER, region TEXT, revenue_target INTEGER, booked_revenue INTEGER, recurring_revenue INTEGER, remaining_opex INTEGER, variable_margin REAL, PRIMARY KEY(year,quarter,region)',
        'sites':'persona TEXT, city TEXT, rep_cost INTEGER, talent_pool INTEGER, cost_per_seat INTEGER, nearby_accounts INTEGER, nearby_pipeline INTEGER, attrition REAL, collaboration REAL, travel_hours REAL, PRIMARY KEY(persona,city)',
        'grant_history':'id TEXT PRIMARY KEY, college TEXT, sponsor TEXT, year INTEGER, stage TEXT, amount INTEGER, awarded INTEGER',
        'grant_pipeline':'id TEXT PRIMARY KEY, title TEXT, college TEXT, sponsor TEXT, stage TEXT, amount INTEGER, fiscal_year INTEGER, deadline TEXT',
        'enrollment':'year INTEGER, college TEXT, applications INTEGER, admitted INTEGER, deposited INTEGER, enrolled INTEGER, PRIMARY KEY(year,college)',
        'enrollment_current':'year INTEGER, college TEXT, applications INTEGER, admitted INTEGER, deposited INTEGER, PRIMARY KEY(year,college)',
        'university_budget':'fiscal_year INTEGER PRIMARY KEY, operating_budget INTEGER, awarded_research INTEGER, research_target INTEGER',
    }
    for table, ddl in tables.items():
        con.execute(f'DROP TABLE IF EXISTS {table}')
        con.execute(f'CREATE TABLE {table} ({ddl})')
    def add(table, row):
        con.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in row)})',row)
    for k,v in {'seed':seed,'as_of':AS_OF,'classification':'synthetic','generator_version':1,'currency':'USD','research_fiscal_year':'2026-07-01 through 2027-06-30'}.items():add('metadata',(k,str(v)))
    cities = ['Phoenix','Denver','Albuquerque','Austin','Salt Lake City']
    for i in range(600):
        region=REGIONS[i%4]
        add('accounts',(f'A{i+1:04}',f'Meridian Partner {i+1:03}',region,cities[i%5],rng.randrange(700000,4500000,1000)))
    for i in range(120):add('reps',(f'R{i+1:03}',f'Alex {chr(65+i%26)}{i+1:03}',REGIONS[i%4],2*rng.randrange(4500000,7500000,100000),6,round(rng.uniform(.07,.17),3)))
    for year in [2023,2024,2025]:
        for i in range(3600):
            ac=rng.randrange(600); won=rng.random()<[.48,.44,.42,.39][ac%4]
            max_stage=3 if won else rng.choices([0,1,2,3],[20,25,32,23])[0]
            add('closed_deals',(f'H{year}-{i+1:04}',f'A{ac+1:04}',f'R{ac%120+1:03}',REGIONS[ac%4],year,rng.randrange(70000,1250000,1000),'Won' if won else 'Lost',max_stage,f'{year}-{rng.randrange(1,13):02}-{rng.randrange(1,28):02}'))
        for quarter in range(1,5):
            for j,region in enumerate(REGIONS):
                rev=round((128000000+j*11000000)*(1+.06*(year-2023))*(1+.035*(quarter-2)))
                add('pnl',(year,quarter,region,rev,round(rev*.43),round(rev*.145),round(rev*.11),round(rev*.075)))
    for snapshot, count, scale in [('2025-10-07',450,.94),(AS_OF,520,1)]:
        for i in range(count):
            ac=rng.randrange(600); region=REGIONS[ac%4]; stage=rng.choices(STAGES,[15,24,31,30])[0]
            amount=int(rng.randrange(160000,2200000,10000)*scale)
            close=date(int(snapshot[:4]),10,8)+timedelta(days=rng.randrange(84))
            inactive=rng.randrange(1,72); slip=rng.choices([0,1,2,3],[60,24,12,4])[0]
            add('pipeline',(f'D{snapshot[:4]}-{i+1:04}',f'{["Cloud modernization","Analytics expansion","Edge deployment","Platform renewal"][i%4]} · {ac+1:03}',f'A{ac+1:04}',f'R{ac%120+1:03}',region,stage,amount,close.isoformat(),(date.fromisoformat(snapshot)-timedelta(days=inactive)).isoformat(),slip,rng.choice(['Confirmed','Confirmed','Unconfirmed']),snapshot))
    for year in [2025,2026,2027]:
        for quarter in range(1,5):
            for j,region in enumerate(REGIONS):
                target=round((145000000+j*12500000)*(1+.08*(year-2025))*(1+.025*(quarter-2)))
                base=round(target*[.51,.53,.49,.45][j])
                add('plans',(year,quarter,region,target,round(base*.19),round(base*.81),round(target*.205),.57))
    enterprise_sites=[('Phoenix',128000,8800,15600,140,184000000,.14,.69,1.9),('Denver',151000,11200,19400,115,151000000,.09,.85,2.1),('Albuquerque',112000,3600,11200,64,91000000,.08,.77,2.5),('Austin',158000,9800,21500,98,139000000,.15,.81,2.8),('Salt Lake City',136000,5700,16800,83,119000000,.10,.74,2.3)]
    for row in enterprise_sites:add('sites',('enterprise',*row))
    for row in [('Phoenix',122000,4600,17800,28,71000000,.13,.67,2.0),('Denver',143000,7800,21600,45,102000000,.08,.92,2.1),('Albuquerque',113000,5300,14100,39,92000000,.07,.88,2.4),('Austin',152000,6900,22500,34,89000000,.14,.83,2.9),('Salt Lake City',134000,4700,18500,31,78000000,.09,.80,2.6)]:add('sites',('university',*row))
    for year in [2024,2025,2026]:
        for i in range(720):
            sponsor=rng.choices(SPONSORS,[24,41,14,9,12])[0];stage=rng.choice(['Drafting','Submitted','Under Review','Awarded pending'])
            awarded=int(rng.random()<{'Drafting':.15,'Submitted':.31,'Under Review':.53,'Awarded pending':.94}[stage])
            add('grant_history',(f'G{year}-{i:04}',COLLEGES[i%6],sponsor,year,stage,rng.randrange(100000,2000000,10000),awarded))
    for i in range(230):
        add('grant_pipeline',(f'GP{i+1:04}',f'{["Resilient infrastructure","Precision health","Clean energy","Learning futures"][i%4]} {i+1:03}',COLLEGES[i%6],rng.choices(SPONSORS,[24,41,14,9,12])[0],rng.choices(['Drafting','Submitted','Under Review','Awarded pending'],[20,25,35,20])[0],rng.randrange(120000,2800000,10000),2027,f'2027-{rng.randrange(1,13):02}-15'))
    for year in [2024,2025,2026]:
        for j,college in enumerate(COLLEGES):
            applications=round((6200-j*450)*(1+.045*(year-2024)));admitted=round(applications*(.56+j*.017));deposited=round(admitted*(.27+j*.013));enrolled=round(deposited*(.92-j*.008))
            add('enrollment',(year,college,applications,admitted,deposited,enrolled))
    for j,college in enumerate(COLLEGES):
        applications=round((6200-j*450)*1.15);admitted=round(applications*(.56+j*.017));deposited=round(admitted*(.27+j*.013))
        add('enrollment_current',(2027,college,applications,admitted,deposited))
    add('university_budget',(2027,900000000,126000000,310000000))
    con.commit()
    csvdir=db.parent/'csv';csvdir.mkdir(exist_ok=True)
    for table in tables:
        cur=con.execute(f'SELECT * FROM {table}')
        with (csvdir/f'{table}.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow([d[0] for d in cur.description]);w.writerows(cur.fetchall())
    counts={table:con.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables}
    (db.parent/'manifest.json').write_text(json.dumps({'seed':seed,'as_of':AS_OF,'classification':'synthetic','tables':counts},indent=2))
    con.close();print(json.dumps(counts))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=42);p.add_argument('--db',type=Path,default=DB)
    a=p.parse_args();generate(a.seed,a.db)
