"""Original HP stage slide system. Model copy is escaped and typeset locally."""
from html import escape
from functools import lru_cache
from pathlib import Path
import re
from PIL import ImageFont

BG, PANEL, BLUE, LIFT, WHITE, META = '#0A0D14', '#121E31', '#004BDF', '#8DB1FF', '#D1DDF1', '#8C8C8C'
FONT_DIR = Path('/usr/share/fonts/truetype/liberation')


@lru_cache(maxsize=24)
def font(size, bold=False):
    return ImageFont.truetype(str(FONT_DIR / ('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')), size)


def lines(text, size, width, bold=False):
    result, current = [], ''
    face = font(size, bold)
    for word in re.sub(r'\s+', ' ', str(text)).strip().split(' '):
        if face.getlength(word) > width:
            if current:
                result.append(current)
                current = ''
            part = ''
            for letter in word:
                if face.getlength(part + letter) > width:
                    result.append(part)
                    part = letter
                else:
                    part += letter
            current = part
        elif current and face.getlength(current + ' ' + word) > width:
            result.append(current)
            current = word
        else:
            current = (current + ' ' + word).strip()
    if current:
        result.append(current)
    return result


def block(x, y, text, size, width, *, bold=False, color=WHITE, limit=980):
    wrapped = lines(text, size, width, bold)
    bottom = y + len(wrapped) * size * 1.18
    if bottom > limit:
        raise ValueError('Slide copy exceeds its readable layout; request concise wording')
    spans = ''.join(f'<tspan x="{x}" y="{y + size + i * size * 1.18:.1f}">{escape(line)}</tspan>' for i, line in enumerate(wrapped))
    return f'<text fill="{color}" font-size="{size}" font-weight="{700 if bold else 400}">{spans}</text>', bottom


def label(x, y, text, color=LIFT):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="24" font-weight="700" letter-spacing="3">{escape(text)}</text>'


def rule(x, y, width, color=LIFT):
    return f'<path d="M{x} {y}h{width}" stroke="{color}" stroke-width="3"/>'


def nano_outline():
    return f'''<g transform="translate(1250 330)" stroke="{LIFT}" stroke-width="4" stroke-linejoin="round">
    <path d="M0 125 275 0 540 105 270 245Z" fill="#172743"/>
    <path d="M0 125v230l270 145V245Z" fill="#101B2D"/>
    <path d="m270 245 270-140v230L270 500Z" fill="#0C1422"/>
    <path d="m48 205 170 90m-170-60 170 90m-170-60 170 90m-170-60 170 90" stroke="#446DAA"/>
    <path d="m310 285 180-92m-180 120 180-92m-180 120 180-92" stroke="{BLUE}" stroke-width="8"/>
    <path d="M-40 550h620" stroke="#30445F"/>
    </g>'''


def slide_svg(slide, index):
    """Five distinct compositions share the exact model-authored slide content."""
    if index not in range(1, 6):
        raise ValueError('A stage briefing has exactly five slides')
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080" role="img"><title>{escape(slide["title"])}</title>',
           '<g font-family="Arial,Helvetica,Liberation Sans,sans-serif">', f'<rect width="1920" height="1080" fill="{BG}"/>',
           label(100, 80, 'HP ZGX NANO'), label(100, 128, 'EXECUTIVE BRIEFING / FICTIONAL ACCOUNT', META),
           f'<path d="m1770 58-25 65m61-65-25 65" stroke="{BLUE}" stroke-width="10"/>']
    points = slide['points']
    if index == 1:
        item, end = block(100, 205, slide['title'], 88, 1070, bold=True, limit=515);out.append(item)
        out.append(rule(100, end + 30, 980))
        item, end = block(100, end + 65, slide['subtitle'], 34, 1040, color=META, limit=650);out.append(item)
        y = max(655, end + 45)
        for point in points:
            out.append(f'<rect x="100" y="{y+12}" width="8" height="28" fill="{BLUE}"/>')
            item, y = block(130, y, point, 30, 1000);out.append(item);y += 16
        out.append(nano_outline())
    elif index in (2, 3, 5):
        item, end = block(100, 190, slide['title'], 76, 1690, bold=True, limit=400);out.append(item)
        out.append(rule(100, end + 25, 1720))
        item, end = block(100, end + 48, slide['subtitle'], 32, 1640, color=META, limit=490);out.append(item)
        y = max(520, end + 40)
        if index == 2:
            for n, point in enumerate(points, 1):
                out.append(label(100, y + 50, f'{n:02d}'))
                item, bottom = block(250, y + 5, point, 38, 1510);out.append(item)
                height = max(130, bottom - y + 25)
                out.append(rule(250, y + height - 6, 1570, '#30445F'));y += height
        else:
            width = (1720 - 30 * (len(points) - 1)) / len(points)
            for n, point in enumerate(points):
                x = 100 + n * (width + 30)
                if index == 3:
                    out += [f'<rect x="{x}" y="{y}" width="{width}" height="{960-y}" rx="4" fill="{PANEL}"/>',
                            label(x+32, y+55, f'{n+1:02d} / PILOT'),rule(x+32,y+90,width-64,BLUE)]
                    item, _ = block(x+32,y+125,point,36,width-64,limit=945);out.append(item)
                else:
                    out += [f'<circle cx="{x+25}" cy="{y+30}" r="24" fill="{BLUE}"/>',
                            label(x+70,y+38,f'NEXT {n+1:02d}')]
                    if n < len(points)-1:out.append(rule(x+190,y+30,width-180,'#30445F'))
                    item, _ = block(x,y+105,point,36,width-40,limit=945);out.append(item)
    else:
        item, end = block(100, 205, slide['title'], 76, 585, bold=True, limit=660);out.append(item)
        out.append(rule(100,end+35,540))
        item, _ = block(100,end+75,slide['subtitle'],32,570,color=META,limit=945);out.append(item)
        y = 205
        for n, point in enumerate(points, 1):
            out.append(f'<rect x="770" y="{y}" width="1050" height="220" rx="4" fill="{PANEL}"/>')
            out.append(label(805,y+50,f'FOCUS {n:02d}'))
            item, _ = block(805,y+75,point,36,975,limit=y+210);out.append(item);y += 245
    out += [rule(100, 1000, 1720, '#30445F'),label(100,1045,'FICTIONAL ACCOUNT NOTES / 2026-11-08',META),
            label(1710,1045,f'{index:02d} / 05'),'</g></svg>']
    return ''.join(out)
