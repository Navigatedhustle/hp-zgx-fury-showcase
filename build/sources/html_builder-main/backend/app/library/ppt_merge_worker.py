"""Merge slides from several PPTX files into one new PPTX with PowerPoint COM. Runs as its own process.

Modelled on `ingest/ppt_worker.py` and kept free of app imports for the same reason: `library/export.py`
spawns it with a deadline, because COM blocks for ever on a modal dialog and an in-process call could
never be cancelled.

Usage: python ppt_merge_worker.py <job.json>

The job is `{"out": path, "slide_width": pt, "slide_height": pt, "items": [item, ...]}`, one item per
output slide in order. An item is `{"file": pptx, "number": n}` (the n-th slide of that file, hidden ones
included, 1-based) and/or `{"png": path, "notes": str}` — a picture slide, used on its own, or as the
fallback when the original slide cannot be inserted.

Keeping source formatting: `Slides.InsertFromFile` always re-themes the inserted slide with the
destination's first design. Each inserted slide is therefore given back its source slide's design
(`slide.Design = source_slide.Design`, which copies that master and theme into the new file) and then
the source's custom layout by name. The copied design is remembered per (file, design), so twenty slides
from one deck share one master instead of twenty copies. The clipboard route ("Paste — keep source
formatting") is avoided: it needs a window, and it would overwrite whatever the user had copied.

A file holds one slide size. A slide from a deck of another size is fitted, not left to PowerPoint: it leaves a 4:3
slide's shapes where they were on a 16:9 page (hugging the left edge) and half-rescales a 16:9 slide on a 4:3 page
(some shapes shrink, text boxes reflow off the slide). `_fit_to_page` puts every shape back where it was on its
source slide, scaled uniformly to fit and centred, with font sizes scaled from the source's — so it reads exactly
as it did, letterboxed, and stays editable.

Prints `RESULT {"count": N, "fallback": [item index...], "skipped": [item index...], "resized": [item index...]}` on stdout;
a non-zero exit code means nothing usable was written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MSO_TRUE = -1
MSO_FALSE = 0
MSO_GROUP = 6
SAME_SIZE_PT = 0.5            # PowerPoint rounds page sizes to whole points
PP_LAYOUT_BLANK = 12
PP_SAVE_AS_OPENXML = 24       # ppSaveAsOpenXMLPresentation (.pptx)
RESULT_PREFIX = "RESULT "


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _same_layout(design, name: str):  # noqa: ANN001, ANN202
    layouts = design.SlideMaster.CustomLayouts
    for i in range(1, layouts.Count + 1):
        if layouts(i).Name == name:
            return layouts(i)
    return None


def _keep_source_formatting(slide, src_slide, designs: dict, key: tuple) -> None:  # noqa: ANN001
    """Re-apply the source slide's master, theme and layout to an inserted slide."""
    src_layout = src_slide.CustomLayout.Name
    have = designs.get(key)
    if have is not None:
        slide.Design = have             # same presentation: no copy
    else:
        slide.Design = src_slide.Design  # cross-presentation: PowerPoint copies the master in
        designs[key] = slide.Design
    layout = _same_layout(slide.Design, src_layout)
    if layout is not None:
        slide.CustomLayout = layout


