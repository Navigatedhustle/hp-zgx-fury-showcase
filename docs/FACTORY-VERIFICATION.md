# Agent Factory v2.1.0 verification

The strict qualifying soak passed **44.10 minutes**, **4 cycles** and **689 real workflow results**, with measured four-way backend execution overlap in every cycle. These are actual local model/pipeline executions, not recorded playback. The machine-readable [allowlisted evidence summary](verification/factory-v2.1.0.json) contains measurements without private prompts, sessions or host addresses.

## Real Live builds

| Project | Job elapsed | First checked preview | Input tokens | Output tokens | Requests |
|---|---:|---:|---:|---:|---:|
| complete travel | 401.16s | 386.02s | 97,056 | 30,863 | 13 |
| editorial short | 320.37s | 155.46s | 96,953 | 33,929 | 15 |
| short travel | 314.17s | 142.37s | 94,903 | 34,117 | 15 |
| complete travel | 1380.01s | 1365.18s | 317,808 | 113,642 | 50 |

Job elapsed includes waiting and tools. Browser-verified latency additionally includes interaction checks. Token totals use this run's unique endpoint usage records, including real failed/repair attempts. No fixed token threshold controls preview readiness: backend/API and generated QA checks plus browser bootstrap gate the first travel preview; full browser and persistence acceptance gate Ready.

## Reliability and presentation

- 155 Factory regressions and 19 core/controller/gateway/booth checks passed. Native button/tab navigation is now tested alongside anchors; broken navigation remains rejected.
- Backend integration must start in the real sandbox before merging. Rejected syntax is supplied to its retry without publishing it; QA import/discovery failures return to repair. Travel QA has an 8192-token ceiling bounded further by exact serving-context headroom; other lead tickets retain 6000. There is no cumulative run token cutoff.
- Real Live cancellation/rerun released the correct job and gateway resources. A real failed travel job resumed from its ten merged tasks, completed seven further calls, and passed independent acceptance plus 13 portal checks. This recovery is separate from fresh qualifying runs above.
- Ownership, busy/duplicate responses, disconnect/reconnect, retained preview interactions, explicit version selection and final usage/elapsed persistence across an actual Factory service restart passed.
- Two final guided playbacks completed with synchronized recorded events/usage and working artifacts. Thirteen browser/API checks cover authentication, saved trips, itineraries, quotes/reservations, persistence, two-user isolation, admin records/inventory, mobile layout and Factory backend inspection. Four recordings were admitted; a fifth received 429.
- Six desktop/mobile light/dark states passed automated WCAG A/AA checks with no reported violations or overflow. Keyboard skip access and reduced motion were exercised. This is scoped automation, not independent conformance certification.
- Actual private HTTPS pages, cookie attributes, SSE reconnect, preview search and downloads passed using a browser-only resolver mapping on this host. Physical Colorado client/DNS/audio quality remains a site acceptance step.

## Measured operating envelope

The soak completed 253 Atlas results, 165 editable three-slide decks, 267 decoded generated PNGs and 4 Live builds. Generated decks had at least 21 editable text shapes. Browser exceptions: 0. Network aborts were {'net::ERR_ABORTED': 501}; these are the expected superseded/closed Atlas streams, distinguished from genuine failures.

Minimum directly sampled free HBM was **9810 MiB** on the 256703 MiB GB300. Model engines stayed resident; kernel/cache warmup can increase allocation. RSS and host disk deltas are in the JSON summary and include retained outputs/cache activity; no zero-growth or unlimited-load claim is made.

One Live Factory build is admitted globally; extra visitors receive a clear busy response. Short builds allow at most two development requests; travel tickets run sequentially. The gateway admits four upstream requests, at most three ordinary admissions with an Atlas reserve; DeepSeek serves one sequence and Qwen up to four. Guided playback has its separate four-run bound. These results do not establish unlimited users, larger contexts/decks or multiple Live Factory builds.

## Models, installation and preservation

Verified serving checkpoints: nvidia/DeepSeek-V4-Flash-NVFP4 at e3cd60e7de98e9867116860d522499a728de1cf9 (alias fury-lead, context 16384) and unsloth/Qwen3.6-27B-NVFP4 at ccdaab7e68af2409599b8949a8f2685703c9bae5 (context 65536; development tasks capped 32768). Existing FLUX.2 klein 4B, speech and all other demos remain on their original stack. No model substitution, driver/kernel change or new orchestration/database service was introduced.

The original requested tree's tracked changes were preserved; 83 retained travel source/image files matched their checkpoint. Private imagery remains on the existing deployment. Public guided artifacts explicitly substitute redistributable vector scenes and fresh fictional records.

Independent cached setup rebuilt the editor and verified the pinned model manifest; a full model-file rehash passed. Source/ZIP launch guards refused foreign services. No fresh Colorado OS/driver install, new 194 GiB transfer or new cold model boot is claimed. The exact published clone/archive comparison is reported in release notes and the publication verification asset.

During the final long travel build, an actionable SQLite SELECT-projection diagnostic was added after observing the missing email-column lookup. Acceptance criteria were unchanged; the local model repaired the generated code itself. Its 23-minute repair sequence is included above, rather than hidden behind an average. No generated application source was manually patched.

Earlier failed/interrupted attempts remain local and are excluded from the qualifying soak. Generative output can still fail checks; use the clearly recorded guided mode for predictable generalist presentations. The source and asset ZIP intentionally excludes private logs, databases, prompts, credentials, tailnet state, weights and licensed HP fonts.


## v2.1.1 repair-budget correction

A post-release travel repair exhausted a 3469-token output allowance three times while being required to return a complete 15 KB module. The underlying reservation failure also involved an upstream backend dispatcher, so rewriting the reservations module alone could not resolve it.

The controller now measures the existing complete-file JSON envelope with the active serving tokenizer, including its chat template. It reserves output headroom and selects bounded localized exact edits when a complete replacement cannot safely fit. An unexpected length termination forces the next request for that ticket to use localized edits. Incomplete, ambiguous and unchanged patches never merge; safe redundant no-op fragments are ignored when the patch contains a real edit. Reference-file edits trigger a separately scoped owner repair, with dependency depth and cycle checks. Full independent acceptance follows every repair pass. The backend integration gate also checks the declared two-argument module dispatch interface before merging.

Generated QA now supplies the actual rejected API status/reason and selected non-secret inputs; reservation diagnostics include the real listing capacity. This exposed a test attempting three guests in a two-person listing. The model corrected the fixture while preserving reservation success, duplicate conflict and cross-user ownership assertions. Credentials and authorization headers are omitted.

The original blocked run was retained and resumed with real local inference. It finished with all six backend checks, all 15 generated tests, desktop/mobile browser acceptance and persistence verification passing. A browser reconnected after a Factory-only restart, showed Application ready with checked version 2 and six functional listing cards, and reported zero page exceptions. No generated application file was manually patched.

Patch validation: 161 Factory regression tests and 19 core checks. New regressions cover the exact 3469-token limit, rejection of ambiguous or incomplete edits, scoped upstream handoff, dispatcher arity, sanitized real sandbox diagnostics and a forced protocol change after unexpected truncation. The earlier 44.10-minute soak remains the v2.1.0 baseline; it was not repeated for this patch. The serving models, admission limits, generated travel assets and recorded example remain unchanged.
