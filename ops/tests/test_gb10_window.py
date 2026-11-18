"""Native fullscreen controls stay scoped to the trusted shell and owned window."""
import asyncio
from types import SimpleNamespace

import pytest

from showcase_app.gb10_window import WindowControls, trusted_shell


def source(url='http://127.0.0.1:18808/stage', *, child=False):
    frame = SimpleNamespace(url=url)
    page = SimpleNamespace(main_frame=object() if child else frame)
    return {'page': page, 'frame': frame}


@pytest.mark.parametrize('path', ['/stage', '/stage/keys', '/stage/models', '/free', '/free/images', '/free/jobs'])
def test_local_shell_can_control_its_window(path):
    value = source('http://127.0.0.1:18808' + path)
    assert trusted_shell(value) is value['page']


@pytest.mark.parametrize('url,child', [
    ('https://example.com/stage', False), ('http://127.0.0.1:18808/stage', True),
    ('http://127.0.0.1:18808/free/files/a/app.html', False),
    ('http://127.0.0.1:18808/stage/artifact/a/S3/calculator.html', False),
    ('http://127.0.0.1:18809/stage', False), ('file:///stage', False)])
def test_generated_content_and_other_origins_cannot_control_windows(url, child):
    with pytest.raises(ValueError, match='restricted'):
        trusted_shell(source(url, child=child))


def test_native_exit_accepts_restored_maximized_window_and_releases_connection():
    async def run():
        calls = []
        class Session:
            state = 'fullscreen'
            async def send(self, name, values=None):
                calls.append((name, values))
                if name == 'Browser.setWindowBounds':
                    assert values == {'windowId': 17, 'bounds': {'windowState': 'normal'}}
                    self.state = 'maximized'
                return {'windowId': 17, 'bounds': {'windowState': self.state}}
            async def detach(self):
                calls.append(('detach', None))
        session = Session()
        async def new_session(page):
            return session
        value = source()
        value['page'].context = SimpleNamespace(new_cdp_session=new_session)
        control = WindowControls()
        assert await control.state(value) == {'fullscreen': True}
        assert await control.set_fullscreen(value, False) == {'fullscreen': False}
        assert [name for name, _ in calls].count('detach') == 2
        for invalid in ('false', 0, None):
            with pytest.raises(ValueError, match='boolean'):
                await control.set_fullscreen(value, invalid)
    asyncio.run(run())
