# GB10 Gate 1: blocked

Measured on 2026-11-09. Gate 0 passed. Gate 1 still fails global zero-swap acceptance. Stage UI, backups, rehearsal proof and P1 have not started. All owned runtime components are stopped and the GPU is free while an owner-only prerequisite is pending.

Base: `origin/customer_skin` at `369ba6d4cb0f02a9a5fc6925197bb8df4a0dcb65`; `v3.1.0` was absent at the initial fetch. Branch: `nano_exec`. Main, tags and Fury hardware remain untouched.

## Latest actual candidate

| Lane | Model and placement | License |
|---|---|---|
| Lead | gpt-oss-120b MXFP4, direct I/O, 16k per slot, 2 slots | Apache-2.0 |
| Worker and vision | Qwen3.6-35B-A3B UD-Q4_K_XL, F16 projector, direct I/O, 16k per slot, 3 slots | Apache-2.0 |
| Image | FLUX.2 klein 4B, BF16 transformer, FP8 E4M3 encoder weights, full original encoder retained | Apache-2.0 |
| Voice | Kokoro 82M v1.0, CPU, same weights and voices | Apache-2.0 |

Revisions and SHA256 values are in [ASSET-MANIFEST.md](../ASSET-MANIFEST.md), `config/model-files.json` and `config/gb10-build.json`. llama.cpp is MIT and TorchAO is BSD-3-Clause. No model substitution. CPU prompt snapshots are disabled; batch size is 512 and microbatch size is 128. Native per-slot GPU KV reuse remains enabled.

The owner resumed execution after the previous stop report. A concrete diagnosis found a large duplicate clean weight cache during buffered loading. The buffered lead comparison raised free RAM from 2.40 to 56.22 GiB after a read-only per-file advisory, retaining the resident model. Direct I/O avoids creating that cache during native upload; the pinned source's fallback warning was checked and neither native server fell back to buffered I/O. The per-file advisory is limited to pinned regular GB10 weight files after upload. It neither writes files nor changes global cache, swap or kernel settings.

All five model/gateway processes ran in an unprivileged transient user scope with `MemorySwapMax=0`. Membership and zero scope swap were checked each run. Global swap stayed enabled and its counters were monitored without excluding background activity.

## Actual isolated measurements

| Lane | Load seconds | MemAvailable drop GiB | Decode tokens/s at 1k / 8k |
|---|---:|---:|---:|
| lead | 14.73 | 61.775 | 54.42 / 51.32 |
| text | 6.98 | 24.050 | 63.69 / 62.08 |
| image | 10.74 | 15.554 | n/a / n/a |
| voice | 4.77 | 1.854 | n/a / n/a |

Default and non-mmap comparisons are retained in [gb10_memory_plan.json](gb10_memory_plan.json), along with prefill, TTFT, image batches and voice timings. Direct I/O is the new measured loading candidate. Q8 was measured first, then Q6 and Q4. Larger quants were rejected by the summed residency check before unsafe simultaneous loading. All three extracted every whiteboard action/owner/date and chart cell correctly. The direct-I/O Q4 candidate passed both exact vision checks again and GPT-oss passed native tool calling.

The image adapter retains the complete original text encoder and skips only its unused vocabulary projection. A real encoder test found exact hidden states 9, 18 and 27 and identical fixed-seed 1344×768 pixels, reducing peak CUDA allocation by 1.36 GiB. See [gb10_encoder_equivalence.json](gb10_encoder_equivalence.json). Reproduce with `.model-venv/bin/python ops/acceptance/gb10-encoder.py` only when every other model lane is stopped. Image equivalence is not stage acceptance.

## Complete live workload candidate

Two full S1/S2/S3 warm passes preceded five measured Agents and five measured Rushes. The native Agent produced the five-slide briefing, English and Spanish emails, and cover image. Every Rush completed six real jobs, including a model-written calculator with four browser functional checks, exact chart extraction and Spanish/Japanese translation. Audio was off, so the sixth job was the specified summary; Kokoro remained resident and had been measured separately.

| Measurement | Actual | Requirement |
|---|---:|---:|
| Agent p50 / p95 | 37.99 / 39.53 s | p95 at most 75 s |
| Rush p50 / p95 / max | 47.74 / 51.99 / 52.22 s | maximum 60 s |
| Minimum MemAvailable during Rush | 12.394 GiB | at least 10 GiB |
| Completed Rush jobs | 6 of 6 in all 5 runs | 6 of 6 |
| Lanes resident | all original process identities retained | all model lanes resident |
| OOM | none | none |
| Runtime scope swap | 0 bytes each run | 0 |
| Global swap-outs, loading and all workloads | 0 pages | 0 during Rush |
| Global swap-ins during Rush | 3, 19, 0, 12, 1 pages | 0 in every Rush |

| Rush | Seconds | Minimum available GiB | Aggregate output tokens/s | Global swap input / output pages |
|---|---:|---:|---:|---:|
| 1 | 47.74 | 12.433 | 62.69 | 3 / 0 |
| 2 | 52.22 | 12.394 | 56.47 | 19 / 0 |
| 3 | 46.58 | 12.405 | 63.89 | 0 / 0 |
| 4 | 51.09 | 12.422 | 57.86 | 12 / 0 |
| 5 | 46.33 | 12.410 | 63.65 | 1 / 0 |

**Gate 1 fails on global swap input.** The trial began with about 511 MiB already swapped from earlier activity. Zero swap-outs were measured during every component load and throughout both warm passes and all measured jobs, so the current trial did not create new swapped pages. It still fails the required global criterion. The zero-swap scope does not override that failure. No measurements have been relabelled as passes.

Earlier failed candidates, allocator failures and cache investigations remain in the JSON history. An earlier driver applied the 10 GiB floor to the entire cold show; it now evaluates the specified measured-Rush floor, with unit regressions. This does not waive the zero-swap rule.

## Required owner step and next measurement

All five owned components are stopped through the verified controller, the GPU is free, and about 118 GiB is available. Sudo requires the owner's password. The owner was asked to clear old swapped pages and immediately restore enabled swap:

```bash
sudo swapoff /swap.img
sudo swapon /swap.img
```

No model work restarts while that step is pending. Both commands must complete, followed by verification that swap is enabled and empty. The same direct-I/O candidate can then be measured again with global swap enabled, unchanged thresholds and no background-page exclusions. This is a clean baseline prerequisite, not an acceptance bypass. No privileged command was run by the agent.

Stage UI, recordings, ten-show proof, offline shows, chaos, 45 minute idle proof, screenshots, presenter PDF and show-day stage commands remain unbuilt or unperformed. Source/config tests are regression checks, not hardware acceptance.
