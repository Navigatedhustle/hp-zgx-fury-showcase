"""Stage image policy never publishes a rejected candidate."""
import pytest
from showcase_app.gb10_image_policy import stage_prompt, TEXT_SCHEMA


def test_both_stage_image_shapes_use_wordless_non_printed_art_direction():
    for batch in (1, 4):
        prompt = stage_prompt(batch)
        assert 'unmarked surfaces' in prompt
        assert 'no text, letters, numbers' in prompt
        assert 'No screens, keyboards, cards, documents' in prompt
        assert 'Northwind' not in prompt


def test_no_unbounded_image_batch_or_text_transcription():
    with pytest.raises(ValueError):
        stage_prompt(8)
    assert TEXT_SCHEMA['additionalProperties'] is False
    assert TEXT_SCHEMA['properties'] == {'text': {'type': 'boolean'}}


def test_gallery_has_four_distinct_wordless_compositions_with_bounded_index():
    prompts = [stage_prompt(4, index) for index in range(4)]
    assert len(set(prompts)) == 4
    assert all('no text, letters, numbers' in prompt for prompt in prompts)
    for batch, index in [(1, 1), (4, 4), (4, -1)]:
        with pytest.raises(ValueError):
            stage_prompt(batch, index)


def test_worker_quarantines_rejected_images_and_fails_closed(monkeypatch, tmp_path):
    import asyncio
    import importlib
    from types import SimpleNamespace
    import threading
    import showcase_app.gb10_memory as memory
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    api = importlib.import_module('showcase_app.gb10_creative_api')
    monkeypatch.setattr(api, 'OUTPUT', tmp_path)
    monkeypatch.setattr(memory, 'release_unused_buffers', lambda: {})
    monkeypatch.setattr(api, 'execution_start', lambda *args: None)
    monkeypatch.setattr(api, 'execution_end', lambda *args: None)
    records = []
    monkeypatch.setattr(api, 'record', lambda *args, **kwargs: records.append((args, kwargs)))
    class Renderer:
        def run(self, kind, prompt, path, stop, options, job):
            assert 'Absolutely no text' in prompt
            path.write_bytes(b'not-for-publication')
            return dict(render_seconds=.01, gpu_peak_allocated_bytes=1, gpu_peak_reserved_bytes=1)
    monkeypatch.setattr(api, 'lane', Renderer())
    async def rejects(*args):
        return {'text': True, 'model': 'Qwen3.6-35B-A3B', 'seconds': .01, 'call_id': 'unit'}
    monkeypatch.setattr(api, 'check_artwork', rejects)
    async def check():
        queue = asyncio.Queue(maxsize=3)
        monkeypatch.setattr(api, 'queue', queue)
        job = {'id': 'a' * 32, 'status': 'queued', '_stop': threading.Event()}
        spec = SimpleNamespace(batch=1, seed=42, width=1344, height=768, run_id='unit', purpose='warmup')
        queue.put_nowait((job, spec))
        worker = asyncio.create_task(api.work())
        try:
            await asyncio.wait_for(queue.join(), 5)
            assert job['status'] == 'failed' and job['text_rejections'] == 2
            assert 'files' not in job
            assert not list(tmp_path.glob('*.png'))
            assert not list((tmp_path / 'pending').glob('*'))
            assert records[-1][0][4] == 'failed'
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(check())
