"""Pure customer palette mathematics. Semantic status tokens are never overridden."""
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


def linear_lab(lab):
    l, a, b = lab
    x = (l + .3963377774*a + .2158037573*b)**3
    y = (l - .1055613458*a - .0638541728*b)**3
    z = (l - .0894841775*a - 1.291485548*b)**3
    return (4.0767416621*x - 3.3077115913*y + .2309699292*z,
              -1.2684380046*x + 2.6097574011*y - .3413193965*z,
              -.0041960863*x - .7034186147*y + 1.707614701*z)


def hex_lab(lab):
    values=linear_lab(lab)
    return '#' + ''.join(f'{round(min(1,max(0,srgb(v)))*255):02x}' for v in values)


def lch(color):
    l, a, b = oklab(color)
    return l, math.hypot(a,b), math.degrees(math.atan2(b,a)) % 360


def from_lch(l, c, h):
    def lab(chroma):return (l,chroma*math.cos(math.radians(h)),chroma*math.sin(math.radians(h)))
    if not all(-1e-7<=v<=1.0000001 for v in linear_lab(lab(c))):
        low,high=0,c
        for _ in range(24):
            mid=(low+high)/2
            if all(0<=v<=1 for v in linear_lab(lab(mid))):low=mid
            else:high=mid
        c=low
    return hex_lab(lab(c))


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
            lightness=l+(1-l)*i/100
            lab=(lightness,chroma*math.cos(math.radians(h)),chroma*math.sin(math.radians(h)))
            if not all(-1e-7<=v<=1.0000001 for v in linear_lab(lab)):continue
            candidate = hex_lab(lab)
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
    """Paint weights use geometric area; paths integrate curves with AreaPen."""
    weights = Counter()
    def number(v,default=0):
        try:return float(re.match(r'[-+.\deE]+',str(v))[0])
        except (ValueError,TypeError):return default
    gradients={node.get('id'):[child.get('stop-color','#000000') for child in node if child.tag.split('}')[-1]=='stop' and number(child.get('stop-opacity',1))>0]
               for node in root.iter() if node.tag.split('}')[-1] in ('linearGradient','radialGradient')}
    def visit(node, inherited,scale=1,alpha=1):
        attrs = dict(inherited);attrs.update(node.attrib)
        tag = node.tag.split('}')[-1]
        if tag in ('defs','clipPath','mask','title','desc'):return
        for kind,values in re.findall(r'(scale|matrix)\s*\(([^)]+)\)',node.get('transform','')):
            nums=[float(v) for v in re.findall(r'[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?',values)]
            if kind=='scale' and nums:scale*=abs(nums[0]*(nums[1] if len(nums)>1 else nums[0]))
            if kind=='matrix' and len(nums)==6:scale*=abs(nums[0]*nums[3]-nums[1]*nums[2])
        alpha*=max(0,min(1,number(node.get('opacity',1))))
        perimeter=0
        if tag=='rect':
            w,h=number(attrs.get('width')),number(attrs.get('height'));area=w*h;perimeter=2*(w+h)
        elif tag in ('circle','ellipse'):
            a,b=number(attrs.get('r',attrs.get('rx'))),number(attrs.get('r',attrs.get('ry')));area=math.pi*a*b
            perimeter=math.pi*(3*(a+b)-math.sqrt(max(0,(3*a+b)*(a+3*b))))
        elif tag=='path':
            try:
                from fontTools.pens.areaPen import AreaPen
                from fontTools.svgLib.path import parse_path
                pen=AreaPen(None);parse_path(attrs.get('d',''),pen);area=abs(pen.value)
            except (ValueError,TypeError,NotImplementedError):area=1
            try:
                from fontTools.pens.perimeterPen import PerimeterPen
                pen=PerimeterPen(None);parse_path(attrs.get('d',''),pen);perimeter=pen.value
            except (ValueError,TypeError,NotImplementedError):perimeter=0
        elif tag in ('polygon','polyline'):
            nums = [float(v) for v in re.findall(r'[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?',attrs.get('d',attrs.get('points','')))]
            points=list(zip(nums[::2],nums[1::2]));area=abs(sum(x*y2-x2*y for (x,y),(x2,y2) in zip(points,points[1:]+points[:1])))/2 if points else 1
            perimeter=sum(math.dist(a,b) for a,b in zip(points,points[1:]+(points[:1] if tag=='polygon' else [])))
        elif tag=='line':
            area=0;perimeter=math.hypot(number(attrs.get('x2'))-number(attrs.get('x1')),number(attrs.get('y2'))-number(attrs.get('y1')))
        else:area = 1
        if tag in ('rect','circle','ellipse','path','polygon','polyline','text','line'):
            for key in ('fill','stroke'):
                value = attrs.get(key,'#000000' if key=='fill' else 'none')
                if value=='currentColor':value=attrs.get('color','#000000')
                match=re.fullmatch(r'url\(#([\w.-]+)\)',value)
                paints=gradients.get(match[1],[]) if match else [value]
                weight=(area if key=='fill' else perimeter*number(attrs.get('stroke-width',1)))*scale*alpha*max(0,min(1,number(attrs.get(key+'-opacity',1))))
                try:
                    for paint in paints:
                        if weight>0:
                            color = '#'+''.join(f'{round(x*255):02x}' for x in rgb(paint));weights[color]+=weight/max(1,len(paints))
                except (ValueError,TypeError):pass
        for child in node:visit(child,{k:v for k,v in attrs.items() if k in ('fill','stroke','color','fill-opacity','stroke-opacity','stroke-width')},scale,alpha)
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
    # Leave a small margin for 8-bit sRGB quantization at the requested bounds.
    bg,panel,raised=[from_lch(l,c,surface_h) for l,c in ((.135,.015),(.17,.022),(.185,.022))]
    text=accessible(primary,panel,4.5);edge=accessible(primary,panel,3);act=accessible(accent,panel,4.5)
    variables={'--mc-bg':bg,'--mc-panel':panel,'--mc-raise':raised,'--mc-blue':text,'--mc-cyan':act,'--mc-line':edge,
               '--mc-text':'#edf5ff','--mc-muted':'#9eb0c7','--bg':bg,'--page':bg,'--panel':panel,'--surface':panel,'--surface-raised':raised,'--action':text,'--accent':act,'--border':edge,'--text':'#edf5ff','--subtle':'#9eb0c7','--on-action':bg,'--focus':text}
    if monochrome:
        variables={};text=DEFAULT_PRIMARY;act='#69d9ee';panel='#101c2e';edge=DEFAULT_PRIMARY
    return {'primary':primary,'accent':accent,'swatches':[c for c,_ in sorted(colors,key=lambda x:x[1],reverse=True)[:6]],
            'variables':variables,'monochrome':monochrome,'red_brand':red_brand,
            'note':'Logo is monochrome, default accent kept' if monochrome else 'Brand hue preserved; semantic status colors retained.',
            'contrast':{'text':contrast(text,panel),'accent':contrast(act,panel),'ui':contrast(edge,panel)}}


def css(theme):
    return ':root:root {'+';'.join(k+':'+v for k,v in theme.get('variables',{}).items() if k not in SEMANTIC and re.fullmatch(r'--[a-z-]+',k) and re.fullmatch(r'#[0-9a-fA-F]{6}',v))+'}'
