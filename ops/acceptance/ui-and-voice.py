"""Local browser UI/accounting check and real synthetic TTS -> ASR round trip."""
import asyncio,audioop,base64,io,json,sqlite3,time,wave
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
async def main():
 out=ROOT/'reports/ui-voice';out.mkdir(parents=True,exist_ok=True);report={'started':time.time(),'scope':'Headless local Chromium and real local audio models; no physical microphone/speaker claim'}
 async with async_playwright() as p:
  b=await p.chromium.launch(args=['--no-sandbox']);page=await b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://localhost:8080');await page.get_by_text('Atlas',exact=True).first.wait_for()
  with sqlite3.connect(ROOT/'state/slides/app.db') as db:before=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
  await page.goto('http://localhost:8080/operator');await page.wait_for_timeout(6000)
  live=await page.evaluate("fetch('/api/live').then(r=>{if(!r.ok)throw Error(r.status);return r.json()})");assert live
  with sqlite3.connect(ROOT/'state/slides/app.db') as db:after=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
  assert before==after,'Inference ledger changed during idle observation; rerun without other workflows';report['operator_no_inference_calls']=True
  await page.goto('http://localhost:8200');await page.wait_for_function('()=>typeof config!=="undefined"&&!!config');await page.evaluate('voice=false;attract=false')
  encoded=await page.evaluate("""async()=>{const r=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'What is our forecast revenue for the next quarter?'})});if(!r.ok)throw Error('TTS '+r.status);const a=new Uint8Array(await r.arrayBuffer());let s='';for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(s)}""")
  pcm=base64.b64decode(encoded);assert len(pcm)>24000
  audio,_=audioop.ratecv(pcm,2,1,24000,16000,None);stream=io.BytesIO()
  with wave.open(stream,'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(audio)
  result=await page.evaluate("""async data=>{const a=Uint8Array.from(atob(data),c=>c.charCodeAt(0));const r=await fetch('/api/transcribe',{method:'POST',body:a});if(!r.ok)throw Error('ASR '+r.status);return r.json()}""",base64.b64encode(stream.getvalue()).decode())
  text=result.get('text','').lower();assert 'revenue' in text or 'forecast' in text,result
  report.update(tts_pcm_bytes=len(pcm),transcription=result,browser_errors=errors,passed=not errors,ended=time.time());assert not errors,errors
  await page.screenshot(path=str(out/'browser.png'));await b.close()
 (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
asyncio.run(main())
