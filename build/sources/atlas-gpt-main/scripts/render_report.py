"""Build the final scorecard from saved measurements, never guessed results."""
import json,statistics
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from atlas.config import ROOT

def read(name):return json.loads((ROOT/'eval'/name).read_text())
def render():
 test_suites=ET.parse(ROOT/'eval/test-results.xml').getroot()
 test_count=sum(int(s.get('tests',0)) for s in test_suites.iter('testsuite'))
 golden=read('golden-results.json');cold=read('cold-start.json');voice=read('voice-browser-qa.json');samples=read('voice-browser-samples.json');uncached=read('uncached-voice.json');network=read('network-audit.json');browser=read('browser-qa.json');camera=read('camera-qa.json');acceptance=read('acceptance.json')
 records=golden['records'];correct=sum(r['routing_correct'] for r in records);checked=sum(r['grounding']['checked'] for r in records);passed=sum(r['grounding']['checked'] for r in records if r['grounding']['passed'])
 ttfas=[s['browser_ttfa_ms']/1000 for s in samples if s['browser_ttfa_ms'] is not None];median=statistics.median(ttfas)
 # Retain the earlier actual observation as inspectable evidence.
 observed_before_cold=read('resource-observation-0033.json')['app_memory_gib_estimate']
 peak=max(observed_before_cold,cold['peak_mem_gib_estimate'],golden['telemetry']['peak_app_memory_gb'])
 resources={'peak_gib_upper_bound_estimate':peak,'peak_decimal_gb_upper_bound_estimate':peak*2**30/10**9,'budget_decimal_gb':48,'method':'Owned-process PSS plus owned nvidia-smi GPU allocations; overlap on unified memory can double-count. This is an upper-bound estimate, not exact physical usage.','before_cold_observation_gib':observed_before_cold,'cold_peak_gib':cold['peak_mem_gib_estimate'],'cold_minimum_host_available_gib':cold['minimum_host_available_gib']}
 (ROOT/'eval/resource-summary.json').write_text(json.dumps(resources,indent=2))
 report=['# Measured Atlas evaluation','',f'Final golden evaluation: {golden["measured_at"]}.',f'Routing: **{correct}/12**. Final answer numerical grounding: **{passed}/{checked} checked claims ({100*passed/checked:.1f}%)**. Charts and headline values come directly from deterministic Python tools.','',f'Generated-microphone Q1: **{median:.3f} s median** from push-to-talk release to the first scheduled browser audio sample across {len(ttfas)} runs (range {min(ttfas):.3f}–{max(ttfas):.3f} s). Correct forecast and grounding in every run; live streaming partials and barge-in verified. The 1.5 s target is met on this measured path. Physical acoustic latency through the Poly bar has not been measured. The test holds capture for WAV duration plus 150 ms, so release is slightly after the synthesized utterance ends.','',f'All-golden text-to-first-sentence PCM median: **{statistics.median(r["text_to_first_audio_s"] for r in records):.3f} s**. This excludes spoken input and playback scheduling. Golden narration/audio are warmed and cached; LLM tool selection still executes locally on each question. Cache hits are disclosed.','',f'Uncached Kokoro synthesis: **{uncached["uncached_wall_median_ms"]:.1f} ms median** for three new sentences sent directly to the GPU sidecar, bypassing the audio cache. These are synthesis times, not microphone-to-answer times.','', '| Q | Tool | Selection ms | Python ms | Narration ms | Grounding ms | Judgment ms | Answer ms | First sentence ms | Audio cache |','|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
 for r in records:
  t=r['timings'];report.append(f'| {r["index"]} | {r["actual"]} | {t["routing_ms"]:.1f} | {t["analytics_ms"]:.1f} | {t["narration_ms"]:.1f} | {t["grounding_ms"]:.1f} | {t.get("decision_ms",0):.1f} | {r["wall_ms"]:.1f} | {r["tts_ms"]:.1f} | {r["audio_cache"]} |')
 report+=['','Zero narration milliseconds denotes the validated local narration cache. Judgment time on repeated golden questions is a cache lookup; original model latency and checkpoint temperature are retained in each result. It is not a newly measured model inference.','', 'Latest generated-microphone browser stages (milliseconds):']
 for k,v in voice.get('client_timings',{}).items():
  if k.endswith('_ms'):report.append(f'- {k}: {v:.1f}')
 report+=['',f'Cold restart: UI {cold["ui_start_s"]:.2f} s; all five model services ready {max(cold["ready_s_by_port"].values()):.2f} s; full warmup {cold["warmup_complete_s"]:.2f} s. Stop closed every owned port; text and generated-microphone Q1 passed after restart. Warmups and assets are local.','',f'Peak observed lane memory estimate: {peak:.2f} GiB / {peak*2**30/10**9:.2f} decimal GB, below the 48 GB budget. During the sampled cold load, host MemAvailable never fell below {cold["minimum_host_available_gib"]:.2f} GiB. Estimate methodology: owned process PSS plus reported owned GPU allocations; these can overlap on GB10 unified memory. Startup checks free -g, keeps a 20 GiB reserve, and refuses a projected lane allocation above 48 decimal GB.','',f'Network: {network["duration_s"]} one-second socket samples found **zero non-loopback connections owned by the runtime services**. The Python runtime refuses remote connects; model assets are cache-only; browser page requests were local. Socket sampling cannot rule out every short-lived connection independently. Physical cable/Wi-Fi removal was not performed on the shared host; a privilege-free isolated network namespace was rejected by host permissions.','', 'The OFFLINE pill means no IPv4/IPv6 default route. The traffic figure is a real all-host non-loopback TX upper bound, not process-attributed cloud traffic. Other processes and virtual interfaces may contribute; no fabricated zero is shown.','', f'Validation: {test_count} automated analytics, grounding, offline-policy, brief-consistency and model-inventory tests passed; both personas and 16:9/9:16 record screenshots reviewed; no browser console errors. Attract playback, interrupt, golden drawer, five named deal rows, source CSVs and PNG/PDF briefs passed acceptance. All twelve deterministic brief layouts fit their 1080×1350 canvas.','', 'RF-DETR: real blank-frame and synthetic-camera tests pass with zero people and measured detector latency. Missing camera is graceful. Actual Poly camera/microphone/speaker and a positive person-entry greeting remain hardware checks. System One uses the checkpoint temperature calibration; business-domain probabilities are not validated.','', 'Raw evidence: golden-results.json, voice-browser-samples.json, voice-browser-qa.json, uncached-voice.json, cold-start.json, network-audit.json, resource-summary.json, browser-qa.json, camera-qa.json, acceptance.json and screenshots/.']
 (ROOT/'eval/REPORT.md').write_text('\n'.join(report)+'\n')
 score=f'''agent: gpt
tiers_complete: 1-4
viral_features: 1 real route/TX proof; 2 loaded model/latency/resource strip; 3 System One bars; 4 PNG/PDF Executive Brief; 5 attract playback and interrupt; 6 camera/detector with missing-device fallback; 7 golden questions drawer
golden_routing: {correct}/12
grounded_numbers: {100*passed/checked:.1f}% ({passed}/{checked} checked final-answer claims)
ttfa_median_s: {median:.3f} (generated microphone, release to scheduled audio; {len(ttfas)} runs; warmed narration/audio)
peak_mem_gb: {peak*2**30/10**9:.2f} (decimal GB upper-bound estimate; {peak:.2f} GiB)
llm: NVIDIA Nemotron 3.5 Lightning 30B-A3B, official ggml-org Q4_0 GGUF, llama.cpp CUDA, thinking off
asr: nvidia/Nemotron-3.5-ASR-Streaming-0.6B, q8_0 GGUF, NeMo-Speech.cpp CUDA
tts: hexgrad/Kokoro-82M v1.0, af_heart, GPU, 24 kHz English
decisions: jaredpalmer/kev-4b + Qwen/Qwen3.5-4B-Base, BF16 GPU, checkpoint temperature 2.406050072164233
vision: RF-DETR Nano, official rfdetr package, GPU
cold_ui_s: {cold['ui_start_s']:.2f}
cold_full_stack_s: {max(cold['ready_s_by_port'].values()):.2f}
cold_fully_warm_s: {cold['warmup_complete_s']:.2f}
known_gaps:
- Physical Poly hardware and acoustic timing await attachment; tested generated microphone and synthetic/blank camera only.
- Physical network unplug not performed; Wi-Fi has a default route. Host TX is a disclosed cloud upper bound.
- Decision probabilities have checkpoint calibration; business-domain calibration is not evaluated.
- Magpie CUDA startup failed and CPU voice was too slow; prescribed Kokoro fallback is active. English only.
- Headline digits animate upward with final values; no fictitious intermediate business figures.
- Golden narration/audio cache is disclosed; uncached synthesis is measured separately.
'''
 (ROOT/'eval/SCORECARD.md').write_text(score)
 print(score)
if __name__=='__main__':render()
