"""Pure customer palette mathematics. Semantic status tokens are never overridden."""
import colorsys
import math
import re
from collections import Counter

DEFAULT_PRIMARY = '#4c9cff'
SEMANTIC = {'--mc-lime': '#b5ee73', '--mc-amber': '#f5c46d', '--mc-red': '#ff8d92'}


def rgb(value):
    from PIL import ImageColor
    return tuple(v / 255 for v in ImageColor.getrgb(value)[:3])


def linear(v):
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def srgb(v):
    return 12.92 * v if v <= .0031308 else 1.055 * max(0, v) ** (1 / 2.4) - .055


def oklab(color):
    r, g, b = map(linear, rgb(color) if isinstance(color, str) else color)
    l = (.4122214708*r + .5363325363*g + .0514459929*b) ** (1/3)
    m = (.2119034982*r + .6806995451*g + .1073969566*b) ** (1/3)
    s = (.0883024619*r + .2817188376*g + .6299787005*b) ** (1/3)
    return (.2104542553*l + .793617785*m - .0040720468*s,
            1.9779984951*l - 2.428592205*m + .4505937099*s,
            .0259040371*l + .7827717662*m - .808675766*s)


def hex_lab(lab):
    l, a, b = lab
    x = (l + .3963377774*a + .2158037573*b)**3
    y = (l - .1055613458*a - .0638541728*b)**3
    z = (l - .0894841775*a - 1.291485548*b)**3
    values = (4.0767416621*x - 3.3077115913*y + .2309699292*z,
              -1.2684380046*x + 2.6097574011*y - .3413193965*z,
              -.0041960863*x - .7034186147*y + 1.707614701*z)
    return '#' + ''.join(f'{round(min(1,max(0,srgb(v)))*255):02x}' for v in values)


def lch(color):
    l, a, b = oklab(color)
    return l, math.hypot(a,b), math.degrees(math.atan2(b,a)) % 360


def from_lch(l, c, h):
    return hex_lab((l, c*math.cos(math.radians(h)), c*math.sin(math.radians(h))))


def contrast(a, b):
    def lum(v):
        r,g,b = map(linear,rgb(v));return .2126*r + .7152*g + .0722*b
    x,y = sorted((lum(a),lum(b)))
    return (y+.05)/(x+.05)


def accessible(color, panel, threshold):
    l,c,h = lch(color)
    # Preserve hue; try lightness before reducing chroma. Quantized output is checked.
    for chroma in (c,c*.8,c*.6,c*.3,0):
        for i in range(101):
            candidate = from_lch(l+(1-l)*i/100,chroma,h)
            if contrast(candidate,panel) >= threshold:return candidate
    return '#ffffff'


def raster_colors(image):
    """Deterministic k=6 Lloyd clustering in OKLab; alpha/background excluded."""
    import numpy as np
    pixels = np.array(image.convert('RGBA').resize((128,128)),dtype=float).reshape(-1,4)/255
    pixels = pixels[(pixels[:,3]>.95)&(pixels[:,:3].max(axis=1)>.10)&(pixels[:,:3].min(axis=1)<.94)]
    if not len(pixels):return []
    labs = np.array([oklab(tuple(p[:3])) for p in pixels])
    order = np.argsort(labs[:,0],kind='stable')
    centers = labs[order[np.linspace(0,len(labs)-1,6).astype(int)]]
    for _ in range(24):
        labels = ((labs[:,None,:]-centers[None,:,:])**2).sum(axis=2).argmin(axis=1)
        new = np.array([labs[labels==i].mean(axis=0) if (labels==i).any() else centers[i] for i in range(6)])
        if np.allclose(new,centers,atol=1e-6):break
        centers = new
    return [(hex_lab(center),int((labels==i).sum())) for i,center in enumerate(centers) if (labels==i).any()]


