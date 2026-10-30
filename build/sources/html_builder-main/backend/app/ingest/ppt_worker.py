"""Export every visible slide of a PPTX to PNG with PowerPoint COM. Runs as its own process.

Kept deliberately free of app imports so it can be started as a plain script: `render.py` spawns it with
a timeout because COM blocks forever on a modal dialog (repair prompt, activation nag, a crashed prior
instance) and an in-process call could never be cancelled.

Usage: python ppt_worker.py <pptx> <out_dir> [width]
Prints `RESULT {"count": N}` on stdout; a non-zero exit code means the export failed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MSO_TRUE = -1
RESULT_PREFIX = "RESULT "


def export(pptx: Path, out_dir: Path, width: int = 1600) -> int:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    pres = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        pres = app.Presentations.Open(str(pptx.resolve()), True, False, False)  # ReadOnly, Untitled, WithWindow
        sw, sh = float(pres.PageSetup.SlideWidth), float(pres.PageSetup.SlideHeight)
        height = round(width * sh / sw)
        n = 0
        for i in range(1, pres.Slides.Count + 1):
            slide = pres.Slides(i)
            try:
                if int(slide.SlideShowTransition.Hidden) == MSO_TRUE:
                    continue
            except Exception:  # noqa: BLE001
                pass
            n += 1
            slide.Export(str((out_dir / f"{n:03d}.png").resolve()), "PNG", width, height)
        return n
    finally:
        try:
            if pres is not None:
                pres.Close()
            # PowerPoint is single-instance: only quit if we are not closing the user's other decks
            if app is not None and app.Presentations.Count == 0:
                app.Quit()
        except Exception:  # noqa: BLE001
            pass
        pythoncom.CoUninitialize()


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: ppt_worker.py <pptx> <out_dir> [width]", file=sys.stderr)
        return 2
    out_dir = Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        n = export(Path(argv[1]), out_dir, int(argv[3]) if len(argv) > 3 else 1600)
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(RESULT_PREFIX + json.dumps({"count": n}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
