"""Persist a dated handoff after every working step."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
stamp=datetime.now(ZoneInfo('America/Denver')).isoformat(timespec='seconds')
p=Path('STATUS.md');text=p.read_text() if p.exists() else '# Status\n'
text+='\n- '+stamp+': '+sys.argv[1]+'\n';p.write_text(text)
print(stamp)
