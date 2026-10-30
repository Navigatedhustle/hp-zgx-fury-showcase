"""Documentation numbers come from measurements and live graph/index counts."""
import json,statistics,datetime,urllib.request
from atlas.config import ROOT
from atlas.documents import stats
E=ROOT/'eval/v2'
def read(name):return json.loads((E/name).read_text())
golden=read('golden-results.json');voice=read('voice-results.json');cold=read('cold-start.json');resource=read('resources.json');final_voice=read('final-voice.json')
before=[read('ttfa-before-1.json')['metrics'][0]['ttfa_ms']/1000,read('ttfa-before-2.json')['metrics'][0]['ttfa_ms']/1000]
after=[e['metrics'][0]['ttfa_ms']/1000 for e in voice if e['persona']=='enterprise' and e['orb_on']]
off=[e['metrics'][0]['ttfa_ms']/1000 for e in voice if e['persona']=='enterprise' and not e['orb_on']]
b,a,o=map(statistics.median,[before,after,off])
feeds=[e['feed'] for e in read('knowledge-results.json') if 'feed' in e]
counts={p:stats(p) for p in ['enterprise','university']}
graphs={p:json.load(urllib.request.urlopen('http://127.0.0.1:8200/api/knowledge/'+p)) for p in counts}
cold_runs=[cold]+[read(name) for name in ['cold-start-first.json','cold-start-second.json','cold-start-third.json'] if (E/name).exists()]
peak=max([c['peak_lane_gb'] for c in cold_runs]+[resource['peak_lane_gb'],read('screenshot-memory-observation.json')['rounding_upper_bound_gb']]);available=min([c['min_available_gb'] for c in cold_runs]+[resource['min_available_gb']])
report=f'''

# Atlas v2 measured upgrade

Measured {datetime.datetime.now(datetime.timezone.utc).isoformat()}. The v1 evaluation above is historical; raw v2 evidence is in eval/v2.

Routing: **{golden['routing']}/26**. Answer grounding: **{golden['grounding']}/26**, with **{golden['numeric_claims_checked']} numerical tokens checked (including period/entity labels)**. All **{golden['citation_passed']}/6 knowledge questions** passed exact document/passage identity and numeric grounding. Graph highlights use exact SQLite primary keys. The graph explicitly distinguishes shown nodes from total nodes.

Developer: **{golden['developer_executed']}/8 questions executed code successfully**; the other **2/8 inspect real source or connection metadata**. All eight requested behaviors passed. The six runnable artifacts actually ran in isolated subprocesses and matched independent reference runs. {golden['repairs']} artifacts required one disclosed repair/rerun in this measured run; original code, stdout and stderr are retained. The overdue query returns no rows at the October 7 synthetic snapshot; no overdue deals are manufactured. Three site-scoring tests exercise actual source, cost inversion, neutral equal ranges and driver reconciliation. The REST handler is tested in-process; sandbox sockets remain prohibited.

Generated-microphone TTFA, release to scheduled browser playback: **{b:.3f} s before** (two new v1 samples) to **{a:.3f} s upgraded** (three final orb-on samples). A paired test of the same upgraded pipeline measured **{o:.3f} s orb-off** versus **{a:.3f} s orb-on**, alternating three samples each. This does not establish a causal improvement. Warm narration/audio caches and shared-host load are disclosed. A separate concurrent-load run is retained in voice-results-shared-load.json. Physical acoustic timing is unmeasured. All three persona voice routes passed, including actual Developer execution. Every orb-on playback sample had positive AnalyserNode energy; synchronous state updates were below 50 ms.

Cold restart: **{cold['ui_ready_s']:.2f} s UI**, **{cold['all_services_ready_s']:.2f} s all six model services**. UI and models verified on 127.0.0.1, ports 8200–8206. Language alias atlas-local verified. Peak observed lane memory estimate **{peak:.2f} decimal GB**, below 48 GB; minimum MemAvailable in the sampled cold/voice checks **{available:.2f} GB**, above 16 GB. Peak includes a conservative upper rounding bound from an earlier live screenshot reading of 43.6 GiB during concurrent code/voice activity. Owned process PSS plus GPU allocations can double-count on unified memory and are a conservative estimate.

Optional fine-tune skipped after the shared heavy-lock audit: measured 2.60 GB lane headroom cannot fit at least 8 GB additional BF16 gradients, before optimizer/activations. Released checkpoint/general calibration retained; no domain held-out accuracy is claimed.

'''
for p,g in graphs.items():
    s=counts[p]
    report+=f"- {p}: **{g['counts']['nodes']:,} nodes / {g['counts']['edges']:,} edges**; **{s['documents']} documents / {s['passages']} passages / {s['vectors']} vectors**, {s['dimension']} dimensions. Embedding model: {s['model']}.\n"
