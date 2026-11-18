'use strict';
(() => {
  let fullscreen = false, busy = false, refreshTimer;
  const native = () => typeof window.nanoWindowState === 'function' && typeof window.nanoSetFullscreen === 'function';
  const browserFullscreen = () => !!document.fullscreenElement ||
    (innerHeight >= screen.height - 2 && innerWidth >= screen.width - 2);
  function update() {
    for (const button of document.querySelectorAll('[data-window-fullscreen]')) {
      const text = busy ? 'Changing view…' : fullscreen ? 'Exit full screen ↙' : 'Full screen ↗';
      if (button.textContent !== text) button.textContent = text;
      button.disabled = busy;
      button.setAttribute('aria-pressed', String(fullscreen));
      button.title = fullscreen ? 'Return to a normal window' : 'Show full screen';
    }
  }
  async function refresh() {
    try {fullscreen = native() ? (await window.nanoWindowState()).fullscreen : browserFullscreen();}
    catch {fullscreen = browserFullscreen();}
    update();
  }
  function message(text) {
    const node = document.querySelector('#notice, #toast');
    if (node) {node.textContent = text;node.hidden = false;setTimeout(() => {node.hidden = true;}, 6500);}
  }
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-window-fullscreen]');
    if (!button || busy) return;
    busy = true;update();
    try {
      if (native()) {
        if (document.fullscreenElement) await document.exitFullscreen();
        fullscreen = (await window.nanoSetFullscreen(!fullscreen)).fullscreen;
      } else if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (browserFullscreen()) {
        message('Press F11 to leave your browser’s full screen.');
      } else {
        await document.documentElement.requestFullscreen();
      }
    } catch {message('Could not change full screen. You can also use F11 in a standard browser.');}
    finally {busy = false;await refresh();}
  });
  const scheduleRefresh = () => {clearTimeout(refreshTimer);refreshTimer = setTimeout(refresh, 150);};
  document.addEventListener('fullscreenchange', scheduleRefresh);
  addEventListener('resize', scheduleRefresh);
  addEventListener('focus', scheduleRefresh);
  new MutationObserver(update).observe(document.body, {childList: true, subtree: true});
  refresh();
})();
