"""Original, local editorial destination illustrations; no network or real-property claims."""
from html import escape


def scene(city):
    palettes = {
        'Lisbon': ('#e5d5b5', '#8bb7bd', '#c36948', '#edd8ac'),
        'Kyoto': ('#d5ddce', '#97aca4', '#9a5142', '#eadbc2'),
        'Copenhagen': ('#dce3df', '#83a3aa', '#b75d48', '#dfc27f'),
        'Edinburgh': ('#d7dbd0', '#94a28e', '#6e796e', '#a7aa92'),
        'Porto': ('#edd9bd', '#91b5b5', '#bb6f4d', '#e8cf9f'),
        'Ljubljana': ('#dbe2cd', '#89b0a5', '#b87355', '#edddb5'),
    }
    sky, water, roof, wall = palettes.get(city, palettes['Lisbon'])
    shapes = [f'<rect width="800" height="600" fill="{sky}"/>',
              '<circle cx="646" cy="110" r="56" fill="#f8edce"/>',
              '<path d="M0 270Q170 140 350 240T800 195V600H0Z" fill="#b7c2ae"/>',
              f'<path d="M0 380Q300 330 800 360V600H0Z" fill="{water}"/>']

    def building(x, y, w, h, color=wall, gable=False):
        shapes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>')
        shapes.append(f'<path d="M{x-8} {y}L{x+w/2} {y-(w*.42 if gable else 22)}L{x+w+8} {y}Z" fill="{roof}"/>')
        shapes.append(f'<rect x="{x+w-13}" y="{y}" width="13" height="{h}" fill="#233d36" opacity=".13"/>')
        for wy in range(int(y+18), int(y+h-16), 35):
            for wx in range(int(x+12), int(x+w-10), 26):
                shapes.append(f'<rect x="{wx}" y="{wy}" width="10" height="18" rx="1" fill="#37584e"/><path d="M{wx-2} {wy+20}h14" stroke="#fff4d4" stroke-width="3"/>')

    def tree(x, y, size=1, color='#3f6656'):
        shapes.append(f'<g transform="translate({x} {y}) scale({size})"><path d="M0 0v90" stroke="#52614c" stroke-width="7"/><ellipse cy="-12" rx="29" ry="58" fill="{color}"/><ellipse cx="-9" cy="-21" rx="17" ry="41" fill="#668568" opacity=".5"/></g>')

    if city in ('Lisbon', 'Porto'):
        for x, y, w, h, color in [(25,230,100,154,'#d7af76'),(128,195,90,188,'#f0dfbc'),(218,248,95,150,'#d99973'),(327,185,94,209,'#ead0a0'),(439,245,110,160,'#f0dfbb'),(565,211,91,196,'#c99878'),(675,255,106,165,'#e8d8b5')]:
            building(x,y,w,h,color)
        shapes.append('<path d="M0 430L800 397V455L0 480Z" fill="#a29c7b"/>')
        if city == 'Porto':
            shapes.append('<path d="M-30 414Q360 180 830 409M-30 434Q360 200 830 429" fill="none" stroke="#546b61" stroke-width="13"/><path d="M0 431H800M150 350V430M260 313V430M380 295V430M500 313V430M630 350V430" fill="none" stroke="#546b61" stroke-width="7"/>')
        else:
            shapes.append('<g transform="translate(105 366) rotate(-3)"><rect width="106" height="49" rx="7" fill="#d6a443"/><rect x="10" y="8" width="84" height="22" fill="#355d55"/><path d="M30 8v22m32-22v22" stroke="#d6a443" stroke-width="5"/><circle cx="20" cy="49" r="6" fill="#374c44"/><circle cx="85" cy="49" r="6" fill="#374c44"/></g>')
        shapes.append('<path d="M415 490h180l-24 22H440Z" fill="#6a6650"/><path d="M480 490v-78l58 78" fill="#f9edcf" stroke="#6a6650" stroke-width="3"/>')
    elif city == 'Kyoto':
        shapes.append('<path d="M0 295L210 112 365 294 530 140 800 310V390H0Z" fill="#8b9f87"/>')
        for y, width in [(270,230),(217,175),(174,119)]:
            x=400-width/2
            shapes.append(f'<rect x="{x+22}" y="{y-38}" width="{width-44}" height="55" fill="{wall}"/><path d="M{x-20} {y}Q400 {y-72} {x+width+20} {y}Q400 {y+20} {x-20} {y}" fill="{roof}"/><path d="M{x+40} {y-27}v34M{x+width-40} {y-27}v34" stroke="#7c5743" stroke-width="8"/>')
        shapes.append('<path d="M275 382Q400 342 540 390" fill="none" stroke="#c7b58e" stroke-width="15"/><path d="M380 123v-51" stroke="#5c6250" stroke-width="4"/><path d="M40 470Q240 390 430 464T820 480" fill="none" stroke="#d7d4b5" stroke-width="8"/>')
        for x,y,s in [(80,318,1.4),(680,320,1.2),(615,390,.7)]:tree(x,y,s)
        for x,y in [(92,120),(40,180),(710,130),(770,210)]:
            shapes.append(f'<g fill="#ac6b55"><circle cx="{x}" cy="{y}" r="65"/><circle cx="{x+48}" cy="{y+26}" r="49"/><circle cx="{x-33}" cy="{y+49}" r="44"/></g>')
    elif city == 'Copenhagen':
        for i,color in enumerate(['#ca9b64','#ece0b7','#be745a','#72928b','#cdbd87','#c98b70','#ead9ad']):
            building(22+i*111,245-(i%3)*26,101,180+(i%3)*26,color,True)
        shapes.append('<path d="M0 430H800v24H0Z" fill="#777f6a"/>')
        for x in [125,400,645]:
            shapes.append(f'<path d="M{x-65} 496h140l-24 25h-95Z" fill="#f4e5bf"/><path d="M{x} 496V335" stroke="#53685e" stroke-width="4"/><path d="M{x+5} 348l55 133h-55Z" fill="#f9f1d9"/><path d="M{x-8} 375l-41 106h41Z" fill="#bd745d"/>')
    elif city == 'Edinburgh':
        shapes.append('<path d="M30 355L200 230 320 249 485 175 680 279 800 300V430H0Z" fill="#77866d"/>')
        for x,y,w,h in [(270,179,100,150),(375,145,95,184),(480,187,90,142)]:
            building(x,y,w,h,'#92977d')
            shapes.append(f'<path d="M{x} {y}v-16h15v16h15v-16h15v16h15v-16h15v16h20" fill="none" stroke="#747f69" stroke-width="10"/>')
        for x in range(-15,800,92):building(x,371+(x%3)*9,88,149,'#c8c7a8')
        shapes.append('<path d="M0 535L800 510V600H0" fill="#5d7567"/>')
    else:
        for i,color in enumerate(['#e4c5a0','#e8d8ad','#c89773','#e8d5ae','#e5c69c']):building(30+i*150,240-(i%2)*45,128,185+(i%2)*45,color)
        shapes.append('<path d="M0 440Q400 320 800 440" fill="none" stroke="#b4b59a" stroke-width="35"/><path d="M0 418Q400 298 800 418" fill="none" stroke="#697e67" stroke-width="7"/><path d="M125 383v42M240 354v48M360 342v48M480 346v48M600 368v48" stroke="#697e67" stroke-width="6"/>')
        for x in [80,713]:tree(x,280,1.4)
    shapes += ['<path d="M0 555Q200 495 390 555T800 548V600H0Z" fill="#466b56"/>',
               '<g stroke="#f6edd4" stroke-width="2" opacity=".34"><path d="M40 505h90m95 29h120m270-9h120m-265 23h90m-510-20h90m400-46h90"/></g>',
               '<rect width="800" height="600" filter="url(#grain)" opacity=".08"/>']
    return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600"><title>'+escape(city)+' — fictional destination illustration</title><defs><filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".7" numOctaves="3" stitchTiles="stitch"/></filter></defs>'+''.join(shapes)+'</svg>'
