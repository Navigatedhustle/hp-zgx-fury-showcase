"""Recorded walkthrough with an authentic artifact and fresh per-session app data.

Playback never submits model requests. Only sanitized, curated recording fields
are distributed. Timing is compressed and explicitly disclosed in the browser.
"""
import copy,hashlib,json,shutil,threading,time
from collections import deque
from pathlib import Path
from travel_run import TravelRun
EXAMPLE=Path(__file__).with_name('examples')/'recorded-travel'
class GuidedRun(TravelRun):
 mode='recorded'
 def __init__(self):
  super().__init__()
  self.recording=json.loads((EXAMPLE/'recording.json').read_text())
  self.recorded_usage={key:sum(c.get('usage',{}).get(field,0) for c in self.recording['calls']) for key,field in [('input_tokens','prompt_tokens'),('output_tokens','completion_tokens')]}
  for name,digest in self.recording['files'].items():
   source=EXAMPLE/name
   if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise RuntimeError('Recorded application checksum mismatch')
   shutil.copyfile(source,self.candidate/name)
  self.tasks=[];self.calls=[];self.events=[];self.seq=0
  self.product.update(criteria=copy.deepcopy(self.recording['criteria']),next_action='Recorded walkthrough · no live inference',recorded=True)
  self.tests={'passed':True,'recorded':True,'verification':self.recording['verification']}
  self.promote('Recorded successful travel application · supplied artifact')
  self.versions[-1]['stage']='recorded';self.save()
 def start(self):
  self.started=time.time();self.state='running';self.stop_event.clear();self.save()
 def stop(self):
  self.state='stopped';self.stop_event.set();self.event('terminal',state=self.state)
 def snapshot(self,compact=False):
  if self.state=='running' and self.started and time.time()-self.started>=self.recording['playback_s']:
   self.state='finished';self.event('terminal',state=self.state)
  d=super().snapshot(compact=compact);record=getattr(self,'recording',None)
  if not record:return d
  elapsed=min(d['elapsed_s'],record['playback_s']);fraction=min(1,elapsed/record['playback_s']) if self.started else 0;position=fraction*record['duration_s']
  events=[e for e in record['events'] if e['offset']<=position]
  d.update(mode='recorded',recording_description=record['description'],recorded_duration_s=record['duration_s'],recorded_position_s=position)
  d['events']=[{'seq':i+1,'job_id':self.id,'time':e['offset'],'kind':e['kind'],'title':e['title'],'recorded':True} for i,e in enumerate(events)]
  d['seq']=len(events);d['calls']=[{**c,'status':'complete','current_tps':None,'live_supported':False,'recorded':True} for c in record['calls'] if c['offset']<=position]
  d['tasks']=[{**t,'id':'recorded-task-'+str(i),'dependencies':[],'status':'merged' if any(e['kind']=='task merged' and e['title']==t['title'] for e in events) else 'pending'} for i,t in enumerate(record['tasks'])]
  d['product']['next_action']='Recorded: '+(events[-1]['title'] if events else 'Preparing the application')
  return d
