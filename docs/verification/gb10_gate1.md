# GB10 memory qualification

The current wordless artwork profile passed Gate 1 on 2026-11-10. This is real concurrent workload qualification. Native stage rehearsal acceptance is separate.

The original gpt-oss-120b MXFP4 and Qwen3.6 UD Q4_K_XL identities remain selected, with native Jinja tools, flash attention, direct I/O, 16k context per slot and two / three slots. FLUX.2 klein retains its full original FP8 text encoder weights; Kokoro is resident on CPU. Q8 and Q6 were measured first. Q4_K_M was also measured during development; Q4_K_XL remains the highest quality passing quant.

| Measurement | Actual | Required |
|---|---:|---:|
| Agent p50 / p95 | 38.913 / 41.799 s | p95 at most75 s |
| Rush p50 / p95 / maximum | 49.248 / 50.442 / 50.677 s | maximum at most60 s |
| Minimum Rush MemAvailable | 10.590 GiB | at least10 GiB |
| Rush jobs | 6 of6 in all five runs | 6 of6 |
| Global swap input / output | 0 pages | 0 during Rush |
| OOM | none | none |
| Original model identities | all resident | all resident |

Two exact S1/S2/S3 warm passes preceded five measured Agents and five measured Rushes. Every cover and all four Rush images were generated live by FLUX and reviewed locally by the pinned Qwen vision lane before publication. The calculator is still model-written HTML and JavaScript, checked against four real browser arithmetic cases with networking denied; the trusted stage supplies its layout. Removing redundant model-generated CSS corrected the earlier60.773 second timing miss. The failed trial is retained in the history.

The owner cleared old swapped pages and re-enabled swap before qualification. Global swap remained enabled, while the owned model scope had MemorySwapMax=0. Independent global counters recorded zero activity throughout this trial. No model was silently substituted and no context or slot floor was reduced.

Per-process GB10 allocator settings limit glibc arenas and use128 KiB mmap/trim thresholds. [The official allocator manual](https://sourceware.org/glibc/manual/latest/html_node/Memory-Allocation-Tunables.html) documents these controls; [actual identical-pixel load comparisons](gb10_allocator.json) record their evaluation. No system library or global setting changed. The larger Agent cover uses an8.125 GiB creative guard; Rush retains10.125 GiB, with a required actual minimum of10 GiB.

[Full measurement history](gb10_memory_plan.json), [actual image review verification](gb10_text_free_images.json) and [separate stage development attempts](gb10_stage_development.json) preserve the evidence. Stage readiness still requires current backups and successful rehearsal, offline, chaos and idle proof.
