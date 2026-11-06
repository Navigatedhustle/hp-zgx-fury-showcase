#!/usr/bin/env python3
"""Actual reset/idle/optional preview/export checks, using fictional skin only."""
import argparse
import asyncio
import io
import json
import os
import sqlite3
import subprocess
import time
import zipfile
from pathlib import Path
import httpx
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[2]


async def main(output):
 report={};config=ROOT/'config/skin.json';original=config.read_text()
 def configure(value):
  temp=config.with_suffix('.tmp');temp.write_text(value);temp.replace(config)
 async with httpx.AsyncClient(base_url='http://localhost:8080',trust_env=False,timeout=15) as client:
  r=await client.post('/skin/unlock',json={'pin':(ROOT/'state/skin-presenter.pin').read_text().strip()});r.raise_for_status()
  state=(await client.get('/skin/state')).json();base=state['active'];assert base['name']=='Northwind Beverages';counter=state['public_web_lookups']
  async def restore():
   r=await client.post('/skin/apply',json={'id':base['id'],'primary':base['theme']['primary'],'accent':base['theme']['accent'],'pack':base['pack']});r.raise_for_status()
  reset=await asyncio.create_subprocess_exec('python3','ops/event-session.py','reset','--name','Conference session',cwd=ROOT,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE);await reset.communicate();assert reset.returncode==0
  assert (await client.get('/skin/state')).json()['active'] is None;report['actual_host_event_reset']=True
  await restore();path=ROOT/'state/skin/active.json';before=path.stat().st_mtime
  await client.get('/skin/state');await client.get('/skin/active.css');assert path.stat().st_mtime==before;report['polling_does_not_touch_retention']=True
  value=json.loads(path.read_text());old=time.time()-8*3600-2;value['touched']=old;path.write_text(json.dumps(value));os.utime(path,(old,old))
  assert (await client.get('/skin/state')).json()['active'] is None;assert not path.exists();report['idle_expiry_with_backdated_fixture']=True
  await restore()
  try:
   settings=json.loads(original);settings['presentations_booth_palette']=True;configure(json.dumps(settings,indent=2)+'\n')
   sheet=(await client.get('/skin/booth.css')).text;assert '.bf' in sheet;assert 'Northwind' not in sheet;assert '/skin/logo/' not in sheet
   with sqlite3.connect('file:'+str(ROOT/'state/slides/app.db')+'?mode=ro',uri=True) as db:pid=db.execute("SELECT id FROM project WHERE source='composed' AND status='complete' LIMIT 1").fetchone()[0]
   async with async_playwright() as p:
    browser=await p.chromium.launch(args=['--no-sandbox']);page=await browser.new_page(viewport={'width':1366,'height':768});await page.goto('http://localhost:8765/booth');await page.wait_for_function('()=>Boolean(window.FurySkin)')
    await page.evaluate("pid=>{const f=document.createElement('iframe');f.id='skin-deck-check';f.src='/api/projects/'+pid+'/deck';document.getElementById('stage').append(f)}",pid)
    frame=page.frame_locator('#skin-deck-check');await frame.locator('.bf').first.wait_for();await frame.locator('#fury-booth-palette').wait_for(state='attached')
    from PIL import ImageColor
    expected='rgb('+', '.join(str(v) for v in ImageColor.getrgb(base['theme']['variables']['--mc-bg']))+')'
    await expect(frame.locator('.bf').first).to_have_css('background-color',expected)
    assert await frame.locator('img[src*="/skin/"]').count()==0
    report['actual_booth_palette_css_only']=True;await browser.close()
   async with httpx.AsyncClient(trust_env=False,timeout=90) as exports:
    result=await exports.get('http://localhost:8765/api/projects/'+pid+'/export.pptx?editable=true');result.raise_for_status()
   with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
    assert len([n for n in archive.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==3
    for name in archive.namelist():
     data=archive.read(name);assert b'Northwind' not in data;assert b'/skin/logo/' not in data
   report['actual_pptx_has_no_customer_identity']=True
  finally:configure(original)
  await restore();state=(await client.get('/skin/state')).json();assert state['public_web_lookups']==counter
  assert (await client.get('/skin/booth.css')).text=='';report['booth_palette_default_off_restored']=True
 report['scope']='Actual local services; idle expiry uses backdated fictional state, not an eight-hour observation. Existing fictional booth deck exported without new inference.'
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);asyncio.run(main(parser.parse_args().output))
