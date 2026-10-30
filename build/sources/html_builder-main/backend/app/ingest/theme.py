"""Read the source deck's Office theme (`ppt/theme/theme1.xml`): colour scheme + font scheme.

Exposed on the parsed deck so a later step can tell an HP-branded deck from a partner/customer one.
Nothing in generation reads it yet.
"""
from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

from lxml import etree
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
# dk1/lt1/dk2/lt2 are the text/background pairs; accent1-6 drive every chart and shape fill.
SCHEME_SLOTS = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink")


class DeckTheme(BaseModel):
    name: str = ""
    colors: dict[str, str] = Field(default_factory=dict)  # slot -> "#RRGGBB"
    major_font: str = ""  # headings
    minor_font: str = ""  # body

    @property
    def accents(self) -> list[str]:
        return [self.colors[k] for k in SCHEME_SLOTS if k.startswith("accent") and k in self.colors]


def _color(el) -> str:
    for child in el:
        tag = etree.QName(child).localname
        if tag == "srgbClr" and child.get("val"):
            return "#" + child.get("val").upper()
        if tag == "sysClr" and child.get("lastClr"):
            return "#" + child.get("lastClr").upper()
    return ""


def _typeface(root, which: str) -> str:
    for el in root.iter(f"{{{A_NS}}}{which}"):
        latin = el.find(f"{{{A_NS}}}latin")
        if latin is not None and latin.get("typeface"):
            return latin.get("typeface")
    return ""


def parse_theme(pptx: Path) -> DeckTheme:
    """Best effort: an unreadable or missing theme part yields an empty DeckTheme."""
    try:
        with zipfile.ZipFile(pptx) as z:
            names = sorted(n for n in z.namelist() if re.fullmatch(r"ppt/theme/theme\d+\.xml", n))
            if not names:
                return DeckTheme()
            root = etree.fromstring(z.read(names[0]))
        theme = DeckTheme(name=root.get("name") or "")
        scheme = next(iter(root.iter(f"{{{A_NS}}}clrScheme")), None)
        if scheme is not None:
            for child in scheme:
                slot = etree.QName(child).localname
                val = _color(child)
                if slot in SCHEME_SLOTS and val:
                    theme.colors[slot] = val
        theme.major_font = _typeface(root, "majorFont")
        theme.minor_font = _typeface(root, "minorFont")
        return theme
    except Exception as e:  # noqa: BLE001
        log.warning("theme extraction failed: %s", e)
        return DeckTheme()
