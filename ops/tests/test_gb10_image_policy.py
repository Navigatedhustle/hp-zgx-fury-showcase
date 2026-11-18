"""Stage image policy never publishes a rejected candidate."""
import pytest
from showcase_app.gb10_image_policy import stage_prompt, stage_brief, TEXT_SCHEMA, STAGE_REVIEW_SCHEMA


def test_both_stage_image_shapes_use_wordless_non_printed_art_direction():
    for batch in (1, 4):
        prompt = stage_prompt(batch)
        assert 'blank and unmarked' in prompt
        assert 'no text, letters, numbers' in prompt
        assert 'No screens, keyboards' in prompt
        assert 'fictional' in prompt.lower()
        assert stage_brief(batch)['use']
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


@pytest.mark.parametrize('writing', [True, False])
def test_worker_quarantines_rejected_images_and_fails_closed(monkeypatch, tmp_path, writing):
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
    async def rejects(*args, **kwargs):
        return {'text': writing, 'relevant': False, 'model': 'Qwen3.6-35B-A3B', 'seconds': .01, 'call_id': 'unit'}
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
            assert job['status'] == 'failed'
            assert job['text_rejections'] == (2 if writing else 0)
            assert job['relevance_rejections'] == (0 if writing else 2)
            assert 'files' not in job
            assert not list(tmp_path.glob('*.png'))
            assert not list((tmp_path / 'pending').glob('*'))
            assert records[-1][0][4] == 'failed'
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(check())


def test_story_briefs_have_distinct_real_deliverable_roles():
    briefs = [stage_brief(4, i) for i in range(4)]
    assert [b['id'] for b in briefs] == ['briefing-cover', 'local-workspace', 'team-workshop', 'pilot-planning']
    assert len({b['subject'] for b in briefs}) == 4
    assert STAGE_REVIEW_SCHEMA['required'] == ['text', 'relevant']
    assert STAGE_REVIEW_SCHEMA['additionalProperties'] is False


def test_relevance_review_cannot_accept_an_incomplete_model_result(monkeypatch, tmp_path):
    import asyncio
    import showcase_app.gb10_image_policy as policy
    calls = []
    async def incomplete(messages, **options):
        calls.append(options)
        return {'content': '{"text":false}', 'model': 'Qwen3.6-35B-A3B', 'call_id': 'test'}
    monkeypatch.setattr(policy, 'infer', incomplete)
    monkeypatch.setattr(policy, 'vision_payload', lambda path: 'data:image/png;base64,AA==')
    with pytest.raises(ValueError):
        asyncio.run(policy.check_artwork(tmp_path / 'unused.png', 'test', 'warmup', brief=stage_brief(1)))
    assert calls[0]['max_tokens'] == 32


def test_reviewed_cover_is_passed_to_the_export_and_preview_renderer(monkeypatch, tmp_path):
    import base64
    import hashlib
    import json
    from types import SimpleNamespace
    import showcase_app.gb10_agent as agent
    monkeypatch.setattr(agent, 'ROOT', tmp_path)
    folder = tmp_path / 'deck'
    folder.mkdir()
    deck = {'title': 'Fictional pilot', 'slides': [dict(title='Planning pilot', subtitle='Proposal for discussion',
        points=['Choose an owner.', 'Agree on measures.'], notes='Fictional example.') for _ in range(5)]}
    (folder / 'briefing.json').write_text(json.dumps(deck))
    def export(data, output, cover_uri=None):
        from showcase_app.gb10_deck_design import slide_svg
        vectors = [slide_svg(slide, index, cover_uri=cover_uri if index == 1 else None) for index, slide in enumerate(data['slides'], 1)]
        for index, vector in enumerate(vectors, 1):
            (output / f'slide-{index}.svg').write_text(vector)
        (output / 'briefing.html').write_text(''.join(vectors))
        return {'cover_applied': bool(cover_uri)}
    monkeypatch.setattr(agent, 'write_deck', export)
    image_folder = tmp_path / 'state/stage/creative'
    image_folder.mkdir(parents=True)
    name = 'a' * 32 + '.png'
    pixels = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    (image_folder / name).write_bytes(pixels)
    events = []
    subject = SimpleNamespace(folder=folder, artifacts={'image': {'files': [name],
        'text_checks': [{'text': True}, {'text': False, 'relevant': True}]}}, event=lambda *args, **kw: events.append(kw))
    agent.NanoAgent.apply_reviewed_cover(subject)
    uri = 'data:image/png;base64,' + base64.b64encode(pixels).decode()
    assert uri in (folder / 'slide-1.svg').read_text()
    assert uri in (folder / 'briefing.html').read_text()
    assert uri not in (folder / 'slide-2.svg').read_text()
    assert subject.artifacts['deck']['cover_sha256'] == hashlib.sha256(pixels).hexdigest()
    assert subject.artifacts['deck']['cover_applied'] is True
    assert events[-1]['artifact'] == 'deck'
    subject.artifacts['image']['text_checks'] = [{'text': False, 'relevant': False}]
    with pytest.raises(ValueError, match='passed local review'):
        agent.NanoAgent.apply_reviewed_cover(subject)


