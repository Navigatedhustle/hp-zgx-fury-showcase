"""Free Mode decks: escaped local previews and native editable PowerPoint shapes."""
from html import escape
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Slide(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=65)
    subtitle: str = Field(default='', max_length=110)
    points: list[str] = Field(min_length=2, max_length=3)
    notes: str = Field(default='', max_length=700)


class Deck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=90)
    slides: list[Slide] = Field(min_length=3, max_length=8)


def export_deck(data, folder: Path):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from showcase_app.gb10_deck_design import block, lines

    deck = Deck.model_validate(data)
    if any(len(point) > 180 for slide in deck.slides for point in slide.points):
        raise ValueError('Keep each slide point under 180 characters')
    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = Inches(16), Inches(9)
    previews = []
    for index, content in enumerate(deck.slides):
        svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">',
               '<rect width="1920" height="1080" fill="#0A0D14"/><g font-family="Arial,Helvetica,sans-serif">']
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string('0A0D14')

        def text(x, y, width, height, value, size, color='D1DDF1', bold=False):
            while len(lines(value, size, width, bold)) * size * 1.18 > height and size > 24:
                size -= 2
            rendered, _ = block(x, y, value, size, width, color='#' + color, bold=bold, limit=y+height)
            svg.append(rendered)
            box = slide.shapes.add_textbox(Inches(x/120), Inches(y/120), Inches(width/120), Inches(height/120))
            box.text_frame.word_wrap = True
            box.text_frame.margin_left = box.text_frame.margin_top = 0
            box.text_frame.margin_right = box.text_frame.margin_bottom = 0
            paragraph = box.text_frame.paragraphs[0]
            paragraph.text = value
            paragraph.font.name = 'Arial'
            paragraph.font.size = Pt(size * .6)
            paragraph.font.bold = bold
            paragraph.font.color.rgb = RGBColor.from_string(color)

        text(100, 55, 1720, 60, 'HP ZGX NANO / FREE MODE', 25, '8DB1FF', True)
        title_width = 1090 if index == 0 else 1720
        text(100, 180, title_width, 220, content.title, 76, bold=True)
        text(100, 415, title_width, 120, content.subtitle, 32, 'A8B7CF')
        if index == 0:
            svg.append('<path d="m1370 220 360 180-360 200-220-190Z" fill="#004BDF"/><path d="m1370 600 360-200v250l-360 200-220-190V410Z" fill="#152B50"/>')
            from pptx.enum.shapes import MSO_SHAPE
            shape = slide.shapes.add_shape(MSO_SHAPE.CUBE, Inches(11), Inches(2), Inches(3.5), Inches(4.5))
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string('004BDF')
            shape.line.fill.background()
        for number, point in enumerate(content.points):
            if index % 3 == 2:
                width = 510
                x, y = 100 + number * 590, 610
                text(x, y-45, width, 50, f'{number+1:02d}', 28, '8DB1FF', True)
                text(x, y+25, width, 320, point, 36)
            else:
                width = 1050 if index == 0 else 1600
                text(100, 590 + number*120, width, 115, point, 34)
        text(100, 1000, 1480, 60, 'LOCAL AI DRAFT / REVIEW BEFORE USE', 22, 'A8B7CF')
        text(1680, 1000, 200, 60, f'{index+1:02d} / {len(deck.slides):02d}', 22, '8DB1FF')
        slide.notes_slide.notes_text_frame.text = content.notes
        name = f'slide-{index+1}.svg'
        (folder / name).write_text(''.join(svg) + '</g></svg>')
        previews.append(name)
    presentation.save(folder / 'presentation.pptx')
    (folder / 'presentation.json').write_text(deck.model_dump_json(indent=2))
    return {'deck': deck.model_dump(), 'previews': previews, 'files': ['presentation.pptx', 'presentation.json', *previews]}
