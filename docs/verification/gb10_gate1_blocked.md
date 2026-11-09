# GB10 Gate 1: blocked

Measured on 2026-11-09. Gate 0 passed. Gate 1 failed, and hardware retries stopped under the owner's repeated-failure rule. Phase 2, P1 and stage readiness are not claimed.

Base: `origin/customer_skin` at `369ba6d4cb0f02a9a5fc6925197bb8df4a0dcb65`; `v3.1.0` was absent at the initial fetch. Branch: `nano_exec`. Main, tags and Fury hardware remain untouched.

## Latest actual candidate

| Lane | Model and placement | License |
|---|---|---|
| Lead | gpt-oss-120b MXFP4, no mmap, 16k per slot, 2 slots | Apache-2.0 |
| Worker and vision | Qwen3.6-35B-A3B UD-Q4_K_XL, F16 projector, no mmap, 16k per slot, 3 slots | Apache-2.0 |
| Image | FLUX.2 klein 4B, BF16 transformer, FP8 E4M3 encoder weights, full original encoder retained | Apache-2.0 |
| Voice | Kokoro 82M v1.0, CPU, same weights and voices | Apache-2.0 |

Revisions and SHA256 values are in [ASSET-MANIFEST.md](../ASSET-MANIFEST.md), `config/model-files.json` and `config/gb10-build.json`. llama.cpp is MIT and TorchAO is BSD-3-Clause. No model substitution. CPU prompt snapshots are disabled, with batch size 512 and microbatch size 128; native per-slot GPU KV reuse remains enabled.

All five owned model/gateway processes ran in an unprivileged transient user scope with `MemorySwapMax=0`. Membership and zero scope swap were checked each run. Global swap stayed enabled and its counters were monitored without subtracting background activity. No global swap, kernel, boot service, driver or network configuration was changed by the agent.

## Isolated measurements used for admission

| Lane | Load seconds | MemAvailable drop GiB | Decode tokens/s at 1k / 8k |
|---|---:|---:|---:|
| lead | 55.72 | 61.145 | 54.50 / 50.76 |
| text | 21.64 | 23.991 | 63.55 / 61.28 |
| image | 7.09 | 15.275 | n/a / n/a |
| voice | 4.77 | 1.854 | n/a / n/a |

Q8 was measured first, then Q6 and Q4. Both larger Qwen quants were rejected by the summed residency check before unsafe simultaneous loading. All three correctly extracted every whiteboard owner/date/action and chart cell. Full prefill, TTFT, loading comparisons, image batches and voice timings remain in [gb10_memory_plan.json](gb10_memory_plan.json).

The image adapter skips the unused language vocabulary projection while retaining the complete original encoder weights. A real pinned encoder test found exact equality of hidden states 9, 18 and 27 and identical pixels for the same seed at 1344×768. CUDA peak allocation fell by 1.36 GiB. See [gb10_encoder_equivalence.json](gb10_encoder_equivalence.json); reproduction: `.model-venv/bin/python ops/acceptance/gb10-encoder.py` with every other model lane stopped. This is image equivalence evidence, not stage acceptance.

## Five actual Agent runs and five actual Rushes

Two complete S1/S2/S3 warm passes preceded the measured runs. The native Agent produced the five-slide briefing, English email, Spanish email and image. Each Rush ran six actual jobs including the model-written calculator with four browser functional checks, exact chart extraction and Spanish/Japanese translation. Audio was off, so the sixth job was the specified summary; Kokoro remained resident and had been tested separately.

| Measurement | Actual | Requirement |
|---|---:|---:|
| Agent p50 / p95 | 43.41 / 44.90 s | p95 at most 75 s |
| Rush p50 / p95 / max | 48.68 / 52.11 / 52.18 s | max 60 s |
| Rush minimum MemAvailable | 10.566 GiB | at least 10 GiB |
| Rush peak OS memory used | 111.061 GiB of 121.627 GiB | measured, not GPU memory |
| Rush jobs completed | 6 of 6 in all 5 runs | 6 of 6 |
| Model residency | all original process identities retained | all resident |
| OOM | none | none |
| Runtime scope swap used | 0 bytes each run | 0 |
| Global swap activity | nonzero input in all 5 runs | zero input and output |

| Rush | Seconds | Minimum available GiB | Aggregate output tokens/s | Swap input / output pages |
|---|---:|---:|---:|---:|
| 1 | 48.68 | 10.621 | 61.48 | 132 / 0 |
| 2 | 52.18 | 10.603 | 57.30 | 108 / 0 |
| 3 | 46.29 | 10.589 | 63.71 | 102 / 0 |
| 4 | 51.83 | 10.617 | 56.89 | 51 / 0 |
| 5 | 46.72 | 10.566 | 63.69 | 52 / 0 |

**Gate 1 fails on global swap input.** The first cold Agent warm-up also reached 9.202 GiB available and is reported without alteration. The specified 10 GiB memory gate applies to the measured Rushes. An earlier driver mistakenly applied that floor to the entire cold show; the source now evaluates the requested Rush rule, with unit regressions. Reassessing these unchanged measurements still fails because of global swap. It does not convert this run into a pass.

## Failure history and limits

Earlier candidates and all failed attempts remain in the JSON report. Fixes addressed real allocator limits, CPU prompt snapshot growth and unnecessary image encoder projection. The latest candidate completed every required job without those failures.

A prior separate 60 second idle diagnostic correlated 317 global swap input pages with major faults in build agents and existing host daemons, with no model faults observed. That does not attribute every page in the latest Rushes. The build does not claim that background swap can be excluded.

All five owned model/gateway components have been stopped through the verified controller; the GPU is free. No unknown processes were signalled. Stage UI, backups, ten-show proof, three offline shows, chaos, 45 minute idle proof, screenshots, presenter PDF and show-day launch commands remain unbuilt or unperformed. Unit tests are not hardware acceptance.

## Options before another qualification

1. Repeat from the Nano's local terminal after the build agent and unrelated interactive applications have exited. Prior attribution makes this a plausible diagnostic, not a guaranteed fix. Do not disable global swap or change the zero-swap rule.
2. Investigate clean weight-file page cache after GPU upload, using a per-file advisory only on this runtime's own model files. This is unimplemented and unmeasured; it would need an isolated comparison before another full trial.
3. Investigate native FP8 encoder matrix multiplication to reduce temporary BF16 dequantization memory further, preserving all four models and the contexts/slots. This is also unimplemented and would require equivalence and full workload measurements.

The repeated-failure stop is in force. No further hardware retry starts automatically, and Phase 2 cannot begin on these measurements.
