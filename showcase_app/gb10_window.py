"""Fullscreen control for the owned presenter browser, including native kiosk mode."""
import asyncio
from urllib.parse import urlsplit


SHELL_PATHS = {'/', '/stage', '/stage/keys', '/stage/models', '/free', '/free/jobs', '/free/models',
               '/free/atlas', '/free/slides', '/free/factory', '/free/images', '/free/vision',
               '/free/translate', '/free/voice'}


def trusted_shell(source):
    page, frame = source['page'], source['frame']
    url = urlsplit(frame.url)
    if (frame != page.main_frame or url.scheme != 'http' or url.netloc != '127.0.0.1:18808'
            or url.path not in SHELL_PATHS):
        raise ValueError('Window controls are restricted to the local experience shell')
    return page


class WindowControls:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def state(self, source):
        page = trusted_shell(source)
        session = await page.context.new_cdp_session(page)
        try:
            window = await session.send('Browser.getWindowForTarget')
            return {'fullscreen': window['bounds'].get('windowState') == 'fullscreen'}
        finally:
            await session.detach()

    async def set_fullscreen(self, source, enabled):
        page = trusted_shell(source)
        if type(enabled) is not bool:
            raise ValueError('Fullscreen state must be a boolean')
        async with self.lock:
            session = await page.context.new_cdp_session(page)
            try:
                window = await session.send('Browser.getWindowForTarget')
                await session.send('Browser.setWindowBounds', {'windowId': window['windowId'],
                    'bounds': {'windowState': 'fullscreen' if enabled else 'normal'}})
                # Window managers may restore the previous maximized state.
                for _ in range(40):
                    result = await session.send('Browser.getWindowBounds', {'windowId': window['windowId']})
                    fullscreen = result['bounds'].get('windowState') == 'fullscreen'
                    if fullscreen == enabled:
                        return {'fullscreen': fullscreen}
                    await asyncio.sleep(.05)
                raise RuntimeError('The browser window did not change fullscreen state')
            finally:
                await session.detach()
