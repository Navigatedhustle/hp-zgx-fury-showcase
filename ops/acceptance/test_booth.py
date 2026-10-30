"""Focused malformed-output fixtures; never touches the live project store."""
import sys,asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'build/sources/html_builder-main/backend'))
from app import booth as m
from app.llm.client import LLMResult
from app.store.db import Project,Slide,Version
VALID={'title':'Fixture','slides':[{'title':'Fixture '+str(i),'subtitle':'Synthetic validation','points':['One','Two','Three'],'notes':'Fixture only'} for i in range(3)]}
class BoothTests(unittest.TestCase):
 def check(self,texts):
  p=Project(id='pfixture',name='Fixture',filename='',status='generating');saved=[];seen=[]
  async def chat(*args,**kwargs):
   self.assertFalse(any(isinstance(x,(Slide,Version)) for x in saved),'Artifacts were written before author validation')
   seen.append(kwargs);return LLMResult(text=texts[len(seen)-1],model='fixture',finish_reason='stop')
  def save(obj):saved.append(obj);return obj
  with tempfile.TemporaryDirectory() as folder,patch.object(m,'BOOTH_EVIDENCE',Path(folder)),patch.object(m,'pending',1),patch.object(m.llm,'chat',side_effect=chat),patch.object(m.db,'get',return_value=p),patch.object(m.db,'save',side_effect=save):asyncio.run(m.generate('pfixture','Synthetic fixture brief'))
  return p,saved,seen
 def test_invalid_then_valid_is_repaired_before_artifacts(self):
  p,saved,calls=self.check(['This is not JSON',json.dumps(VALID)]);self.assertEqual(p.status,'complete');self.assertEqual(len(calls),2);self.assertEqual(len({x.id for x in saved if isinstance(x,Slide)}),3);self.assertTrue(all(c['response_format']['json_schema']['strict'] for c in calls))
 def test_two_invalid_outputs_fail_without_partial_slides(self):
  p,saved,calls=self.check(['broken','broken']);self.assertEqual(p.status,'error');self.assertEqual(len(calls),2);self.assertFalse(any(isinstance(x,(Slide,Version)) for x in saved))
if __name__=='__main__':unittest.main()
