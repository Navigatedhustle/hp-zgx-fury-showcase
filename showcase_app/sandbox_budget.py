"""Owner-side admission and monitoring for sandbox workspace storage."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

MAX_BYTES=64*1024**2
MAX_ENTRIES=256


def check_workspace(path,max_bytes=MAX_BYTES,max_entries=MAX_ENTRIES):
    total=0;count=0
    def inspect(directory):
        nonlocal total,count
        for entry in os.scandir(directory):
            try:metadata=entry.stat(follow_symlinks=False)
            except FileNotFoundError:continue
            count+=1
            if stat.S_ISREG(metadata.st_mode):total+=metadata.st_size
            if count>max_entries or total>max_bytes:
                raise RuntimeError('Sandbox workspace storage limit reached')
            if stat.S_ISDIR(metadata.st_mode):
                try:child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                except (FileNotFoundError,NotADirectoryError):continue
                try:inspect(child)
                finally:os.close(child)
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:inspect(descriptor)
    finally:os.close(descriptor)
    if shutil.disk_usage(path).free<2*1024**3:
        raise RuntimeError('Sandbox workspace needs at least 2 GiB free temporary space')


def wait_limited(process,path,timeout,**limits):
    deadline=time.monotonic()+timeout
    try:
        while True:
            check_workspace(path,**limits)
            if process.poll() is not None:return process.returncode
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired(process.args,timeout)
            try:
                result=process.wait(timeout=min(.01,remaining))
                check_workspace(path,**limits)
                return result
            except subprocess.TimeoutExpired:pass
    except BaseException:
        # This unreaped direct child belongs to this invocation; never signal a PID/group from a snapshot.
        if process.poll() is None:process.kill()
        process.wait()
        raise
