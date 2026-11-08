#!/usr/bin/env python3
"""Draw original fictional vision qualification inputs using local fonts only."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'samples/stage/vision'
FONTS = ROOT / 'build/sources/atlas-gpt-main/static/fonts'


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
        draw.text((115, y + (i % 2) * 5), action['action'], font=font(40), fill='#154a9b')
        draw.text((860, y - 3), action['owner'], font=font(38), fill='#154a9b')
        draw.text((1220, y + 2), action['date'], font=font(38), fill='#154a9b')
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
    (OUT / 'expected.json').write_text(json.dumps({'whiteboard.png': actions,
        'chart.png': {'columns': ['Quarter', 'Local jobs', 'Hours saved'], 'rows': rows}}, indent=2) + '\n')


if __name__ == '__main__':
    main()
