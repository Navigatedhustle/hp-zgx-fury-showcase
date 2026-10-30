"""Kernel-enforced sandbox entrypoint: filesystem allowlist and no network/processes."""
import ctypes,errno,json,os,platform,resource,sqlite3,sys,traceback
from pathlib import Path

def isolate(work,db):
    libc=ctypes.CDLL(None,use_errno=True)
    def checked(value,what):
        if value<0:raise OSError(ctypes.get_errno(),what)
        return value
    checked(libc.prctl(38,1,0,0,0),'no_new_privs')
    # Landlock ABI >= 3: reads only from runtime/code; writes only within the workdir.
    abi=libc.syscall(444,0,0,1)
    if abi<3:raise RuntimeError('Landlock ABI >= 3 required; execution disabled')
    rights=(1<<15)-1 # includes TRUNCATE; excludes later device-ioctl ABI additions
    class Ruleset(ctypes.Structure):_fields_=[('handled_access_fs',ctypes.c_uint64)]
    class Rule(ctypes.Structure):_pack_=1;_fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int)]
    ruleset=Ruleset(rights);fd=checked(libc.syscall(444,ctypes.byref(ruleset),ctypes.sizeof(ruleset),0),'landlock ruleset')
    read=(1<<2)|(1<<3) # READ_FILE and READ_DIR; execution denied
    for path,access in [(work,rights&~1), (str(Path(db).parent),read),('/usr',read),('/lib',read),('/lib64',read),(sys.prefix,read),(str(Path(__file__).parent),read),('/dev/null',1<<2)]:
        if not Path(path).exists():continue
        parent=os.open(path,os.O_PATH|os.O_CLOEXEC)
        rule=Rule(access,parent);checked(libc.syscall(445,fd,1,ctypes.byref(rule),0),'landlock add '+path);os.close(parent)
    checked(libc.syscall(446,fd,0),'landlock restrict');os.close(fd)
    # Classic seccomp BPF. Deny all socket creation, process creation/exec and escape syscalls.
    machine=platform.machine()
    if machine=='aarch64': arch=0xc00000b7;denied=[198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,220,221,281,435,117,40,41,97,104,105,106,268,272,273,129,130,131,270,271,424,425,426,427,438]
    elif machine=='x86_64':arch=0xc000003e;denied=[41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,322,435,101,165,166,272,308,310,311,62,200,234,424,425,426,427,438]
    else:raise RuntimeError('Unsupported sandbox architecture')
    class Filter(ctypes.Structure):_fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
    class Program(ctypes.Structure):_fields_=[('len',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]
    instructions=[Filter(0x20,0,0,4),Filter(0x15,1,0,arch),Filter(0x06,0,0,0x80000000),Filter(0x20,0,0,0)]
    for number in denied:instructions.extend([Filter(0x15,0,1,number),Filter(0x06,0,0,0x00050000|errno.EPERM)])
    instructions.append(Filter(0x06,0,0,0x7fff0000));array=(Filter*len(instructions))(*instructions);program=Program(len(instructions),array)
    checked(libc.prctl(22,2,ctypes.byref(program),0,0),'seccomp filter')

if __name__=='__main__':
    job=json.loads(Path(sys.argv[1]).read_text());work=os.getcwd();db=job['database']
    os.environ.clear();os.environ.update(ATLAS_DB=db,PYTHONDONTWRITEBYTECODE='1',HOME=work)
    resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(8,9));resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2));resource.setrlimit(resource.RLIMIT_NOFILE,(64,64));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    try:
        isolate(work,db)
        if job['language']=='sql':
            con=sqlite3.connect('file:'+db+'?mode=ro',uri=True);con.execute('PRAGMA query_only=ON');con.row_factory=sqlite3.Row
            cursor=con.execute(job['code']);records=[dict(row) for row in cursor.fetchmany(500)]
            print(json.dumps({'table':records,'columns':[d[0] for d in cursor.description] if cursor.description else []}))
        else:
            exec(compile(job['code'],'generated.py','exec'),{'__name__':'__main__','__file__':str(Path(work)/'generated.py')})
    except BaseException:
        traceback.print_exc();sys.exit(1)