def test_rush_image_kit_preserves_reviewed_pixels_and_named_uses(monkeypatch, tmp_path):
    import asyncio
    import hashlib
    import json
    import zipfile
    from types import SimpleNamespace
    import showcase_app.gb10_rush as rush
    monkeypatch.setattr(rush, 'ROOT', tmp_path)
    creative = tmp_path / 'state/stage/creative'
    creative.mkdir(parents=True)
    files = ['a' * 32 + f'-{i}.png' for i in range(1, 5)]
    for index, name in enumerate(files):
        (creative / name).write_bytes(b'reviewed-png-' + str(index).encode())
    briefs = [{k: stage_brief(4, i)[k] for k in ('id', 'title', 'use')} for i in range(4)]
    async def accepted(*args, **kwargs):
        return {'files': files, 'briefs': briefs, 'model': 'FLUX.2-klein-4B'}
    monkeypatch.setattr(rush, 'image_job', accepted)
    folder = tmp_path / 'kit'
    folder.mkdir()
    subject = SimpleNamespace(run_id='unit', purpose='unit', folder=folder, event=lambda *args, **kw: None)
    result = asyncio.run(rush.NanoRush.images(subject))
    with zipfile.ZipFile(folder / result['kit_file']) as archive:
        assert len(archive.namelist()) == 6
        manifest = json.loads(archive.read('image-briefs.json'))
        assert 'fictional' in manifest['account']
        for original, row in zip(files, manifest['images']):
            assert archive.read(row['file']) == (creative / original).read_bytes()
            assert row['sha256'] == hashlib.sha256(archive.read(row['file'])).hexdigest()
            assert row['use']


