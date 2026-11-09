#!/usr/bin/env python3
"""Draw original fictional vision qualification inputs using local fonts only."""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'samples/stage/vision'
FONTS = ROOT / 'build/sources/atlas-gpt-main/static/fonts'

# Original single-stroke capitals. These are fixture artwork, not a downloaded font.
MARKER = {
    'A': [[(0,1),(.5,0),(1,1)],[(.2,.6),(.8,.6)]],
    'B': [[(0,1),(0,0),(.65,0),(1,.2),(.7,.48),(0,.48)],[(.7,.48),(1,.7),(.7,1),(0,1)]],
    'C': [[(1,.12),(.75,0),(.2,0),(0,.2),(0,.8),(.2,1),(.8,1),(1,.86)]],
    'D': [[(0,1),(0,0),(.6,0),(1,.25),(1,.75),(.6,1),(0,1)]],
    'E': [[(1,0),(0,0),(0,1),(1,1)],[(0,.48),(.8,.48)]],
    'F': [[(1,0),(0,0),(0,1)],[(0,.48),(.8,.48)]],
    'G': [[(1,.13),(.75,0),(.2,0),(0,.2),(0,.8),(.2,1),(.8,1),(1,.8),(1,.5),(.55,.5)]],
    'H': [[(0,0),(0,1)],[(1,0),(1,1)],[(0,.5),(1,.5)]],
    'I': [[(0,0),(1,0)],[(.5,0),(.5,1)],[(0,1),(1,1)]],
    'J': [[(0,0),(1,0),(1,.8),(.75,1),(.25,1),(0,.8)]],
    'K': [[(0,0),(0,1)],[(1,0),(0,.55),(1,1)]],
    'L': [[(0,0),(0,1),(1,1)]],
    'M': [[(0,1),(0,0),(.5,.5),(1,0),(1,1)]],
    'N': [[(0,1),(0,0),(1,1),(1,0)]],
    'O': [[(.2,0),(.8,0),(1,.2),(1,.8),(.8,1),(.2,1),(0,.8),(0,.2),(.2,0)]],
    'P': [[(0,1),(0,0),(.75,0),(1,.2),(1,.35),(.75,.5),(0,.5)]],
    'Q': [[(.2,0),(.8,0),(1,.2),(1,.8),(.8,1),(.2,1),(0,.8),(0,.2),(.2,0)],[(.6,.7),(1.1,1.1)]],
    'R': [[(0,1),(0,0),(.75,0),(1,.2),(1,.35),(.75,.5),(0,.5)],[(.5,.5),(1,1)]],
    'S': [[(1,.1),(.75,0),(.2,0),(0,.2),(.2,.45),(.8,.55),(1,.8),(.8,1),(.2,1),(0,.9)]],
    'T': [[(0,0),(1,0)],[(.5,0),(.5,1)]],
    'U': [[(0,0),(0,.8),(.2,1),(.8,1),(1,.8),(1,0)]],
    'V': [[(0,0),(.5,1),(1,0)]],
    'W': [[(0,0),(.2,1),(.5,.55),(.8,1),(1,0)]],
    'X': [[(0,0),(1,1)],[(1,0),(0,1)]],
    'Y': [[(0,0),(.5,.5),(1,0)],[(.5,.5),(.5,1)]],
    'Z': [[(0,0),(1,0),(0,1),(1,1)]],
    '0': [[(.2,0),(.8,0),(1,.2),(1,.8),(.8,1),(.2,1),(0,.8),(0,.2),(.2,0)]],
    '1': [[(.2,.2),(.6,0),(.6,1)],[(.1,1),(1,1)]],
    '2': [[(0,.15),(.2,0),(.8,0),(1,.2),(1,.35),(0,1),(1,1)]],
    '3': [[(0,0),(.8,0),(1,.2),(.8,.5),(.4,.5)],[(.8,.5),(1,.75),(.8,1),(0,1)]],
    '4': [[(.75,1),(.75,0),(0,.65),(1,.65)]],
    '5': [[(1,0),(0,0),(0,.5),(.8,.5),(1,.7),(1,.85),(.8,1),(0,1)]],
    '6': [[(.9,0),(.25,.05),(0,.35),(0,.8),(.2,1),(.8,1),(1,.8),(1,.6),(.8,.5),(0,.5)]],
    '7': [[(0,0),(1,0),(.3,1)]],
    '8': [[(.2,0),(.8,0),(1,.2),(.8,.5),(.2,.5),(0,.25),(.2,0)],[(.2,.5),(0,.75),(.2,1),(.8,1),(1,.75),(.8,.5)]],
    '9': [[(1,.5),(.2,.5),(0,.3),(0,.2),(.2,0),(.8,0),(1,.2),(1,.75),(.75,1),(.2,1)]],
    '-': [[(.1,.5),(.9,.5)]],
}


