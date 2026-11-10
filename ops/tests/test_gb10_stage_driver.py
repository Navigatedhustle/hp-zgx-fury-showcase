"""The rehearsal driver observes one asynchronous keypress without resending it."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def driver_module(monkeypatch):
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    monkeypatch.setenv('FURY_STAGE_RUNTIME', '1')
    path = Path(__file__).resolve().parents[1] / 'acceptance/gb10-stage.py'
    spec = importlib.util.spec_from_file_location('stage_driver_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('observed,valid', [(['S0', 'S0', 'S1'], True), (['S2'], False)])
def test_one_next_waits_for_expected_beat_and_rejects_skips(monkeypatch, observed, valid):
    module = driver_module(monkeypatch)
    async def check():
        pressed = []
        async def press(key):
            pressed.append(key)
        states = iter(observed)
        async def state():
            return {'beat': next(states), 'run': {'status': 'complete', 'started': 1,
                'ended': 43, 'backup': False}}
        proof = object.__new__(module.Proof)
        proof.page = SimpleNamespace(keyboard=SimpleNamespace(press=press))
        proof.state = state
        if valid:
            result = await proof.segment(1, dwell=False)
            assert result['beat'] == 'S1'
        else:
            with pytest.raises(RuntimeError, match='Unexpected beat'):
                await proof.segment(1, dwell=False)
        assert pressed == ['PageDown']
    asyncio.run(check())