@pytest.mark.parametrize('raises', [False, True])
def test_image_memory_options_restore_original_settings_even_after_failure(monkeypatch, tmp_path, raises):
    import sys
    import threading
    from types import SimpleNamespace
    import showcase_app.creative as creative
    import showcase_app.gb10_memory as memory
    noop = lambda *args: None
    cuda = SimpleNamespace(empty_cache=noop, mem_get_info=lambda: (30 * 2**30, 128 * 2**30),
        memory_reserved=lambda: 12 * 2**30, set_per_process_memory_fraction=noop,
        reset_peak_memory_stats=noop, synchronize=noop, max_memory_allocated=lambda: 12 * 2**30,
        max_memory_reserved=lambda: 12 * 2**30)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=cuda,
        Generator=lambda *args: SimpleNamespace(manual_seed=lambda seed: seed)))
    monkeypatch.setattr(creative, 'unified_available', lambda: 30 * 2**30)
    monkeypatch.setattr(memory, 'release_unused_buffers', lambda: {})
    vae = SimpleNamespace(use_tiling=False, tile_sample_min_size=1024, tile_latent_min_size=128,
        config=SimpleNamespace(block_out_channels=[128, 256, 512, 512]))
    vae.enable_tiling = lambda: setattr(vae, 'use_tiling', True)
    calls = []
    class Tokenizer:
        def apply_chat_template(self, *args, **kwargs): return 'brief'
        def __call__(self, text): return {'input_ids': list(range(80))}
    class Pipeline:
        def __init__(self):
            self.vae = vae
            self.tokenizer = Tokenizer()
        def __call__(self, **options):
            calls.append((dict(options), vae.use_tiling, vae.tile_sample_min_size))
            if raises:
                raise RuntimeError('Decode failure')
            return SimpleNamespace(images=[SimpleNamespace(save=lambda path: path.write_bytes(b'png'), close=noop)])
        def maybe_free_model_hooks(self):
            pass
    lane = object.__new__(creative.CreativeLane)
    lane.gb10, lane.flux = True, Pipeline()
    for stage in (True, False):
        options = dict(width=1024, height=576, batch=1, seed=42)
        if stage:
            options['max_sequence_length'] = 256
        if raises:
            with pytest.raises(RuntimeError, match='Decode failure'):
                lane.run('image', 'test', tmp_path / 'test.png', threading.Event(), options, {})
        else:
            lane.run('image', 'test', tmp_path / 'test.png', threading.Event(), options, {})
        assert (vae.use_tiling, vae.tile_sample_min_size, vae.tile_latent_min_size) == (False, 1024, 128)
    assert calls[0][0]['max_sequence_length'] == 256 and calls[0][1:] == (True, 256)
    assert calls[1][0]['max_sequence_length'] == 96 and calls[1][1:] == (True, 256)


@pytest.mark.parametrize('failures,complete', [(1, True), (2, False)])
def test_render_memory_retry_is_bounded_and_keeps_candidates_private(monkeypatch, tmp_path, failures, complete):
    import asyncio, importlib, threading
    from types import SimpleNamespace
    import showcase_app.gb10_memory as memory
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    api = importlib.import_module('showcase_app.gb10_creative_api')
    monkeypatch.setattr(api, 'OUTPUT', tmp_path)
    monkeypatch.setattr(memory, 'release_unused_buffers', lambda: {})
    monkeypatch.setattr(api, 'execution_start', lambda *a: None)
    monkeypatch.setattr(api, 'execution_end', lambda *a: None)
    monkeypatch.setattr(api, 'record', lambda *a, **kw: None)
    oom = type('OutOfMemoryError', (RuntimeError,), {})
    class Renderer:
        calls = 0
        def run(self, kind, prompt, path, stop, options, job):
            self.calls += 1
            if self.calls <= failures: raise oom('private allocator diagnostics')
            path.write_bytes(b'reviewed candidate')
            return dict(render_seconds=.01, gpu_peak_allocated_bytes=1, gpu_peak_reserved_bytes=1)
    renderer = Renderer()
    monkeypatch.setattr(api, 'lane', renderer)
    async def review(*args, **kwargs): return {'text': False, 'relevant': True}
    monkeypatch.setattr(api, 'check_artwork', review)
    async def run():
        queue = asyncio.Queue(maxsize=3)
        monkeypatch.setattr(api, 'queue', queue)
        job = {'id': 'b'*32, 'status': 'queued', '_stop': threading.Event()}
        spec = SimpleNamespace(batch=1, seed=42, width=1344, height=768, run_id='unit', purpose='warmup')
        queue.put_nowait((job, spec));worker = asyncio.create_task(api.work())
        try:
            await asyncio.wait_for(queue.join(), 5)
            assert job['status'] == ('complete' if complete else 'failed')
            assert renderer.calls == 2 and job['memory_retries'] == 1
            assert bool(list(tmp_path.glob('*.png'))) == complete
            if not complete: assert job['failure']['code'] == 'image_memory' and 'files' not in job
            assert not list((tmp_path / 'pending').glob('*'))
        finally:
            worker.cancel();await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(run())
