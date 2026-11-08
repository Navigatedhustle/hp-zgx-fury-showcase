"""Ephemeral personal-data directories. No database, media logging or repo storage."""
import os
import re
import secrets
import shutil
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
VISITORS = Path.home()/'.cache/fury-showcase/visitors'
IDLE_SECONDS = 15*60


def prepare_root(root=VISITORS):
    root = Path(root).absolute()
    if root.resolve().is_relative_to(PROJECT) or root.is_symlink():
        raise RuntimeError('Visitor temporary storage must be outside the repository')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.stat().st_uid != os.getuid():raise RuntimeError('Visitor storage is not owned by this account')
    root.chmod(0o700)
    return root


def clear_on_start(root=VISITORS):
    root = prepare_root(root)
    for child in root.iterdir():
        if not re.fullmatch('session-[0-9a-f]{32}',child.name):
            raise RuntimeError('Unknown file in visitor storage; operator inspection required')
        if child.is_symlink():child.unlink()
        elif child.is_dir():shutil.rmtree(child)
        else:child.unlink()


class VisitorStore:
    def __init__(self,root=VISITORS):
        self.root = prepare_root(root)
        self.sessions = {}

    def start(self):
        clear_on_start(self.root)
        self.sessions.clear()

    def consent(self):
        self.expire()
        if len(self.sessions) >= 64:
            raise ValueError('Visitor session capacity is full; retry after a session ends')
        sid = secrets.token_hex(16)
        folder = self.root/('session-'+sid)
        folder.mkdir(mode=0o700)
        session = {'id':sid,'path':folder,'created':time.time(),'touched':time.time(),'deleted':False}
        self.sessions[sid] = session
        return session

    def get(self,sid,touch=False):
        session = self.sessions.get(sid)
        if not session:return None
        if not session['path'].is_dir() or time.time()-session['touched']>=IDLE_SECONDS:
            self.delete(sid)
            return None
        if touch:session['touched'] = time.time()
        return session

    def delete(self,sid):
        session = self.sessions.pop(sid,None)
        if not session:return None
        session['deleted'] = True
        task = session.get('task')
        if task and not task.done():task.cancel()
        if session['path'].is_dir():shutil.rmtree(session['path'])
        return session

    def expire(self):
        now = time.time()
        return [self.delete(sid) for sid,s in list(self.sessions.items()) if now-s['touched']>=IDLE_SECONDS]
