"""Stage invariants exercised without starting or substituting a model."""
import asyncio
import importlib
import os
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def stage_module(monkeypatch):
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    monkeypatch.setenv('FURY_STAGE_RUNTIME', '1')
    sys.path.insert(0, str(ROOT / 'ops'))
    return importlib.import_module('showcase_app.stage_api')


def test_copy_edit_preserves_guard_against_regulatory_claims():
    from showcase_app.gb10_agent import check_claims, operational_wording
    edited, changes = operational_wording({'points': ['Track review compliance weekly']})
    assert changes and edited['points'] == ['Track review completion weekly']
    assert check_claims(edited)
    for claim in ['HIPAA compliant', 'GDPR compliance', 'SOC 2 certified', 'review compliance and ISO 27001 certification']:
        candidate, _ = operational_wording(claim)
        with pytest.raises(ValueError):
            check_claims(candidate)


def test_keepalive_and_warmup_never_enter_live_session_totals(monkeypatch, tmp_path):
    module = stage_module(monkeypatch)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    with sqlite3.connect(tmp_path / 'usage.sqlite') as db:
        db.execute('CREATE TABLE events(input_tokens, output_tokens, images, pages, images_analyzed, purpose, run_id, status)')
        db.executemany('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)', [
            (10, 20, 1, 2, 3, 'live', 'session_S1', 'complete'),
            (999, 999, 999, 999, 999, 'keepalive', 'session_ping', 'complete'),
            (999, 999, 999, 999, 999, 'warmup', 'session_warm', 'complete'),
            (999, 999, 999, 999, 999, 'live', 'other_S1', 'complete'),
            (999, 999, 999, 999, 999, 'live', 'session_failed', 'failed')])
    show = object.__new__(module.Show)
    show.session = 'session'
    show.attempts = [{'segment': 'S1', 'started': 10, 'ended': 12}]
    assert show.totals() == dict(input_tokens=10, output_tokens=20, images=1, pages=2, images_analyzed=3, tokens_per_second=10)


def test_back_and_multiple_pending_next_never_repeat_or_stack(monkeypatch):
    module = stage_module(monkeypatch)
    async def check():
        show = object.__new__(module.Show)
        show.lock = asyncio.Lock()
        show.view = 1
        show.runs = {'S0': {'backup': False}, 'S1': {'backup': False}}
        show.resetting = False
        show.pending = False
        show.task = asyncio.create_task(asyncio.sleep(30))
        try:
            for _ in range(5):
                await show.next()
            assert show.pending is True and show.view == 1
            show.view = 0
            await show.next()
            assert show.view == 1 and len(show.runs) == 2
        finally:
            show.task.cancel()
            await asyncio.gather(show.task, return_exceptions=True)
    asyncio.run(check())


def test_reset_failure_clears_reset_flag_and_blocks_readiness(monkeypatch):
    module = stage_module(monkeypatch)
    show = object.__new__(module.Show)
    show.resetting = False
    show.warm = True
    async def broken(segment):
        show.resetting = True
        raise RuntimeError('Owned lane recovery failed')
    show._reset = broken
    with pytest.raises(RuntimeError):
        asyncio.run(show.reset())
    assert not show.resetting and not show.warm
    assert 'status' in show.warm_error


def test_private_settings_require_boolean_flags(monkeypatch, tmp_path):
    from showcase_app import stage_common
    monkeypatch.setattr(stage_common, 'STATE', tmp_path)
    (tmp_path / 'stage.local.json').write_text('{"audio":"false"}')
    with pytest.raises(ValueError, match='audio'):
        stage_common.local_settings()


def test_rejected_second_reset_cannot_unlock_the_running_reset(monkeypatch):
    module = stage_module(monkeypatch)
    async def check():
        show = object.__new__(module.Show)
        show.resetting = False
        show.warm = True
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(segment):
            if show.resetting:
                raise module.HTTPException(409)
            show.resetting = True
            entered.set()
            await release.wait()
        show._reset = slow
        first = asyncio.create_task(show.reset())
        await entered.wait()
        try:
            with pytest.raises(module.HTTPException) as rejected:
                await show.reset()
            assert rejected.value.status_code == 409
            assert show.resetting and show.warm
        finally:
            release.set()
            await first
        assert not show.resetting
    asyncio.run(check())
