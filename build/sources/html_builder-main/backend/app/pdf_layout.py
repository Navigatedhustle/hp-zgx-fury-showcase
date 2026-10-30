"""Read a PDF page the way it is laid out, not the way its text happens to be stored.

pypdf returns text in stream order, line by line across the full width. On a two-column whitepaper that
interleaves the columns into sentences nobody wrote, and a table arrives as words with spaces between them.
Both then defeat everything downstream: headings are not found, quotes are not verbatim, and a table cannot
be kept whole because nothing says it is one.

pypdf does report where each run of text sits. This module rebuilds the page from those positions:

- runs on one baseline become a row of cells (a wide gap separates cells);
- consecutive rows whose cells start at the same x positions are a block. Long cells make it **columns** —
  read down the first, then the second. Short cells make it a **table** — written `| a | b |`, the form the
  chunker keeps whole and repeats the header of;
- everything else is ordinary text, with a blank line where the page left a paragraph gap.

It is a reading of geometry, so it is checked: if the rebuilt text has lost or gained more than a little
against pypdf's own, the page falls back to pypdf's. Widths are estimated (pypdf gives a run's start, not its
end), which is why every threshold here is generous.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

GLYPH = 0.5           # average glyph width as a share of the font size — the estimate behind every run's end
CELL_GAP = 2.2        # runs further apart than this many font sizes are different cells
ALIGN = 8.0           # points: cell starts this close are the same column
COLUMN_CHARS = 28     # a block whose cells are typically at least this long is text in columns, not a table
PARA_GAP = 1.6        # a line gap this many times the usual one is a paragraph break
DRIFT = 0.12          # share of letters and digits the rebuilt page may differ by before pypdf's text is used


@dataclass
class Cell:
    x: float
    text: str
    size: float

    @property
    def end(self) -> float:
        return self.x + len(self.text) * self.size * GLYPH


@dataclass
class Row:
    y: float
    cells: list[Cell] = field(default_factory=list)

    @property
    def size(self) -> float:
        return max(c.size for c in self.cells)


def _rows(page) -> list[Row]:  # noqa: ANN001
    """The page's text runs, grouped into rows top to bottom and merged into cells left to right."""
    runs: list[tuple[float, float, str, float]] = []

    def visit(text, cm, tm, _font, size) -> None:  # noqa: ANN001
        t = text.replace("\n", " ").strip()
        if not t:
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        scale = (abs(tm[0] * cm[0]) or 1.0)
        runs.append((x, y, t, max(1.0, float(size or 10) * scale)))

    page.extract_text(visitor_text=visit)
    rows: list[Row] = []
    for x, y, t, size in sorted(runs, key=lambda r: (-r[1], r[0])):
        row = rows[-1] if rows and abs(rows[-1].y - y) <= 0.45 * size else None
        if row is None:
            row = Row(y=y)
            rows.append(row)
        row.cells.append(Cell(x, t, size))
    for row in rows:
        merged: list[Cell] = []
        for c in sorted(row.cells, key=lambda c: c.x):
            if merged and c.x - merged[-1].end < CELL_GAP * c.size:
                merged[-1].text += " " + c.text
            else:
                merged.append(Cell(c.x, c.text, c.size))
        row.cells = merged
    return rows


def _column_of(starts: list[float], x: float) -> int | None:
    return next((i for i, s in enumerate(starts) if abs(s - x) <= ALIGN), None)


def _fits(row: Row, starts: list[float]) -> bool:
    """Does every cell of this row start at one of the block's columns and stay out of the next one?"""
    for c in row.cells:
        i = _column_of(starts, c.x)
        if i is None or (i + 1 < len(starts) and c.end > starts[i + 1] + 2 * c.size):
            return False
    return True


def _blocks(rows: list[Row]) -> list[tuple[str, list[Row], list[float]]]:
    """("text" | "grid", rows, column starts): maximal runs of rows that share column positions."""
    out: list[tuple[str, list[Row], list[float]]] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        if len(row.cells) < 2:
            if out and out[-1][0] == "text":
                out[-1][1].append(row)
            else:
                out.append(("text", [row], []))
            i += 1
            continue
        starts = [c.x for c in row.cells]
        j = i + 1
        while j < len(rows) and _fits(rows[j], starts) and rows[j - 1].y - rows[j].y <= 3.5 * rows[j].size:
            j += 1
        out.append(("grid", rows[i:j], starts))
        i = j
    return out


def _lines(rows: list[Row]) -> str:
    """Rows as running text: one line each, a blank line where the page left more room than between lines."""
    if not rows:
        return ""
    gaps = [a.y - b.y for a, b in zip(rows, rows[1:]) if a.y > b.y]
    usual = median(gaps) if gaps else 0.0
    out = [" ".join(c.text for c in rows[0].cells)]
    for a, b in zip(rows, rows[1:]):
        gap = a.y - b.y
        out.append(("\n\n" if usual and gap > max(PARA_GAP * usual, 1.4 * b.size + 2) else "\n") + " ".join(c.text for c in b.cells))
    return "".join(out)


def _grid(rows: list[Row], starts: list[float]) -> str:
    cells = [c for r in rows for c in r.cells]
    many = sum(len(r.cells) >= 2 for r in rows)
    if len(rows) >= 3 and median(len(c.text) for c in cells) >= COLUMN_CHARS:
        # Columns of prose: down the first, then down the next.
        cols = [[Row(y=r.y, cells=[c]) for r in rows for c in r.cells if _column_of(starts, c.x) == k] for k in range(len(starts))]
        return "\n\n".join(t for t in (_lines(col) for col in cols) if t)
    if many < 2:
        return _lines(rows)  # one row with a wide gap in it is a line, not a table
    table: list[list[str]] = []
    for r in rows:
        if len(r.cells) == 1 and table:
            # A lone cell under a table row is that cell's text wrapping onto another line.
            k = _column_of(starts, r.cells[0].x) or 0
            table[-1][k] = f"{table[-1][k]} {r.cells[0].text}".strip()
            continue
        line = [""] * len(starts)
        for c in r.cells:
            line[_column_of(starts, c.x) or 0] = c.text.replace("|", "/")
        table.append(line)
    return "\n".join("| " + " | ".join(line) + " |" for line in table)


def _alnum(s: str) -> int:
    return len(re.findall(r"[^\W_]", s))


def page_text(page) -> str:  # noqa: ANN001
    """The page's text in reading order, tables marked — or pypdf's own text when the layout cannot be trusted."""
    plain = (page.extract_text() or "").strip()
    try:
        rows = _rows(page)
        parts = [_lines(rs) if kind == "text" else _grid(rs, starts) for kind, rs, starts in _blocks(rows)]
        text = "\n\n".join(p for p in parts if p).strip()
    except Exception:  # noqa: BLE001 - an unusual PDF must cost the layout, never the document
        return plain
    want = _alnum(plain)
    if not text or (want and abs(_alnum(text) - want) > DRIFT * want):
        return plain
    return text
