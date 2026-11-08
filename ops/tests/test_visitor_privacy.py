import time
import pytest
from showcase_app.visitor_store import VisitorStore, clear_on_start, IDLE_SECONDS


def test_done_removes_photo_video_and_session(tmp_path):
    store=VisitorStore(tmp_path/'visitors');store.start();s=store.consent()
    (s['path']/'photo.jpg').write_bytes(b'fictional photo fixture')
    (s['path']/'trailer.mp4').write_bytes(b'fictional video fixture')
    store.delete(s['id'])
    assert not list(store.root.iterdir())
    assert store.get(s['id']) is None
    assert s['deleted']


def test_service_restart_removes_previous_session_media(tmp_path):
    store=VisitorStore(tmp_path/'visitors');s=store.consent()
    (s['path']/'photo.jpg').write_bytes(b'fictional')
    clear_on_start(store.root)
    assert not list(store.root.iterdir())
    assert store.get(s['id']) is None


def test_idle_expiry_deletes_media_without_a_browser(tmp_path):
    store=VisitorStore(tmp_path/'visitors');s=store.consent()
    (s['path']/'photo.jpg').write_bytes(b'fictional')
    s['touched']=time.time()-IDLE_SECONDS-1
    store.expire()
    assert not list(store.root.iterdir())


def test_start_refuses_unknown_files_instead_of_deleting_them(tmp_path):
    root=tmp_path/'visitors';root.mkdir();unknown=root/'unowned.txt';unknown.write_text('keep')
    with pytest.raises(RuntimeError):clear_on_start(root)
    assert unknown.read_text()=='keep'
