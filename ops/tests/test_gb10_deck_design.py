"""Generated copy is preserved, escaped, and bounded in the actual slide artwork."""
import xml.etree.ElementTree as ET

import pytest

from showcase_app.gb10_deck_design import block, lines, slide_svg


def test_five_slide_compositions_preserve_copy_without_active_content():
    slide = {'title': 'Pilot <script>alert(1)</script>', 'subtitle': 'Owners & dates are fictional',
             'points': ['Mara owns the pilot on 2026-11-15.', 'Theo reviews results on 2026-11-22.']}
    designs = []
    for index in range(1, 6):
        source = slide_svg(slide, index)
        root = ET.fromstring(source)
        assert root.attrib['viewBox'] == '0 0 1920 1080'
        text = ' '.join(root.itertext())
        for value in [slide['title'], slide['subtitle'], *slide['points']]:
            assert value in text
        assert not any(node.tag.rsplit('}', 1)[-1] in ('script', 'foreignObject', 'image') for node in root.iter())
        assert not any('href' in key for node in root.iter() for key in node.attrib)
        designs.append(source)
    assert len(set(designs)) == 5


def test_unreadable_copy_fails_instead_of_clipping_or_shrinking():
    with pytest.raises(ValueError, match='readable layout'):
        block(100, 900, 'Long copy ' * 80, 36, 500)
    for index in (0, 6):
        with pytest.raises(ValueError, match='five slides'):
            slide_svg({}, index)
    assert ''.join(lines('ABCDEFGHIJK', 36, 20)) == 'ABCDEFGHIJK'
