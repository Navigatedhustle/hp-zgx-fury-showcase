"""Accounting, power integration, open presenter controls, and framing contracts."""
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from showcase_app import event
from showcase_app.frame_policy import station_ancestors


def row(identity='one', **changes):
    return {'id':identity,'demo':'atlas','status':'complete','input_tokens':1000,
            'output_tokens':200,'started':100,'seconds':1,**changes}


def test_physical_requests_count_once_and_only_final_real_usage_is_priced():
    rows=[row(),row(),row('recorded',demo='recorded'),row('missing',input_tokens=None),
          row('active',status='active'),row('failed',status='failed',input_tokens=None,output_tokens=None)]
    eligible,costs=event.price_rows(rows,[{'id':'price','input':2,'output':10}])
    assert list(eligible)==['one']
    assert costs['price']==pytest.approx(.004)


def test_long_context_rates_are_per_request_and_promotion_expires_offline():
    model={'id':'price','input':10,'output':50,'long_threshold':1000,'long_input':20,'long_output':75}
    _,costs=event.price_rows([row(),row('long',input_tokens=1001)], [model])
    assert costs['price']==pytest.approx(.01+.01+.02002+.015)
    before=event.prices(date(2026,11,30))['models'][-1]
    after=event.prices(date(2026,12,1))['models'][-1]
    assert (before['input'],before['output'])==(2,10)
    assert (after['input'],after['output'])==(4,20)


def test_invalid_numeric_usage_is_not_fabricated():
    for value in [None,float('nan'),float('inf'),-1,True,'200']:
        assert not event.price_rows([row(output_tokens=value)],[])[0]


@pytest.fixture
def monitor(tmp_path,monkeypatch):
    monkeypatch.setattr(event,'ROOT',tmp_path)
    directory=tmp_path/'state/slides';directory.mkdir(parents=True)
    with sqlite3.connect(directory/'app.db') as db:
        db.execute('CREATE TABLE events(id TEXT PRIMARY KEY,demo TEXT,status TEXT,input_tokens INTEGER,output_tokens INTEGER,started REAL,seconds REAL)')
    return event.Monitor(event.Store(tmp_path/'event.sqlite'))


def live(watts):
    return {'gpu_memory_MiB_util_pct_power_W':'100,0,'+str(watts),
            'services':{'language':{'connected':True,'data':{'active':{},'queued':{}}},
                        'image':{'connected':True,'data':{'active':0,'queued':0}}}}


def test_power_is_trapezoidal_and_missing_samples_and_gaps_are_not_extrapolated(monitor):
    t=monitor.store.current()['started']
    monitor.snapshot(live(100),t+1)
    result=monitor.snapshot(live(300),t+11)
    assert result['totals']['energies_kwh']['GPU only']==pytest.approx(200*10/3_600_000)
    monitor.snapshot(live('N/A'),t+21)
    monitor.snapshot(live(500),t+31)
    result=monitor.snapshot(live(500),t+61)
    assert result['totals']['coverage_seconds']['GPU only']==pytest.approx(10)


def test_energy_survives_restart_without_filling_downtime(monitor):
    t=monitor.store.current()['started'];monitor.snapshot(live(100),t+1)
    first=monitor.snapshot(live(100),t+11)
    restarted=event.Monitor(monitor.store)
    after=restarted.snapshot(live(100),t+100)
    assert after['totals']['energies_kwh']==first['totals']['energies_kwh']


def test_empty_power_is_unavailable_and_stale_meter_never_changes_scope(tmp_path,monkeypatch):
    assert event.read_power({'gpu_memory_MiB_util_pct_power_W':''},100)['watts'] is None
    meter=tmp_path/'meter.json';monkeypatch.setenv('FURY_POWER_METER_FILE',str(meter))
    meter.write_text(json.dumps({'timestamp':100,'watts':1200}))
    assert event.read_power(live(200),105)['scope']=='whole system'
    assert event.read_power(live(200),105)['watts']==1200
    assert event.read_power(live(200),130)['watts'] is None
    assert event.read_power(live(200),130)['scope']=='whole system'


def test_reset_preserves_jobs_ledger_and_prior_event_history(monitor):
    t=monitor.store.current()['started']
    with sqlite3.connect(event.ROOT/'state/slides/app.db') as db:
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',('live','atlas','complete',1000,200,t+1,1))
    first=monitor.snapshot(live(100),t+2);old=first['session']['id']
    monitor.store.reset('Next event')
    assert monitor.store.current()['id']!=old
    assert monitor.store.history(old)
    with sqlite3.connect(event.ROOT/'state/slides/app.db') as db:
        assert db.execute('SELECT count(*) FROM events').fetchone()[0]==1


@pytest.mark.parametrize('origin,hostname,allowed',[
    (None,'localhost',True),('http://localhost:8080','localhost',True),
    ('http://localhost:8765','localhost',True),('https://station.example','station.example',True),
    ('https://evil.example','localhost',False),('null','localhost',False)])
def test_shared_presenter_controls_accept_station_origins_without_a_code(origin,hostname,allowed):
    assert event.station_origin_allowed(origin,hostname) is allowed


@pytest.mark.parametrize('host,expected',[
    ('localhost',"'self' http://localhost:8080 http://127.0.0.1:8080"),
    ('demo.'+'tail123.ts.net',"'self' https://"+'demo.'+'tail123.ts.net'),
    ('evil.example',"'self'"),('evil.ts.net.example',"'self'"),
    ('demo.'+'tail123.ts.net; script-src *',"'self'"),
])
def test_station_framing_only_allows_own_private_host(host,expected):
    assert station_ancestors(host)==expected


def test_reported_usage_of_failed_calls_is_not_discarded():
    eligible,costs=event.price_rows([row('measured-failure',status='failed')],[{'id':'price','input':2,'output':10}])
    assert len(eligible)==1
    assert costs['price']==pytest.approx(.004)


def test_factory_busy_is_workflow_capacity_even_between_model_calls(monitor):
    sample=live(100)
    sample['services']['factory_jobs']={'data':{'active':1,'limit':1}}
    result=monitor.snapshot(sample)
    assert result['activity']['agent']['active']==0
    assert result['capacity']['agent']=={'active':1,'limit':1}
