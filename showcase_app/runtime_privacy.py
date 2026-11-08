"""Private runtime files, disabled crash dumps and bounded service log retention."""
import asyncio
import fcntl
import os
from pathlib import Path
import resource
import stat


def service_policy(root):
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    for folder in (Path(root)/'state',Path(root)/'logs'):
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        if folder.is_symlink() or folder.stat().st_uid!=os.getuid():
            raise RuntimeError('Unsafe runtime directory ownership')
        folder.chmod(0o700)


def rotate_logs(folder,maximum=8*1024**2,archives=3):
    """Copy the bounded tail then truncate the same inode used by open O_APPEND writers."""
    folder=Path(folder)
    for path in folder.glob('*.log'):
        try:
            descriptor=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
        except FileNotFoundError:continue
        try:
            meta=os.fstat(descriptor)
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.getuid() or meta.st_nlink!=1:
                raise RuntimeError('Unsafe service log file')
            os.fchmod(descriptor,0o600)
            if meta.st_size<=maximum:continue
            fcntl.flock(descriptor,fcntl.LOCK_EX)
            for number in range(archives,1,-1):
                prior=path.with_name(path.name+'.'+str(number-1))
                if prior.exists():prior.replace(path.with_name(path.name+'.'+str(number)))
            target=path.with_name(path.name+'.1')
            archive=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            try:
                os.fchmod(archive,0o600)
                os.lseek(descriptor,max(0,meta.st_size-maximum),os.SEEK_SET)
                remaining=maximum
                while remaining:
                    chunk=os.read(descriptor,min(65536,remaining))
                    if not chunk:break
                    os.write(archive,chunk);remaining-=len(chunk)
            finally:os.close(archive)
            os.ftruncate(descriptor,0)
        finally:os.close(descriptor)


async def log_maintenance(folder):
    while True:
        await asyncio.to_thread(rotate_logs,folder)
        await asyncio.sleep(5)
