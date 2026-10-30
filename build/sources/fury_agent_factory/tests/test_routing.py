
"""Synthetic transport tests for real gateway routing and slot release."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
import showcase_app.gateway as g
from fastapi import HTTPException
RealClient=httpx.AsyncClient
class Request:
 def __init__(self,model,cid):self.body={'model':model,'stream':True,'messages':[]};self.headers={'x-fury-call-id':cid}
 async def json(self):return self.body
 async def stream(self):yield json.dumps(self.body).encode()
class RoutingTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.addCleanup(self.tmp.cleanup)
 def test_legacy_routes_keep_qwen_and_unknown_new_alias_rejected(self):
  self.assertEqual(g.select('atlas',g.LEAD),('atlas',g.MODEL));self.assertEqual(g.select('agent/v1',g.LEAD),('agent',g.MODEL));self.assertEqual(g.select('devteam/v1',g.LEAD),('agent',g.LEAD))
  with self.assertRaises(HTTPException):g.select('devteam/v1','remote-model')
 def test_real_stream_preserved_accounted_once_and_slot_released(self):
  urls=[]
  def endpoint(req):
   urls.append(str(req.url));return httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: '+json.dumps({'choices':[{'delta':{'content':'ok'}}]})+'\n\ndata: '+json.dumps({'choices':[],'usage':{'prompt_tokens':4,'completion_tokens':2}})+'\n\ndata: [DONE]\n\n')
  def client(**kw):return RealClient(transport=httpx.MockTransport(endpoint))
  async def perform():
   response=await g.chat('devteam/v1',Request(g.LEAD,'fixture:one'))
   body=b''.join([part async for part in response.body_iterator]);self.assertIn(b'\n\n',body)
   self.assertEqual(g.normal._value,3);self.assertEqual(g.total._value,4);self.assertEqual(g.lead_slots._value,1)
   with self.assertRaises(HTTPException) as error:await g.chat('devteam/v1',Request(g.LEAD,'fixture:one'))
   self.assertEqual(error.exception.status_code,409)
  with patch.object(g,'DB',Path(self.tmp.name)/'ledger.sqlite'),patch.object(g.httpx,'AsyncClient',side_effect=client):asyncio.run(perform())
  self.assertEqual(urls,['http://127.0.0.1:8100/v1/chat/completions'])
  with patch.object(g,'DB',Path(self.tmp.name)/'ledger.sqlite'):
   c=g.connect();row=c.execute('SELECT status,output_tokens FROM events WHERE id=?',('fixture:one',)).fetchone();c.close();self.assertEqual(row,('complete',2))
 def test_lead_waiter_does_not_hold_atlas_or_normal_slots(self):
  async def perform():
   with patch.object(g,'lead_slots',asyncio.Semaphore(0)):
    response=await g.chat('devteam/v1',Request(g.LEAD,'fixture:waiting'))
    async def consume():return [p async for p in response.body_iterator]
    task=asyncio.create_task(consume());await asyncio.sleep(.02)
    self.assertEqual(g.normal._value,3);self.assertEqual(g.total._value,4)
    task.cancel();await asyncio.gather(task,return_exceptions=True)
    self.assertFalse(g.waiting);self.assertFalse(g.active)
  with patch.object(g,'DB',Path(self.tmp.name)/'ledger.sqlite'):asyncio.run(perform())
if __name__=='__main__':unittest.main()
