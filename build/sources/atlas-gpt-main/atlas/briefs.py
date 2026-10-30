"""Local, deterministic executive takeaways: 1080x1350 PNG and one-page PDF."""
import hashlib
import uuid
import io
import textwrap
from datetime import datetime
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from atlas.config import ROOT,NAME,PERSONAS

BLUE='#004BDF';PALE='#D1DDF1';META='#6B7280'
def font(size,bold=False):
 # Bundled Liberation Sans, SIL OFL 1.1; no host font directory dependency.
 base=ROOT/'static/fonts'
 return ImageFont.truetype(str(base/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),size)
def wrap(draw,text,width,f):
 lines=[]
 for paragraph in text.splitlines():
  line=''
  for word in paragraph.split():
   candidate=(line+' '+word).strip()
   if draw.textlength(candidate,font=f)>width and line:lines.append(line);line=word
   else:line=candidate
  lines.append(line)
 return lines
def export(result):
 key=uuid.uuid4().hex[:24]
 stem=f'{NAME.lower()}-brief-{key}';directory=ROOT/'artifacts';directory.mkdir(exist_ok=True)
 im=Image.new('RGB',(1080,1350),'white');d=ImageDraw.Draw(im)
 def text(x,y,value,size=24,bold=False,color='black',width=948,line_gap=7):
  f=font(size,bold)
  for line in wrap(d,str(value),width,f):d.text((x,y),line,font=f,fill=color);y+=size+line_gap
  return y
 d.rectangle((0,0,1080,14),fill=BLUE)
 text(66,53,NAME,58,True);text(66,128,'EXECUTIVE BRIEF · ON DEVICE',17,True,BLUE)
 text(66,177,PERSONAS[result['persona']]['name'],23,True)
 d.rectangle((66,230,1014,366),fill=PALE)
 text(91,251,'THE QUESTION',15,True,BLUE)
 text(91,284,result['question'],27,width=898)
 headline_size=87 if len(result['headline'])<=12 else 70
 text(66,398,result['headline'],headline_size,True)
 text(66,505,result['headline_label'],18,True,META)
 # Render the identical tool chart without any model-generated arithmetic.
 c=result['chart'];d.rectangle((66,552,1014,833),fill=PALE)
 text(90,575,c['title'].upper(),16,True,BLUE)
 values=c['values'];extras=c.get('series',[]);all_values=values+[v for s in extras for v in s['values']]
 low=min(0,min(all_values));high=max(0,max(all_values));span=max(1,high-low)
 left,right,top,bottom=112,980,628,767;zero=bottom-(0-low)/span*(bottom-top)
 d.line((left,zero,right,zero),fill='white',width=2)
 from atlas.analytics import money
 for i,label in enumerate(c['labels']):
  group=(right-left)/len(values);x=left+i*group;bar_count=1+len(extras);w=min(55,group/(bar_count+1))
  for j,val in enumerate([values[i]]+[s['values'][i] for s in extras]):
   xx=x+group/2-bar_count*w/2+j*w;yy=bottom-(val-low)/span*(bottom-top)
   d.rectangle((xx,min(yy,zero),xx+w-5,max(yy,zero)),fill=BLUE if j==0 else '#8CAEEB')
  shown=money(values[i]) if c['unit']=='currency' else f'{values[i]:.2f}×' if c['unit']=='ratio' else f'{values[i]:,.1f}'
  label_y=min(zero,bottom-(values[i]-low)/span*(bottom-top))-22
  text(int(x+group/2-d.textlength(shown,font=font(15,True))/2),int(label_y),shown,15,True,BLUE,width=int(group))
  text(int(x+3),784,str(label),13,color=META,width=int(group-6),line_gap=3)
 if extras:text(90,810,'BLUE: FORECAST     LIGHT BLUE: '+extras[0]['name'].upper(),11,True,META)
 y=text(66,869,result['answer'],24,width=948,line_gap=8)
 y=max(1015,y+23);text(66,y,'HOW I GOT THIS',15,True,BLUE)
 y=text(66,y+33,result['method']['formula'],18,width=948,line_gap=6)
 sources=', '.join(s['table'] for s in result['sources'])
 text(66,min(1218,y+15),'Local sources: '+sources,14,color=META)
 d.rectangle((0,1272,1080,1350),fill=BLUE)
 text(66,1288,'Generated on HP ZGX Fury in London. Frankfurt access requires WAN.',19,True,'white')
 text(66,1320,'All data synthetic. Fictional companies. Snapshot '+result['method']['as_of']+'.',13,color='white')
 png=directory/(stem+'.png');pdf=directory/(stem+'.pdf');im.save(png)
 out=canvas.Canvas(str(pdf),pagesize=(540,675));out.setTitle(NAME+' Executive Brief');out.setAuthor(NAME+' local analytics');out.drawImage(ImageReader(im),0,0,width=540,height=675);out.showPage();out.save()
 return {'png':'/artifacts/'+png.name,'pdf':'/artifacts/'+pdf.name,'width':1080,'height':1350,'question':result['question'],'grounded':result['grounding']['passed']}
