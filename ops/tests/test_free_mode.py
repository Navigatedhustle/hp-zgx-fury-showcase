"""Free Mode isolation, real artifact formats and bounded job lifecycle (no models)."""
import asyncio
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from showcase_app import free_mode_api as free
from showcase_app.free_mode_deck import Deck, export_deck
from showcase_app.gb10_security import StageRequestGuard


def fake_show():
    async def health():
        return {'gateway': {}, 'image': {}, 'tts': {}}
    async def warmup():
        return None
    return SimpleNamespace(task=None, warm_task=None, resetting=False, pending=False, view=-1,
                           health={name: {'ready': True} for name in ('lead','text','image','tts','gateway')},
                           telemetry={}, fetch_health=health, warmup=warmup, warm=True, full_warm_complete=True)


def test_mode_switch_rejects_presenter_work_and_pending_free_work(tmp_path):
    async def run():
        show = fake_show()
        manager = free.FreeMode(show, tmp_path)
        manager.active = False
        show.task = asyncio.create_task(asyncio.sleep(30))
        with pytest.raises(HTTPException) as error:
            await manager.set_mode(True)
        assert error.value.status_code == 409 and not manager.active
        show.task.cancel()
        await asyncio.gather(show.task, return_exceptions=True)
        show.view = 2
        with pytest.raises(HTTPException):
            await manager.set_mode(True)
        show.view = -1
        await manager.set_mode(True)
        manager.jobs['fake'] = {'status': 'queued'}
        with pytest.raises(HTTPException):
            await manager.set_mode(False)
        manager.jobs.clear()
        await manager.set_mode(False)
        assert not show.warm and not show.full_warm_complete
        await show.warm_task
    asyncio.run(run())


def test_mode_switch_waits_for_downstream_image_cancellation(tmp_path):
    async def run():
        show = fake_show()
        async def draining():
            return {'image': {'active': 1}, 'gateway': {}, 'tts': {}}
        show.fetch_health = draining
        manager = free.FreeMode(show, tmp_path)
        manager.active = True
        with pytest.raises(HTTPException) as error:
            await manager.set_mode(False)
        assert error.value.status_code == 409 and manager.active
    asyncio.run(run())


def test_submit_cannot_race_the_async_mode_health_probe(tmp_path):
    async def run():
        show = fake_show()
        entered, release = asyncio.Event(), asyncio.Event()
        async def probe():
            entered.set()
            await release.wait()
            return {}
        show.fetch_health = probe
        manager = free.FreeMode(show, tmp_path)
        manager.active = True
        switching = asyncio.create_task(manager.set_mode(False))
        await entered.wait()
        with pytest.raises(HTTPException) as error:
            manager.submit([free.JobRequest(demo='atlas', prompt='A concurrent request')])
        assert error.value.status_code == 409 and not manager.jobs
        release.set()
        await switching
        await show.warm_task
        assert not manager.active and not manager.switching
    asyncio.run(run())


def test_queue_has_three_workers_and_rejects_rush_atomically(monkeypatch, tmp_path):
    async def run():
        manager = free.FreeMode(fake_show(), tmp_path)
        monkeypatch.setattr(manager, 'available', lambda: None)
        entered, release = asyncio.Event(), asyncio.Event()
        counters = {'active': 0, 'peak': 0, 'entered': 0}
        async def tool(*args):
            counters['active'] += 1
            counters['entered'] += 1
            counters['peak'] = max(counters['peak'], counters['active'])
            if counters['entered'] == 3:
                entered.set()
            try:
                await release.wait()
                return {'files': []}
            finally:
                counters['active'] -= 1
        monkeypatch.setitem(free.TOOLS, 'atlas', tool)
        spec = free.JobRequest(demo='atlas', prompt='Test bounded admission')
        manager.submit([spec]*12)
        await asyncio.wait_for(entered.wait(), 2)
        assert counters['active'] == 3
        with pytest.raises(HTTPException) as error:
            manager.submit([spec]*6)
        assert error.value.status_code == 429 and len(manager.jobs) == 12
        release.set()
        await asyncio.gather(*list(manager.tasks.values()))
        assert counters['peak'] == 3
        assert all(job['status'] == 'complete' for job in manager.jobs.values())
        restored = free.FreeMode(fake_show(), tmp_path)
        assert len(restored.jobs) == 12 and all(job['status'] == 'complete' for job in restored.jobs.values())
    asyncio.run(run())


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv('FURY_FREE_MODE', '1')
    monkeypatch.setattr(free, 'ROOT', tmp_path)
    router, manager = free.create_router(fake_show())
    monkeypatch.setattr(manager, 'totals', lambda: {})
    app = FastAPI()
    app.add_middleware(StageRequestGuard)
    app.include_router(router)
    return app, manager


