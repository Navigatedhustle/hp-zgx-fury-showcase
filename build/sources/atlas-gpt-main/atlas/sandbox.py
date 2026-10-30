"""Each execution gets an ephemeral workdir and separate read-only database copy."""
import json,os,shutil,signal,subprocess,tempfile,time,sys
from pathlib import Path
from atlas.config import DB,ROOT

def run(code,language='python',timeout=10):
    if language not in ['sql','python']:raise ValueError('Only SQL and Python are executable')
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='atlas-code-') as work, tempfile.TemporaryDirectory(prefix='atlas-db-') as database:
        copy=Path(database)/'atlas.sqlite';shutil.copyfile(DB,copy);copy.chmod(0o444)
        job=Path(work)/'job.json';job.write_text(json.dumps({'code':code,'language':language,'database':str(copy)}))
        stdout_file=(Path(work)/'.stdout').open('wb');stderr_file=(Path(work)/'.stderr').open('wb')
        process=subprocess.Popen([sys.executable,'-I',str(ROOT/'atlas/sandbox_worker.py'),str(job)],cwd=work,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout_file,stderr=stderr_file,start_new_session=True)
        timed_out=False
        try:process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(process.pid,signal.SIGKILL);process.wait()
        stdout_file.close();stderr_file.close()
        stdout=(Path(work)/'.stdout').read_text(errors='replace')[:100000];stderr=(Path(work)/'.stderr').read_text(errors='replace')[:20000];table=[];chart=None
        for line in stdout.splitlines():
            try:
                parsed=json.loads(line)
                if isinstance(parsed,dict):table=parsed.get('table',table);chart=parsed.get('chart',chart)
            except ValueError:pass
        files=[{'name':p.name,'content':p.read_text(errors='replace')[:100000]} for p in Path(work).iterdir() if p.is_file() and p.name not in ['job.json','.stdout','.stderr']]
        return {'executed':True,'success':process.returncode==0 and not timed_out,'returncode':process.returncode,'timeout':timed_out,'stdout':stdout,'stderr':stderr,'table':table,'chart':chart,'files':files,'elapsed_ms':(time.perf_counter()-started)*1000,'isolation':'Landlock filesystem allowlist + seccomp socket/process denial; 384 MiB memory, 10 s wall limit; separate read-only database copy'}
