# GB10 Gate 1: blocked

Measured on the GB10 Nano on 2026-11-08 local time. This is qualification evidence, not stage readiness. Gate 0 passed. Phase 2 and P1 have not started.

Base: `origin/customer_skin` at `369ba6d4cb0f02a9a5fc6925197bb8df4a0dcb65`; `v3.1.0` was absent at initial fetch. Work is isolated on `nano_exec`.

## Model stack

| Lane | Model and quant | License |
|---|---|---|
| Lead | gpt-oss-120b MXFP4 | Apache-2.0 |
| Worker and vision | Qwen3.6-35B-A3B UD-Q4_K_XL with F16 projector | Apache-2.0 |
| Image | FLUX.2 klein 4B, BF16 transformer and FP8 E4M3 text encoder weights | Apache-2.0 |
| Voice | Kokoro 82M v1.0 | Apache-2.0 |

Immutable revisions and SHA256 values are in [ASSET-MANIFEST.md](../ASSET-MANIFEST.md), `config/model-files.json` and `config/gb10-build.json`. llama.cpp is MIT; TorchAO is BSD-3-Clause. No headline model was dropped or substituted.

## Actual isolated measurements

| Lane and final loading | Load seconds | MemAvailable drop GiB | Decode tokens/s at 1k / 8k |
|---|---:|---:|---:|
| lead / no-mmap | 56.22 | 61.668 | 55.26 / 51.90 |
| text / mmap | 21.33 | 24.137 | 66.89 / 64.12 |
| image / BF16/FP8 text encoder | 6.90 | 14.479 | not applicable |
| voice / publisher v1.0 | 4.73 | 3.523 | not applicable |

Q8 and Q6 were measured and rejected by the summed residency admission check before unsafe simultaneous loading. Both vision samples passed for every measured Qwen quant. Contexts are already at the requested floor: 16k per slot, two lead slots and three worker slots.

## Completed five-run candidate, before the final cache cap

| Measurement | Actual result | Required |
|---|---:|---:|
| Agent p50 / p95 | 44.85 / 45.07 s | p95 at most75s |
| Rush p50 / p95 / maximum | 33.33 / 34.69 / 34.87 s | maximum60s |
| Minimum MemAvailable during Rush | 11.293 GiB | at least10GiB |
| Completed Rush jobs | 6 of6 in all five runs | 6 of6 |
| Lanes resident | all five processes retained their verified identities | all model lanes resident |
| Swap input pages | 280, 77, 167, 38, 121 | zero |
| Swap output pages | zero in every measured Rush | zero |

That candidate failed. The zero-swap requirement was not waived. A separate60second idle investigation found317 global swap input pages correlated with major faults in build agents and existing host daemons. No model process faults were observed in that idle test; this does not establish attribution for every prior Rush page.

## Latest bounded-cache candidate

Pinned upstream defaulted to8192MiB additional CPU prompt cache per server. GB10 now explicitly caps it at256MiB each, preserving the required contexts, slots and native KV reuse. This was a concrete configuration correction after the failed series.

The unattended remeasurement retained the source fixes for a strict chart table shape and complete Japanese translation. Ordinary English left in a Japanese draft triggers one visible, logged retry. The generated calculator passed four real browser input/output checks in its opaque network-blocked iframe.

| Latest warm-up | Seconds | Minimum MemAvailable GiB |
|---|---:|---:|
| S1 complete | 39.67 | 11.237 |
| S2 complete | 6.24 | 14.751 |
| S3 complete | 43.29 | 10.351 |
| S1 failed | 17.05 | 11.092 |

The second Agent warm-up failed in FLUX text encoder dequantization. PyTorch rejected a742MiB allocation against a15.10GiB per-process allowance with14.90GiB allocated. MemAvailable remained above11GiB. This is an allocator OOM failure even though the kernel OOM-kill counter did not increase. No final five-run acceptance exists for this configuration.

## Next options requiring a resumed qualification

1. Correct the GB10 allocator allowance to use the same10.125GiB safety threshold as its checkpoint, then repeat every required live measurement. The required10GiB acceptance floor remains unchanged. A proposed patch is retained outside the repository for owner review; it has not been applied or accepted.
2. Evaluate device-native FP8 text encoder matrix multiplication to avoid the742MiB BF16 dequantization temporary, then repeat quality, residency and workload measurements. This preserves the headline model and all four resident lanes.

Hardware retries are stopped under the requested repeated-failure rule. Stage UI, recordings, ten-show proof, offline shows, chaos,45minute idle proof, screenshots and presenter handoff remain unbuilt or unperformed. Existing source/config tests are useful regression checks only, not hardware acceptance.