def svg_colors(root):
    """Paint weights use geometric area (path coordinate bounds approximate area)."""
    weights = Counter()
    def number(v,default=0):
        try:return float(re.match(r'[-+.\deE]+',str(v))[0])
        except (ValueError,TypeError):return default
    def visit(node, inherited):
        attrs = dict(inherited);attrs.update(node.attrib)
        tag = node.tag.split('}')[-1]
        if tag in ('defs','clipPath','mask','title','desc'):return
        if tag=='rect':area = number(attrs.get('width'))*number(attrs.get('height'))
        elif tag in ('circle','ellipse'):area = math.pi*number(attrs.get('r',attrs.get('rx')))*number(attrs.get('r',attrs.get('ry')))
        elif tag in ('path','polygon','polyline'):
            nums = [float(v) for v in re.findall(r'[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?',attrs.get('d',attrs.get('points','')))]
            xs,ys = nums[::2],nums[1::2];area = (max(xs)-min(xs))*(max(ys)-min(ys)) if xs and ys else 1
        else:area = 1
        if tag in ('rect','circle','ellipse','path','polygon','polyline','text','line'):
            for key in ('fill','stroke'):
                value = attrs.get(key,'#000000' if key=='fill' else 'none')
                try:
                    if number(attrs.get('opacity',1))>0 and number(attrs.get(key+'-opacity',1))>0:
                        color = '#'+''.join(f'{round(x*255):02x}' for x in rgb(value));weights[color]+=max(1,area)*(1 if key=='fill' else .1)
                except (ValueError,TypeError):pass
        for child in node:visit(child,{k:v for k,v in attrs.items() if k in ('fill','stroke','opacity','fill-opacity','stroke-opacity')})
    visit(root,{})
    return list(weights.items())


def palette(colors, hint=None, primary=None, accent=None):
    chromatic = [(color,weight) for color,weight in colors if lch(color)[1]>.04]
    chromatic.sort(key=lambda x:x[1],reverse=True)
    if hint:
        try:
            # A site hint breaks near ties; it does not invent logo colors.
            if chromatic:
                top=chromatic[0][1];chromatic.sort(key=lambda x:(x[1]>=top*.9,-sum((a-b)**2 for a,b in zip(oklab(x[0]),oklab(hint))) if x[1]>=top*.9 else x[1]),reverse=True)
        except ValueError:pass
    monochrome = not chromatic and primary is None
    primary = primary or (chromatic[0][0] if chromatic else DEFAULT_PRIMARY)
    rgb(primary)
    if not accent:
        accent = next((c for c,_ in chromatic if math.dist(oklab(primary),oklab(c))*100>=25),None)
        if not accent:
            l,c,h=lch(primary);accent=from_lch(l,c,h+30)
    rgb(accent)
    _,_,h=lch(primary);red_h=lch(SEMANTIC['--mc-red'])[2]
    red_brand = min((h-red_h)%360,(red_h-h)%360)<25
    surface_h=h+30 if red_brand else h
    bg,panel,raised=[from_lch(l,.015 if l==.13 else .022,surface_h) for l in (.13,.17,.19)]
    text=accessible(primary,panel,4.5);edge=accessible(primary,panel,3);act=accessible(accent,panel,4.5)
    variables={'--mc-bg':bg,'--mc-panel':panel,'--mc-raise':raised,'--mc-blue':text,'--mc-cyan':act,'--mc-line':edge,
               '--bg':bg,'--panel':panel,'--surface':panel,'--surface-raised':raised,'--action':text,'--accent':act,'--border':edge}
    if monochrome:
        variables={};text=DEFAULT_PRIMARY;act='#69d9ee';panel='#101c2e';edge=DEFAULT_PRIMARY
    return {'primary':primary,'accent':accent,'swatches':[c for c,_ in sorted(colors,key=lambda x:x[1],reverse=True)[:6]],
            'variables':variables,'monochrome':monochrome,'red_brand':red_brand,
            'note':'Logo is monochrome, default accent kept' if monochrome else 'Brand hue preserved; semantic status colors retained.',
            'contrast':{'text':contrast(text,panel),'accent':contrast(act,panel),'ui':contrast(edge,panel)}}


def css(theme):
    return ':root:root {'+';'.join(k+':'+v for k,v in theme.get('variables',{}).items() if re.fullmatch(r'--[a-z-]+',k) and re.fullmatch(r'#[0-9a-fA-F]{6}',v))+'}'
