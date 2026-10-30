"""Restart only the UI process recorded and identity-checked in this lane."""
import os,signal,time
from scripts.services import ROOT,alive,start_ui,wait
if alive('ui'):
    pid=int((ROOT/'runtime/ui.server.pid').read_text())
    os.killpg(pid,signal.SIGTERM)
    for _ in range(40):
        if not alive('ui'):break
        time.sleep(.1)
start_ui()
assert wait(8200,"/api/health",10),"UI did not become ready"
