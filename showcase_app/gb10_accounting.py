"""Attach validated artifact counts to the real gateway call, exactly once."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validated_counts(call_id, *, pages=0, images_analyzed=0):
    with sqlite3.connect(ROOT / 'state/stage/usage.sqlite', timeout=10) as db:
        cursor = db.execute('UPDATE events SET pages=?,images_analyzed=? WHERE id=? AND status=?',
                            (pages, images_analyzed, call_id, 'complete'))
        if cursor.rowcount != 1:
            raise RuntimeError('Validated artifact has no completed physical gateway call')
