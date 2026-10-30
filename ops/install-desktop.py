#!/usr/bin/env python3
"""Create a local desktop launcher only on explicit request."""
import os,shlex
from pathlib import Path
root=Path(__file__).resolve().parents[1];target=Path.home()/'.local/share/applications/fury-showcase.desktop';target.parent.mkdir(parents=True,exist_ok=True)
# Desktop Exec uses double-quoted arguments, not shell quoting.
script=str(root/'launch.sh').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
target.write_text('[Desktop Entry]\nType=Application\nName=Fury AI Showcase\nComment=Launch local demonstration\nExec="'+script+'"\nTerminal=true\nCategories=Development;\n');target.chmod(0o755)
print('Installed '+str(target)+'. Find Fury AI Showcase in your applications menu. If copied to the desktop, your file manager may require Allow Launching / Trust. The launcher opens a terminal for setup progress and errors.')
