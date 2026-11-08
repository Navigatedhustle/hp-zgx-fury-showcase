"""Local service authority; secret never enters source, URLs or usage records."""
import os
import secrets
from pathlib import Path

PATH=Path.home()/'.config/fury-showcase/creative.key'


def private_key():
    PATH.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not PATH.exists():
        try:
            fd=os.open(PATH,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:stream.write(secrets.token_urlsafe(32))
        except FileExistsError:pass
    return PATH.read_text().strip()