def marker(draw, position, text, seed):
    rng = random.Random(seed)
    x, y = position
    for char in text.upper():
        if char == ' ':
            x += 13
            continue
        dy = rng.uniform(-2, 2)
        for stroke in MARKER[char]:
            points = [(x + a * 19 + b * 1.4 + rng.uniform(-.5,.5),
                       y + b * 37 + dy + rng.uniform(-.5,.5)) for a, b in stroke]
            draw.line(points, fill='#154a9b', width=3, joint='curve')
        x += 25


def font(size, bold=False):
    return ImageFont.truetype(str(FONTS / ('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')), size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    actions = [
        {'action': 'Map the offline pilot', 'owner': 'Alex Rowan', 'date': '2027-04-12'},
        {'action': 'Review access controls', 'owner': 'Casey Moss', 'date': '2027-04-15'},
        {'action': 'Approve the success measures', 'owner': 'Jordan Vale', 'date': '2027-04-19'},
    ]
    image = Image.new('RGB', (1600, 1000), '#d3d6d4')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35, 35, 1565, 965), radius=18, fill='#fffef5', outline='#68736f', width=12)
    draw.text((100, 85), 'Northwind planning session', font=font(56, True), fill='#173c65')
    draw.line([(95, 162), (765, 168), (1480, 161)], fill='#173c65', width=5)
    draw.text((110, 210), 'ACTION', font=font(34, True), fill='#315d4a')
    draw.text((860, 210), 'OWNER', font=font(34, True), fill='#315d4a')
    draw.text((1220, 210), 'DUE DATE', font=font(34, True), fill='#315d4a')
    for i, action in enumerate(actions):
        y = 320 + i * 170
        draw.ellipse((83, y + 15, 99, y + 31), outline='#154a9b', width=4)
        marker(draw, (115, y + (i % 2) * 5), action['action'], 30 + i)
        marker(draw, (860, y - 3), action['owner'], 60 + i)
        marker(draw, (1220, y + 2), action['date'], 90 + i)
        draw.line([(112, y + 98), (690, y + 103), (1490, y + 97)], fill='#d3ddd2', width=3)
    draw.text((110, 875), 'FICTIONAL SAMPLE  |  Original drawing, no customer data', font=font(28), fill='#526159')
    image.save(OUT / 'whiteboard.png')
    image.close()

    image = Image.new('RGB', (1600, 1000), '#ffffff')
    draw = ImageDraw.Draw(image)
    draw.text((90, 55), 'Northwind local pilot: capacity plan', font=font(54, True), fill='#102b50')
    rows = [['Q1', 12, 24], ['Q2', 18, 36], ['Q3', 24, 48], ['Q4', 30, 60]]
    draw.rectangle((1100, 170, 1130, 200), fill='#004bdf')
    draw.text((1150, 165), 'Local jobs', font=font(32), fill='#152c4d')
    draw.rectangle((1100, 230, 1130, 260), fill='#4a8064')
    draw.text((1150, 225), 'Hours saved', font=font(32), fill='#152c4d')
    for tick in range(0, 71, 10):
        y = 800 - tick * 8
        draw.line((140, y, 1050, y), fill='#d8deea', width=2)
        draw.text((75, y - 18), str(tick), font=font(28), fill='#304566')
    for i, (quarter, jobs, hours) in enumerate(rows):
        x = 210 + i * 215
        for offset, value, color in [(0, jobs, '#004bdf'), (77, hours, '#4a8064')]:
            draw.rectangle((x + offset, 800 - value * 8, x + offset + 65, 800), fill=color)
            draw.text((x + offset + 10, 752 - value * 8), str(value), font=font(30, True), fill='#132a49')
        draw.text((x + 35, 825), quarter, font=font(34, True), fill='#132a49')
    draw.text((100, 925), 'Fictional values. Columns: Quarter | Local jobs | Hours saved', font=font(30), fill='#4b586d')
    image.save(OUT / 'chart.png')
    image.close()
    actions = [{key: value.upper() if key != 'date' else value for key, value in action.items()} for action in actions]
    (OUT / 'expected.json').write_text(json.dumps({'whiteboard.png': actions,
        'chart.png': {'columns': ['Quarter', 'Local jobs', 'Hours saved'], 'rows': rows}}, indent=2) + '\n')


if __name__ == '__main__':
    main()