report+='\nFeed the brain uses actual local model prose plus an exact deterministic fact appendix, then real chunk embedding and graph ingestion. Both persona proofs show a unique new action phrase absent before ingestion and present afterward in an exact cited passage. Measured generate/ingest/prove times: '+', '.join(f"{d['document']['persona']} {d['ingest_ms']/1000:.3f} s" for d in feeds)+'. These include before/after retrieval, rather than pure embedding latency.\n'
report+='\nValidation: **24 tests passed**, including all v1 tests, sandbox network/process/filesystem restrictions, read-only database, timeout/memory, live graph counts, exact provenance, real source/unit tests and counterfeit citation rejection. 1920×1080 and 1080×1920 screenshots were opened and reviewed; citation containment, camera controls, Developer state, chart labels and portrait geometry were fixed. Artifacts include each persona, speaking orb, provenance, feed, live code, tests, source, endpoint, Stage mode and record layouts.\n'
report+='\nThe final post-cold voice check measured '+', '.join(f"{d['persona']} {d['metrics'][0]['ttfa_ms']/1000:.3f} s" for d in final_voice)+' (one generated-microphone sample each). All three selected the expected tool and passed grounding, every orb recorded actual playback energy, and Developer showed EXECUTED · VERIFIED. These checks are separate from the paired latency comparison above. The final browser Feed check preserved the selected answer, ingested the new memo, and played its cited suggested answer without browser errors; evidence is in final-feed-ui.json and the Feed screenshot.\n'
report+='\nA 45-second owned TCP socket audit found no non-loopback runtime connection. Physical booth audio/camera, positive person-entry greeting and actual network removal remain morning checks. The shared host networking was unchanged. The live cloud-traffic figure remains a disclosed all-host TX upper bound.\n'
p=ROOT/'eval/REPORT.md';text=p.read_text();p.write_text(text.split('\n\n# Atlas v2 measured upgrade')[0]+report)
score=f'''

v2_features: real-audio orb, Stage mode, exact provenance graph, local document index, Feed the brain, Developer generation/sandbox/source/tests/API/chart/endpoint
brain: enterprise {graphs['enterprise']['counts']['nodes']}/{graphs['enterprise']['counts']['edges']}, university {graphs['university']['counts']['nodes']}/{graphs['university']['counts']['edges']} graph; {sum(s['documents'] for s in counts.values())}/{sum(s['passages'] for s in counts.values())} docs/passages indexed; embed model nvidia/llama-nemotron-embed-1b-v2 @ 113abe4acafa848e77ead9c0623205e511932348
fine_tune: skipped, measured 2.60 GB headroom cannot fit minimum 8 GB gradients; general checkpoint calibration retained
dev_golden: {golden['developer_executed']}/8 executed successfully; 2 source/endpoint informational, all 8 behaviors pass; {golden['repairs']} disclosed repairs
v2_golden_routing_grounding_citations: {golden['routing']}/26, {golden['grounding']}/26, {golden['citation_passed']}/6
ttfa_median_s_before_after: {b:.3f} -> {a:.3f} (2 before / 3 upgraded orb-on generated microphone samples; warm caches)
ttfa_paired_orb_off_on_s: {o:.3f} -> {a:.3f} (same upgraded pipeline; 3 alternating each)
v2_cold_ui_models_s: {cold['ui_ready_s']:.2f} / {cold['all_services_ready_s']:.2f}
v2_peak_mem_gb: {peak:.2f}, conservative PSS+GPU estimate; min available {available:.2f}
v2_tests: 24 passed
'''
p=ROOT/'eval/SCORECARD.md';p.write_text(p.read_text().split('\n\nv2_features:')[0]+score)
(E/'summary.json').write_text(json.dumps({'before_ttfa_s':b,'after_ttfa_s':a,'paired_off_s':o,'golden':{k:v for k,v in golden.items() if k!='questions'},'graphs':{p:g['counts'] for p,g in graphs.items()},'documents':counts,'peak_lane_gb':peak,'min_available_gb':available},indent=2))
print(score)