def test_foreign_origin_cannot_submit_or_delete_and_missing_image_is_rejected(api):
    app, manager = api
    with TestClient(app, base_url='http://127.0.0.1:18808') as client:
        assert client.post('/free/api/jobs', json={'demo':'atlas','prompt':'test'},headers={'origin':'https://foreign.invalid'}).status_code == 403
        assert client.delete('/free/api/jobs/'+'a'*32,headers={'origin':'https://foreign.invalid'}).status_code == 403
        assert client.post('/free/api/jobs',json={'demo':'vision','prompt':'read this','sample':''}).status_code == 422
        assert client.post('/free/api/jobs',json={'demo':'images','prompt':'a subject','width':1344,'height':576}).status_code == 422
    assert not manager.jobs


def test_artifacts_stay_private_until_complete_and_cannot_escape_job_folder(api):
    app, manager = api
    cid = 'a'*32
    folder = manager.folder(cid)
    folder.mkdir()
    (folder/'result.txt').write_text('approved result')
    (folder/'job.json').write_text('private input')
    manager.jobs[cid] = {'id':cid,'demo':'atlas','status':'running','result':{'files':['result.txt']}}
    with TestClient(app, base_url='http://127.0.0.1:18808') as client:
        assert client.get(f'/free/files/{cid}/result.txt').status_code == 404
        manager.jobs[cid]['status']='complete'
        assert client.get(f'/free/files/{cid}/result.txt').text == 'approved result'
        assert client.get(f'/free/files/{cid}/job.json').status_code == 404
        assert client.get(f'/free/files/{cid}/..%2Fjob.json').status_code == 404
        response=client.get(f'/free/files/{cid}/result.txt?download=true')
        assert response.headers['content-disposition'].startswith('attachment')


def test_cancel_before_worker_starts_releases_job_and_restart_marks_interrupted(api, monkeypatch):
    app, manager = api
    monkeypatch.setattr(manager,'available',lambda:None)
    async def blocked(*args):
        await asyncio.sleep(60)
    monkeypatch.setitem(free.TOOLS,'atlas',blocked)
    with TestClient(app,base_url='http://127.0.0.1:18808') as client:
        response=client.post('/free/api/jobs',json={'demo':'atlas','prompt':'test cancellation'})
        cid=response.json()['id']
        assert response.status_code==202
        assert client.post(f'/free/api/jobs/{cid}/cancel').json()['status']=='cancelled'
        assert not manager.busy()
        manager.jobs[cid]['status']='running'
        manager.save(manager.jobs[cid])
    restored=free.FreeMode(fake_show(),manager.storage)
    assert restored.jobs[cid]['status']=='interrupted'


def fixture_deck():
    return {'title':'Fictional pilot','slides':[{'title':title,'subtitle':'A local demonstration',
        'points':['Review output quality','Measure time with the team'],'notes':'Presenter notes.'}
        for title in ['Context <script>alert(1)</script>', 'Pilot scope', 'Next steps']]}


def test_deck_export_is_editable_and_preview_escapes_model_html(tmp_path):
    from pptx import Presentation
    result=export_deck(fixture_deck(),tmp_path)
    preview=(tmp_path/result['previews'][0]).read_text()
    assert '<script>' not in preview and '&lt;script&gt;' in preview
    presentation=Presentation(tmp_path/'presentation.pptx')
    assert len(presentation.slides)==3
    texts=[shape.text for shape in presentation.slides[0].shapes if shape.has_text_frame]
    assert 'Context <script>alert(1)</script>' in texts
    assert 'Review output quality' in texts
    assert presentation.slides[0].notes_slide.notes_text_frame.text=='Presenter notes.'


def test_document_import_preserves_pdf_page_boundaries_and_rejects_scan():
    from reportlab.pdfgen import canvas
    stream=io.BytesIO()
    document=canvas.Canvas(stream)
    document.drawString(50,700,'Northwind page one 12 workstations')
    document.showPage()
    document.drawString(50,700,'Northwind page two 4 weeks')
    document.save()
    upload=free.Upload(filename='brief.pdf',content_base64=base64.b64encode(stream.getvalue()).decode())
    text=free.extract_document(upload)
    assert '\f' in text and '12' in text and '4 weeks' in text
    stream=io.BytesIO()
    document=canvas.Canvas(stream)
    document.showPage()
    document.save()
    with pytest.raises(ValueError,match='OCR'):
        free.extract_document(free.Upload(filename='scan.pdf',content_base64=base64.b64encode(stream.getvalue()).decode()))


