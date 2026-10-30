"""Synthetic accounting fixtures stay in temporary directories, outside live telemetry."""
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from showcase_app import operator

class AccountingTests(unittest.TestCase):
    def test_only_dispatched_calls_import_once_and_missing_usage_stays_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runs=root/'build/sources/fury_agent_factory/runs';runs.mkdir(parents=True)
            source=runs/'fixture.sqlite';target=root/'events.sqlite'
            call={'id':'call-one','agent':'Evidence Analyst','model':'synthetic-test','status':'cancelled','queued_at':100.,'started_at':None,'ended_at':101.,'usage':None}
            with sqlite3.connect(source) as c:
                c.execute('CREATE TABLE metadata(id TEXT,payload TEXT)');c.execute('CREATE TABLE calls(payload TEXT)');c.execute('INSERT INTO metadata VALUES (?,?)',('run',json.dumps({'run_id':'synthetic-fixture'})));c.execute('INSERT INTO calls VALUES (?)',(json.dumps(call),))
            with sqlite3.connect(target) as c:c.execute('CREATE TABLE events(id TEXT PRIMARY KEY,demo TEXT,role TEXT,model TEXT,status TEXT,started REAL,seconds REAL,input_tokens INTEGER,output_tokens INTEGER,cached_tokens INTEGER,error TEXT)')
            with patch.object(operator,'ROOT',root),patch.object(operator,'connect',side_effect=lambda:sqlite3.connect(target)):
                operator.sync_agent()
                with sqlite3.connect(target) as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],0)
                call['started_at']=100.1
                with sqlite3.connect(source) as c:c.execute('UPDATE calls SET payload=?',(json.dumps(call),))
                operator.sync_agent();operator.sync_agent()
                with sqlite3.connect(target) as c:self.assertEqual(c.execute('SELECT id,input_tokens,output_tokens FROM events').fetchall(),[('synthetic-fixture:call-one',None,None)])
                call.update(status='complete',usage={'input':100,'output':20,'cached':None})
                with sqlite3.connect(source) as c:c.execute('UPDATE calls SET payload=?',(json.dumps(call),))
                operator.sync_agent();operator.sync_agent()
                with sqlite3.connect(target) as c:self.assertEqual(c.execute('SELECT count(*),sum(input_tokens),sum(output_tokens) FROM events').fetchone(),(1,100,20))
