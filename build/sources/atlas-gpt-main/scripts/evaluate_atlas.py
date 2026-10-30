"""Measure the actual local demo. Never fill gaps with invented benchmark values."""
import json
import statistics
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import httpx
from atlas.config import GOLDEN, ROOT
from atlas.grounding import check

def run():
    records=[]
    with httpx.Client(base_url='http://127.0.0.1:8200',timeout=45,trust_env=False) as client:
        for _ in range(120):
            try:
                client.get('/api/health').raise_for_status();break
            except httpx.HTTPError:time.sleep(.25)
        for index,(persona,expected,question) in enumerate(GOLDEN,1):
            start=time.perf_counter()
            response=client.post('/api/query',json={'question':question,'persona':persona});response.raise_for_status();r=response.json()
            total=(time.perf_counter()-start)*1000
            report=check(r['answer'],r)
            rec={'index':index,'persona':persona,'expected':expected,'actual':r.get('tool'),'routing_correct':r.get('tool')==expected,'grounding':report,'grounding_fallback':r.get('grounding',{}).get('fallback'),'wall_ms':total,'timings':r.get('timings'),'answer':r['answer'],'headline':r.get('headline')}
            # Start only the first approved sentence; exclude playback duration.
            from atlas.speech import sentences
            first=sentences(r['answer'])[0]
            start_audio=time.perf_counter()
            try:
                audio=client.post('/api/speech',json={'text':first});audio.raise_for_status()
                rec['first_sentence_audio_bytes']=len(audio.content)
                rec['tts_ms']=(time.perf_counter()-start_audio)*1000
                rec['text_to_first_audio_s']=(total+rec['tts_ms'])/1000
                rec['audio_cache']=audio.headers.get('X-Local-Audio-Cache','not reported')
            except httpx.HTTPError as exc:rec['speech_error']=str(exc)
            records.append(rec);print(json.dumps(rec),flush=True)
        telemetry=client.get('/api/telemetry').json()
    timestamp=datetime.now(ZoneInfo('America/Denver')).isoformat()
    (ROOT/'eval/golden-results.json').write_text(json.dumps({'measured_at':timestamp,'records':records,'telemetry':telemetry},indent=2))
    correct=sum(r['routing_correct'] for r in records);numbers=sum(r['grounding']['checked'] for r in records);passed=sum(r['grounding']['checked'] for r in records if r['grounding']['passed']);latencies=[r['text_to_first_audio_s'] for r in records if 'text_to_first_audio_s' in r]
    lines=['# Measured Atlas golden evaluation','',f'Measured: {timestamp}',f'Golden routing: {correct}/{len(records)}.',f'Final checked numbers: {passed}/{numbers}.',f'Final numerical grounding: {100*passed/numbers:.1f}%.' if numbers else 'No numerical claims measured.',f'Text-to-first-sentence audio median: {statistics.median(latencies):.3f} s.' if latencies else 'No successful speech timing.', '', 'These timings include local tool selection and narration plus first sentence synthesis/lookup. They do not include spoken input, browser playback scheduling, or human microphone interaction. Audio cache hits are labeled per row. Generated-audio streaming recognition is evaluated separately.','', '| Question | Tool | Route | Grounded | Answer ms | First sentence ms | Cache |','|---|---|---|---|---:|---:|---|']
    for r in records:lines.append(f'| {r["index"]} | {r["actual"]} | {"pass" if r["routing_correct"] else "FAIL"} | {"pass" if r["grounding"]["passed"] else "FAIL"} | {r["wall_ms"]:.1f} | {r.get("tts_ms",float("nan")):.1f} | {r.get("audio_cache","unavailable")} |')
    lines+=['','The target is 1.5 s after end of speech. Text timings are not a substitute for that end-to-end target. Uncached synthesis and real streaming ASR must be measured and disclosed separately.','', 'Network proof uses real non-loopback TX and actual default routes. Host TX includes other processes, so the cloud figure is labeled as an upper bound. GPU memory accounting on GB10 requires more than process RSS/PSS; telemetry methodology and peak-memory limits must be read with the scorecard.']
    (ROOT/'eval/REPORT.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':run()