def _text_sizes(dst, src, scale: float) -> None:  # noqa: ANN001
    """Font sizes from the source shape, scaled — never from the inserted copy, which PowerPoint may already have
    shrunk. Run by run, so a slide's mixed sizes keep their proportions; a shape whose runs differ is left alone."""
    try:
        if int(src.Type) == MSO_GROUP:
            for i in range(1, min(src.GroupItems.Count, dst.GroupItems.Count) + 1):
                _text_sizes(dst.GroupItems(i), src.GroupItems(i), scale)
            return
        if src.HasTable:
            t, u = dst.Table, src.Table
            for r in range(1, min(t.Rows.Count, u.Rows.Count) + 1):
                for c in range(1, min(t.Columns.Count, u.Columns.Count) + 1):
                    _text_sizes(t.Cell(r, c).Shape, u.Cell(r, c).Shape, scale)
            return
        if not src.HasTextFrame:
            return
        d, o = dst.TextFrame2, src.TextFrame2
        # PowerPoint may have switched a box to "resize shape to fit text" without wrapping when it re-laid the
        # slide out — which is how a text box runs off the page. The source's settings go back first.
        d.AutoSize, d.WordWrap = o.AutoSize, o.WordWrap
        a, b = _runs(dst.TextFrame.TextRange), _runs(src.TextFrame.TextRange)
        if len(a) != len(b):
            return
        for x, y in zip(a, b):
            size = float(y.Font.Size)
            if size > 0:
                x.Font.Size = round(size * scale * 2) / 2   # PowerPoint keeps half points
    except Exception as e:  # noqa: BLE001 — a size left as PowerPoint set it is better than a failed slide
        _log(f"could not scale text of {getattr(src, 'Name', '?')}: {e}")


def _runs(text_range) -> list:  # noqa: ANN001
    """The runs of a (legacy) TextRange, one by one until an empty range says there are no more. Through late
    binding TextRange2.Runs refuses ("Does not support a collection") and Runs() with no argument returns text."""
    out = []
    for i in range(1, 1000):
        r = text_range.Runs(i)
        if not r.Length:
            break
        out.append(r)
    return out


def _fit_to_page(slide, src_slide, src_w: float, src_h: float, dw: float, dh: float) -> bool:  # noqa: ANN001
    """Lay a slide from a deck of another size out as it was there: uniform scale, centred. False = left as is."""
    shapes, src = slide.Shapes, src_slide.Shapes
    if shapes.Count != src.Count:
        _log(f"fit skipped: {shapes.Count} shapes inserted, {src.Count} in the source")
        return False
    scale = min(dw / src_w, dh / src_h)
    ox, oy = (dw - src_w * scale) / 2, (dh - src_h * scale) / 2
    for i in range(1, src.Count + 1):
        d, o = shapes(i), src(i)
        try:
            lock = d.LockAspectRatio
            d.LockAspectRatio = MSO_FALSE
            d.Left, d.Top = float(o.Left) * scale + ox, float(o.Top) * scale + oy
            d.Width, d.Height = float(o.Width) * scale, float(o.Height) * scale
            d.LockAspectRatio = lock
        except Exception as e:  # noqa: BLE001
            _log(f"could not place {getattr(o, 'Name', '?')}: {e}")
        _text_sizes(d, o, scale)
    return True


def _picture_slide(pres, index: int, png: str, notes: str, sw: float, sh: float) -> None:  # noqa: ANN001
    slide = pres.Slides.Add(index, PP_LAYOUT_BLANK)
    try:
        slide.FollowMasterBackground = MSO_FALSE
        slide.DisplayMasterShapes = MSO_FALSE
        slide.Background.Fill.Solid()
        slide.Background.Fill.ForeColor.RGB = 0xFFFFFF
    except Exception:  # noqa: BLE001
        pass
    for i in range(slide.Shapes.Count, 0, -1):   # any placeholder the master's blank layout carries
        slide.Shapes(i).Delete()
    pic = slide.Shapes.AddPicture(str(Path(png).resolve()), MSO_FALSE, MSO_TRUE, 0, 0)
    w, h = float(pic.Width), float(pic.Height)
    scale = min(sw / w, sh / h)
    pic.Width, pic.Height = w * scale, h * scale
    pic.Left, pic.Top = (sw - pic.Width) / 2, (sh - pic.Height) / 2
    if notes:
        _set_notes(slide, notes)


def _set_notes(slide, notes: str) -> None:  # noqa: ANN001
    phs = slide.NotesPage.Shapes.Placeholders
    for i in range(1, phs.Count + 1):
        ph = phs(i)
        if int(ph.PlaceholderFormat.Type) == 2:   # ppPlaceholderBody — the notes text
            ph.TextFrame.TextRange.Text = notes
            return