def test_docx_bomb_and_binary_upload_are_rejected():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml','x'*3_000_001)
    with pytest.raises(ValueError,match='decompression'):
        free.extract_document(free.Upload(filename='bomb.docx',content_base64=base64.b64encode(stream.getvalue()).decode()))
    with pytest.raises(ValueError):
        free.extract_document(free.Upload(filename='program.exe',content_base64='YWJj'))


def test_custom_art_direction_uses_actual_subject_without_changing_stage(monkeypatch):
    import importlib
    monkeypatch.setenv('FURY_PROFILE','gb10')
    module=importlib.import_module('showcase_app.gb10_creative_api')
    request=module.ImageRequest(prompt='A sculptural red glass spiral',run_id='test',art_direction='free',style='Photographic',batch=2)
    assert request.prompt in module.free_prompt(request)
    assert 'Absolutely no text' in module.free_prompt(request)
    assert module.ImageRequest(prompt='original stage brief',run_id='test').art_direction=='stage'


def test_cold_image_start_releases_only_owned_language_models_before_upload(monkeypatch):
    import importlib.util
    import sys
    path=Path(__file__).resolve().parents[1]/'gb10-stage.py'
    spec=importlib.util.spec_from_file_location('free_launcher_fixture',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resident={'lead','text','tts','gateway'}
    events=[]
    control=SimpleNamespace(discover=lambda name: name if name in resident else None,ready=lambda name:name in resident)
    monkeypatch.setitem(sys.modules,'control',control)
    def operate(action,name):
        if action=='stop':
            resident.remove(name)
        else:
            if name=='image' and name not in resident:
                assert not {'lead','text'} & resident, 'Cold upload must not overlap language weights'
            resident.add(name)
        events.append((action,name))
    monkeypatch.setattr(module,'controller',operate)
    module.start_models()
    assert resident=={'lead','text','tts','gateway','image'}
    assert events[:2]==[('stop','lead'),('stop','text')]
    events.clear()
    module.start_models()
    assert all(action=='start' for action,name in events), 'A healthy resident stack must be reused'


@pytest.mark.parametrize('target,valid', [
    ('Piloto de 4 semanas con 12 equipos GX-100 el 2026-11-08.', True),
    ('Piloto de 4 semanas con 12 equipos GY-100 el 2026-11-08.', False),
    ('Piloto de 4 semanas con 12 equipos GX-100 el 08-11-2026.', False),
    ('Piloto con 12 equipos GX-100 el 2026-11-08.', False),
])
def test_translation_preserves_identifiers_but_translates_ordinary_hyphenated_phrases(monkeypatch,tmp_path,target,valid):
    from showcase_app import free_mode_tools as tools
    async def language(*args,**kwargs):
        return {'content':json.dumps({'pages':[target]}),'call_id':'fixture'}
    monkeypatch.setattr(tools,'language',language)
    monkeypatch.setattr(tools,'validated_counts',lambda *args,**kwargs:None)
    spec=SimpleNamespace(prompt='A 4-week pilot with 12 GX-100 workstations on 2026-11-08.',language='Spanish')
    if valid:
        result=asyncio.run(tools.translate({},spec,None,tmp_path))
        assert result['pages']==[target] and (tmp_path/'translation.docx').is_file()
    else:
        with pytest.raises(ValueError):
            asyncio.run(tools.translate({},spec,None,tmp_path))


def test_image_export_does_not_leave_hidden_duplicate_after_job_deletion(monkeypatch,tmp_path):
    import httpx
    from showcase_app import free_mode_tools as tools
    cid='b'*32
    creative=tmp_path/'state/stage/creative'
    creative.mkdir(parents=True)
    (creative/(cid+'.png')).write_bytes(b'checked-image')
    exports=tmp_path/'exports'
    exports.mkdir()
    monkeypatch.setattr(tools,'ROOT',tmp_path)
    real=httpx.AsyncClient
    def response(request):
        return httpx.Response(200,json={'id':cid,'status':'complete','files':[cid+'.png'],
            'text_checks':[{'text':False}],'render_seconds':1})
    monkeypatch.setattr(tools.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(response),**kwargs))
    spec=SimpleNamespace(prompt='A cobalt sculpture',batch=1,width=1024,height=576,seed=42,style='Studio')
    result=asyncio.run(tools.images({'run_id':'free_test'},spec,None,exports))
    assert result['files']==['image-1.png']
    assert (exports/'image-1.png').read_bytes()==b'checked-image'
    assert not (creative/(cid+'.png')).exists()
