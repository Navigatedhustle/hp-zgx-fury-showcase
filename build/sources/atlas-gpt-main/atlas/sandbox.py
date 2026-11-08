"""Each execution gets an ephemeral workdir and separate read-only database copy."""
import json,os,shutil,stat,subprocess,tempfile,time,sys
from pathlib import Path
from atlas.config import DB,ROOT

def run(code,language='python',timeout=10):
    if language not in ['sql','python']:raise ValueError('Only SQL and Python are executable')
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='atlas-code-') as work, tempfile.TemporaryDirectory(prefix='atlas-db-') as database:
        copy=Path(database)/'atlas.sqlite';shutil.copyfile(DB,copy);copy.chmod(0o444)
        job=Path(work)/'job.json';job.write_text(json.dumps({'code':code,'language':language,'database':str(copy)}))
        stdout_file=tempfile.TemporaryFile();stderr_file=tempfile.TemporaryFile()
        process=subprocess.Popen([sys.executable,'-I',str(ROOT/'atlas/sandbox_worker.py'),str(job)],cwd=work,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},stdout=stdout_file,stderr=stderr_file,start_new_session=True)
        timed_out=False
        try:process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;process.kill();process.wait()
        stdout_file.seek(0);stderr_file.seek(0)
        stdout=stdout_file.read(100000).decode(errors='replace');stderr=stderr_file.read(20000).decode(errors='replace')
        stdout_file.close();stderr_file.close();table=[];chart=None
        for line in stdout.splitlines():
            try:
                parsed=json.loads(line)
                if isinstance(parsed,dict):table=parsed.get('table',table);chart=parsed.get('chart',chart)
            except ValueError:pass
        files=[]
        for path in Path(work).iterdir():
            if path.name in ('job.json','.stdout','.stderr'):continue
            try:descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            except OSError:continue
            try:
                metadata=os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1 or metadata.st_size>2*1024**2:continue
                files.append({'name':path.name,'content':os.read(descriptor,100000).decode(errors='replace')})
            finally:os.close(descriptor)
        return {'executed':True,'success':process.returncode==0 and not timed_out,'returncode':process.returncode,'timeout':timed_out,'stdout':stdout,'stderr':stderr,'table':table,'chart':chart,'files':files,'elapsed_ms':(time.perf_counter()-started)*1000,'isolation':'Landlock filesystem allowlist + seccomp socket/process denial; 384 MiB memory, 10 s wall limit; separate read-only database copy'}