def _remove_unused_designs(pres) -> None:  # noqa: ANN001
    """The blank presentation's own "Office Theme" is unused once every slide has its source design."""
    used = {int(pres.Slides(i).Design.Index) for i in range(1, pres.Slides.Count + 1)}
    for i in range(pres.Designs.Count, 0, -1):
        if i not in used and pres.Designs.Count > 1:
            try:
                pres.Designs(i).Delete()
            except Exception:  # noqa: BLE001
                pass
            used = {int(pres.Slides(j).Design.Index) for j in range(1, pres.Slides.Count + 1)}


def merge(job: dict) -> dict:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    pres = None
    sources: dict[str, object] = {}
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        pres = app.Presentations.Add(MSO_FALSE)   # WithWindow=False
        sw, sh = float(job["slide_width"]), float(job["slide_height"])
        pres.PageSetup.SlideWidth, pres.PageSetup.SlideHeight = sw, sh
        designs: dict[tuple, object] = {}
        fallback: list[int] = []
        skipped: list[int] = []
        resized: list[int] = []
        n = 0
        for k, item in enumerate(job["items"]):
            done = False
            if item.get("file"):
                try:
                    f = str(Path(item["file"]).resolve())
                    if f not in sources:
                        sources[f] = app.Presentations.Open(f, True, False, False)  # ReadOnly, Untitled, WithWindow
                    src = sources[f]
                    num = int(item["number"])
                    pres.Slides.InsertFromFile(f, n, num, num)  # inserts after slide n
                    src_slide = src.Slides(num)
                    try:
                        _keep_source_formatting(pres.Slides(n + 1), src_slide, designs, (f, int(src_slide.Design.Index)))
                    except Exception as e:  # noqa: BLE001 — the slide is in, only its theme is the default
                        _log(f"item {k}: could not keep source formatting: {e}")
                    src_w, src_h = float(src.PageSetup.SlideWidth), float(src.PageSetup.SlideHeight)
                    if abs(src_w - sw) > SAME_SIZE_PT or abs(src_h - sh) > SAME_SIZE_PT:
                        if _fit_to_page(pres.Slides(n + 1), src_slide, src_w, src_h, sw, sh):
                            resized.append(k)
                    done = True
                except Exception as e:  # noqa: BLE001
                    _log(f"item {k}: insert from {item.get('file')} #{item.get('number')} failed: {e}")
                    while pres.Slides.Count > n:   # never leave a half-inserted slide behind
                        pres.Slides(pres.Slides.Count).Delete()
            if not done and item.get("png") and Path(item["png"]).exists():
                try:
                    _picture_slide(pres, n + 1, item["png"], item.get("notes") or "", sw, sh)
                    done = True
                    if item.get("file"):
                        fallback.append(k)
                except Exception as e:  # noqa: BLE001
                    _log(f"item {k}: picture slide failed: {e}")
                    while pres.Slides.Count > n:
                        pres.Slides(pres.Slides.Count).Delete()
            if done:
                n += 1
            else:
                skipped.append(k)
        if n == 0:
            raise RuntimeError("no slide could be inserted")
        _remove_unused_designs(pres)
        pres.SaveAs(str(Path(job["out"]).resolve()), PP_SAVE_AS_OPENXML)
        return {"count": n, "fallback": fallback, "skipped": skipped, "resized": resized}
    finally:
        for p in [*sources.values(), pres]:
            try:
                if p is not None:
                    p.Close()
            except Exception:  # noqa: BLE001
                pass
        try:
            # PowerPoint is single-instance: only quit if we are not closing the user's other decks
            if app is not None and app.Presentations.Count == 0:
                app.Quit()
        except Exception:  # noqa: BLE001
            pass
        pythoncom.CoUninitialize()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: ppt_merge_worker.py <job.json>", file=sys.stderr)
        return 2
    try:
        result = merge(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(RESULT_PREFIX + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
