#!/usr/bin/env python3
"""Build the public Nano PDFs from reviewed Markdown; no network or model calls."""
import argparse
import html
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (LongTable, PageBreak, Paragraph,
                               Preformatted, SimpleDocTemplate, Spacer, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
BLUE = colors.HexColor('#075aab')
NAVY = colors.HexColor('#102840')
PALE = colors.HexColor('#edf5fa')


def inline(text):
    pattern = r'(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|https?://[^\s]+)'
    result = []
    for part in re.split(pattern, text):
        if part.startswith('**') and part.endswith('**'):
            result.append('<b>' + html.escape(part[2:-2]) + '</b>')
        elif part.startswith('`') and part.endswith('`'):
            result.append('<font name="NanoMono" size="8">' + html.escape(part[1:-1]) + '</font>')
        elif part.startswith('[') and '](' in part:
            label, url = part[1:].split('](', 1)
            result.append('<link color="#075aab" href="' + html.escape(url[:-1], quote=True) + '">' + html.escape(label) + '</link>')
        elif part.startswith(('https://', 'http://')):
            result.append('<link color="#075aab" href="' + html.escape(part, quote=True) + '">' + html.escape(part) + '</link>')
        else:
            result.append(html.escape(part))
    return ''.join(result)


def styles():
    for name, path in [('NanoSans', '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
                       ('NanoSans-Bold', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
                       ('NanoMono', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')]:
        if not Path(path).is_file():
            raise RuntimeError('Install fonts-liberation and fonts-dejavu-core to render guides: ' + path)
        pdfmetrics.registerFont(TTFont(name, path))
    pdfmetrics.registerFontFamily('NanoSans', normal='NanoSans', bold='NanoSans-Bold', italic='NanoSans', boldItalic='NanoSans-Bold')
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name='NanoBody', fontName='NanoSans', fontSize=9.4, leading=13,
                            textColor=NAVY, spaceAfter=8, splitLongWords=True))
    base.add(ParagraphStyle(name='NanoH1', parent=base['NanoBody'], fontName='NanoSans-Bold', fontSize=25,
                            leading=29, spaceBefore=5, spaceAfter=8, textColor=NAVY, keepWithNext=True))
    base.add(ParagraphStyle(name='NanoH2', parent=base['NanoBody'], fontName='NanoSans-Bold', fontSize=16,
                            leading=20, spaceBefore=7, spaceAfter=10, textColor=BLUE, keepWithNext=True))
    base.add(ParagraphStyle(name='NanoH3', parent=base['NanoBody'], fontName='NanoSans-Bold', fontSize=12,
                            leading=16, spaceBefore=10, spaceAfter=6, textColor=BLUE, keepWithNext=True))
    base.add(ParagraphStyle(name='NanoCell', parent=base['NanoBody'], fontSize=8.7, leading=11.5, spaceAfter=0))
    base.add(ParagraphStyle(name='NanoCode', fontName='NanoMono', fontSize=7.5, leading=11,
                            backColor=PALE, borderPadding=10, spaceBefore=7, spaceAfter=14))
    return base


def parse_markdown(text, style, width):
    lines = text.splitlines()
    story = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.strip() == '<!-- pagebreak -->':
            story.append(PageBreak())
            i += 1
            continue
        if line.startswith('```'):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i])
                i += 1
            story.append(Preformatted('\n'.join(code), style['NanoCode']))
            i += 1
            continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [x.strip() for x in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[:\s-]+', cell) for cell in cells):
                    rows.append(cells)
                i += 1
            columns = len(rows[0])
            weights = [0.25, 0.75] if columns == 2 else [1 / columns] * columns
            formatted = [[Paragraph(inline(cell), style['NanoCell']) for cell in row] for row in rows]
            table = LongTable(formatted, colWidths=[width * v for v in weights], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), PALE),
                ('LINEBELOW', (0, 0), (-1, 0), 1, BLUE),
                ('LINEBELOW', (0, 1), (-1, -1), 0.35, colors.HexColor('#cadbe5')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 7),
                ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.extend([table, Spacer(1, 10)])
            continue
        match = re.match(r'^(#{1,3}) (.+)', line)
        if match:
            story.append(Paragraph(inline(match[2]), style['NanoH' + str(len(match[1]))]))
            i += 1
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|', '```', '<!--')):
            paragraph.append(lines[i])
            i += 1
        story.append(Paragraph(inline(' '.join(paragraph)), style['NanoBody']))
    return story


def render(source, output, label):
    style = styles()
    document = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=42, rightMargin=42,
                                 topMargin=56, bottomMargin=44, title=label,
                                 author='HP ZGX Nano community demo', pageCompression=1)
    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.2)
        canvas.line(42, A4[1] - 34, A4[0] - 42, A4[1] - 34)
        canvas.setFont('NanoSans-Bold', 8)
        canvas.setFillColor(BLUE)
        canvas.drawString(42, A4[1] - 25, 'HP ZGX NANO  /  COMMUNITY DEMO')
        canvas.setFont('NanoSans', 8)
        canvas.setFillColor(NAVY)
        canvas.drawRightString(A4[0] - 42, A4[1] - 25, 'v3.2.0-nano.3  •  18 NOV 2026')
        canvas.setFont('NanoSans', 7.5)
        canvas.drawString(42, 26, label)
        canvas.drawRightString(A4[0] - 42, 26, str(doc.page))
        canvas.restoreState()
    document.build(parse_markdown(source.read_text(), style, document.width), onFirstPage=page, onLaterPages=page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/v3.2.0-nano.3')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for source, filename, label in [
        ('docs/NANO_QUICKSTART.md', 'HP-ZGX-Nano-Quickstart.pdf', 'Fresh Nano install & first run'),
        ('docs/NANO_GUIDE.md', 'HP-ZGX-Nano-Complete-Guide.pdf', 'Complete installation & presenter guide'),
    ]:
        output = args.output / filename
        render(ROOT / source, output, label)
        print(output)


if __name__ == '__main__':
    main()
