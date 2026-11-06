#!/usr/bin/env python3
"""Host-shell event preparation; customer content persists only in state/skin/."""
import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from showcase_app import skin


async def prep(names):
 for number,name in enumerate(names,1):
  job=skin.new_lookup(name);await job['_task']
  if job['status']=='entities':
   print('Choose the official entity for lookup',number)
   for i,row in enumerate(job['entities'],1):print(i,row['name'],row.get('domain') or 'No official domain',row['description'])
   selection=input('Entity number, or Enter to skip: ').strip()
   if not selection:continue
   try:
    index=int(selection)
    if not 1<=index<=len(job['entities']):raise ValueError()
    entity=job['entities'][index-1]
   except (ValueError,IndexError):print('Invalid selection; skipped.');continue
   job['status']='researching';await skin.collect_candidates(job,entity)
  candidates=job['candidates']
  if not candidates:print('No candidates. Use the presenter panel to upload a PNG or SVG.');continue
  print('Lookup',number,'logo candidates; inspect the local files before confirming:')
  for i,row in enumerate(candidates,1):print(i,row['source'],skin.STATE/'cache'/row['id']/Path(row['logo']).name)
  selection=input('Confirm logo number, or Enter to skip: ').strip()
  if not selection:continue
  try:
   index=int(selection)
   if not 1<=index<=len(candidates):raise ValueError()
   value=candidates[index-1]
  except (ValueError,IndexError):print('Invalid selection; skipped.');continue
  value['confirmed']=True;skin.write_json(skin.STATE/'cache'/value['id']/'skin.json',value)
  print('Cached for one tap switching. Nothing was applied.')


def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prep','list','clear']);parser.add_argument('names',nargs='*');args=parser.parse_args()
 if args.action=='prep':
  if not args.names:parser.error('prep requires one or more names')
  asyncio.run(prep(args.names))
 elif args.action=='list':
  for i,value in enumerate(skin.recent(),1):print(i,value['name'],value['source'],'confirmed' if value.get('confirmed') else 'presenter confirmation required')
 else:
  skin.reset();shutil.rmtree(skin.STATE/'cache',ignore_errors=True);print('Active skin and cached logos cleared. Public request counter retained.')


if __name__=='__main__':main()
