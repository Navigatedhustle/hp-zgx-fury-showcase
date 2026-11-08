"""Actual Landlock/seccomp worker probes; synthetic private canary only."""
import json
from pathlib import Path
import sqlite3
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build/sources/atlas-gpt-main'))


@pytest.mark.parametrize('target',['stolen.txt','.stdout','.stderr'])
def test_parent_never_follows_sandbox_created_artifact_links(tmp_path,monkeypatch,target):
    from atlas import sandbox
    database=tmp_path/'fictional.sqlite'
    with sqlite3.connect(database) as c:c.execute('CREATE TABLE fictional (value TEXT)')
    monkeypatch.setattr(sandbox,'DB',database)
    canary=tmp_path/'private-canary.txt';canary.write_text('fictional-private-artifact-canary')
    code='import os\np='+repr(target)+'\nif os.path.lexists(p):os.unlink(p)\nos.symlink('+repr(str(canary))+',p)\n'
    result=sandbox.run(code)
    assert canary.read_text() not in json.dumps(result), 'Parent followed an untrusted artifact link outside the sandbox'
    assert canary.read_text()=='fictional-private-artifact-canary'


def test_legitimate_read_only_sql_and_created_artifact_are_retained(tmp_path,monkeypatch):
    from atlas import sandbox
    database=tmp_path/'fictional.sqlite'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE fictional (value TEXT)');c.execute("INSERT INTO fictional VALUES ('synthetic')")
    monkeypatch.setattr(sandbox,'DB',database)
    result=sandbox.run('SELECT value FROM fictional','sql')
    assert result['success'] and result['table']==[{'value':'synthetic'}]
    result=sandbox.run('from pathlib import Path\nPath("result.txt").write_text("fictional result")\nprint("verified")')
    assert result['success'] and result['stdout']=='verified\n'
    assert result['files']==[{'name':'result.txt','content':'fictional result'}]


def test_generated_code_cannot_change_its_host_parent_resource_limits(tmp_path):
    import subprocess
    canary_db=tmp_path/'fictional.sqlite'
    with sqlite3.connect(canary_db) as c:c.execute('CREATE TABLE fictional (value TEXT)')
    coordinator='''import json,resource,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from atlas import sandbox
sandbox.DB=Path(sys.argv[2]);before=resource.getrlimit(resource.RLIMIT_NOFILE)
result=sandbox.run('import os,resource\\nresource.prlimit(os.getppid(),resource.RLIMIT_NOFILE,(64,64))')
print(json.dumps({'before':before,'after':resource.getrlimit(resource.RLIMIT_NOFILE),'worker_success':result['success']}))
'''
    process=subprocess.run([sys.executable,'-c',coordinator,str(ROOT/'build/sources/atlas-gpt-main'),str(canary_db)],cwd=ROOT,capture_output=True,text=True,check=True)
    result=json.loads(process.stdout)
    assert result['after']==result['before'], 'Generated code altered the host coordinator resource limit'
