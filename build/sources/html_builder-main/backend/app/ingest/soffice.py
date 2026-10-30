"""Locate and run LibreOffice headless.

Every invocation gets its own `-env:UserInstallation` profile: concurrent `soffice` processes that share
the default profile block each other and silently produce nothing.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def find_soffice() -> str | None:
    exe = shutil.which("soffice") or shutil.which("soffice.exe")
    if exe:
        return exe
    return next((c for c in _CANDIDATES if Path(c).exists()), None)


def convert(src: Path, out_dir: Path, fmt: str, timeout: int = 300) -> Path | None:
    """Run `soffice --convert-to <fmt>` into `out_dir`; returns the produced file, or None.

    Raises RuntimeError when LibreOffice is not installed and CalledProcessError/TimeoutExpired on a
    failed conversion, so callers can tell "not available" from "did not work".
    """
    exe = find_soffice()
    if not exe:
        raise RuntimeError("LibreOffice not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = fmt.split(":")[0]
    with tempfile.TemporaryDirectory(prefix="soffice-profile-", ignore_cleanup_errors=True) as profile:
        cmd = [exe, "--headless", "--norestore", "--invisible", "--nolockcheck",
               f"-env:UserInstallation={Path(profile).resolve().as_uri()}",
               "--convert-to", fmt, "--outdir", str(out_dir), str(src)]
        subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)
    want = out_dir / f"{src.stem}.{ext}"
    if want.exists():
        return want
    return next(iter(sorted(out_dir.glob(f"*.{ext}"))), None)
