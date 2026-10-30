"""Start HP Deck Builder.

    python start.py            first run installs everything, then opens http://127.0.0.1:8765 and its
                               usage dashboard (/dashboard) in a second tab
    python start.py --mock     offline mode (no GB300): template slides
    python start.py --setup    install / update dependencies only
    python start.py --build-ui rebuild the UI from frontend/src (developers; needs Node 20+)
    python start.py --port 9000

Uses only the standard library; everything else goes into .venv next to this file.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DIST = ROOT / "frontend" / "dist" / "index.html"
STAMP = VENV / ".deps-installed"


def run(cmd: list, cwd: Path | None = None) -> None:
    print("  >", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, shell=(os.name == "nt" and str(cmd[0]).startswith("npm")))


# The floor the code actually needs. The project is developed and tested on 3.14 — that is what
# the README names — but nothing here uses anything newer than 3.12, and refusing to
# start on a laptop's system Python for no reason is worse than the version skew was.
MIN_PY = (3, 12)


def setup(build_ui: bool = False) -> None:
    if sys.version_info < MIN_PY:
        sys.exit(f"Python {'.'.join(map(str, MIN_PY))}+ is required (this is {sys.version.split()[0]}). "
                 "The project is developed on 3.14.")
    # .env first: a later step failing (npm, most often) must not leave the app with no settings file
    env = ROOT / ".env"
    if not env.exists():
        shutil.copy(ROOT / ".env.example", env)
        print("Created .env from .env.example - set LLM_BASE_URL / LLM_MODEL / VLM_MODEL in it.")
    if not PY.exists():
        print("Creating Python environment (.venv)...")
        run([sys.executable, "-m", "venv", VENV])
    print("Installing Python packages...")
    run([PY, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([PY, "-m", "pip", "install", "-q", "-r", ROOT / "backend" / "requirements.txt"])
    print("Installing headless Chromium (for slide checks and PDF export)...")
    try:
        run([PY, "-m", "playwright", "install", "chromium"])
    except subprocess.CalledProcessError:
        # Corporate networks often block the download. Not fatal: the app falls back to the installed
        # Microsoft Edge or Chrome (qa/render_check.py), which every Windows laptop has.
        print("  ! Chromium download failed - slide checks will use the installed Edge or Chrome instead.")
    # The built UI is committed, so nobody needs Node to run the app. Building here would also rewrite
    # tracked files and turn every later `git pull` into a conflict. Build only when it is missing, or
    # when asked (a developer who changed frontend/src).
    if build_ui or not DIST.exists():
        if not shutil.which("npm"):
            sys.exit("Node.js 20+ is required to build the UI (frontend/dist is missing).")
        print("Building the UI...")
        # ci, not install: a clean install from the committed lockfile, so a stale node_modules cannot hide
        # (or cause) a dependency conflict. build:app skips lint — a lint rule must never cost a user the UI.
        run(["npm", "ci", "--no-fund", "--no-audit"], cwd=ROOT / "frontend")
        run(["npm", "run", "build:app"], cwd=ROOT / "frontend")
    else:
        print("Using the prebuilt UI in frontend/dist (pass --build-ui to rebuild it from source).")
    STAMP.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    print("Setup complete.\n")


def open_when_ready(url: str) -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=2)
            webbrowser.open(url)
            # the usage dashboard sits beside the app in its own tab: tokens, models and the cloud bill avoided
            webbrowser.open_new_tab(url + "/dashboard")
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Start HP Deck Builder")
    ap.add_argument("--mock", action="store_true", help="offline mode without the GB300")
    ap.add_argument("--setup", action="store_true", help="install / update dependencies and exit")
    ap.add_argument("--build-ui", action="store_true", help="rebuild the UI from frontend/src (needs Node 20+)")
    ap.add_argument("--port", default=os.environ.get("PORT", "8765"))
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    if a.setup or a.build_ui or not PY.exists() or not STAMP.exists() or not DIST.exists():
        setup(build_ui=a.build_ui)
    if a.setup:
        return

    env = os.environ.copy()
    if a.mock:
        env["LLM_MOCK"] = "true"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    url = f"http://127.0.0.1:{a.port}"
    print(f"HP Deck Builder: {url}   (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    try:
        subprocess.run([str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(a.port)],
                       cwd=ROOT / "backend", env=env)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
