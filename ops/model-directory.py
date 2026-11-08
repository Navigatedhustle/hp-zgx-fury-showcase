#!/usr/bin/env python3
"""Explicit setup-only reuse of an owner-controlled, checksum-verified model directory."""
import os
from pathlib import Path
import sys


def configure(root, requested):
    root=Path(root).resolve()
    source=Path(requested)
    if not source.is_absolute():raise ValueError('FURY_MODELS_DIR must be an absolute existing path')
    source=source.resolve(strict=True)
    if not source.is_dir() or source.stat().st_uid!=os.getuid():
        raise ValueError('FURY_MODELS_DIR must be an existing directory owned by the service account')
    destination=root/'models'
    if source==destination.resolve() and destination.exists():return source
    if source.is_relative_to(root):raise ValueError('Use an external shared model directory')
    if destination.exists() or destination.is_symlink():
        raise ValueError('This checkout already has a different models directory; it will not be replaced')
    destination.symlink_to(source,target_is_directory=True)
    return source


if __name__=='__main__':
    try:configure(Path(__file__).resolve().parents[1],sys.argv[1])
    except (OSError,ValueError,IndexError) as error:raise SystemExit(str(error)) from None
