# Verification scope

Publication verification is recorded here after executing the candidate. Hardware acceptance is separate from ordinary repository checks. Reports containing paths, browser sessions or run records stay local rather than being published.

Historical active-deployment evidence (before packaging) recorded a clean 3743.14-second soak with ten completed four-workflow cycles, actual four-way backend overlap in every cycle, 348 grounded Atlas answers, 238 verified PPTX decks and 372 decoded images. Median/p95 short Factory build times were 355.73/464.10 seconds. This is prior same-workstation evidence, not clean-install or cross-device evidence. The complete-travel workflow was extended afterward; its frontend foundation is explicitly supplied.

Current candidate and published-delivery results are appended below. No other OS, smaller GPU, remote physical device, fresh GPU driver/toolkit installation or indefinite-duration reliability is claimed.

Secret scanning: `bash ops/scan-secrets.sh` downloads checksum-pinned Gitleaks 8.30.1, scans the explicit publication files and all local Git history when available. Public demonstration idempotency fixtures have narrow inline false-positive annotations; no real credential is allowlisted.

Ordinary source checks: `python3 ops/check-source.py`; after installing pinned app dependencies, `bash ops/test-source.sh`. Browser/sandbox fixtures may require Playwright Chromium and bubblewrap. They test fault contracts and do not prove actual model generation.

Hardware checks: `./launch.sh`, `.venv/bin/python ops/acceptance/showcase.py --wait-idle`, the complete-travel commands in docs/TRAVEL.md, the supplier/prospecting browser scripts, actual PNG/PPTX decoding, and identity-checked lifecycle/repeated-launch checks. These create test-owned fictional data and local reports. Never run disruptive lifecycle checks during another user's work.

## Publication candidate — 2026-10-30

An explicit release archive was extracted into a separate directory with **no Git metadata**, an empty home/configuration directory, fresh Python/tool/browser environments, independent caches and independent model downloads. Both setup passes retrieved all 193.91 GiB of selected Hugging Face files from the official pinned sources and verified their upstream hashes without publisher credentials. The clean test shared this workstation's existing OS, GPU driver, CUDA toolkit and system prerequisites; it was not a fresh OS or another physical machine.

The first empty-cache engine launch took approximately **38 minutes 41 seconds** (Qwen alone 296.44 seconds). FlashInfer/DeepGEMM compilation and NVIDIA kernel downloads explain the difference from historical cached starts. One preparatory controller wait was resumed with a longer bounded cold-start timeout; the existing two model sessions retained their identities and were not duplicated. The published controller allows up to 60 minutes for cold lead initialization and handles its verified nested compiler groups. Actual cold compiler ancestry/cache/executable ownership was checked read-only; unknown ownership remains a refusal.

The original 176 GiB lead allocation passed functional four-way browser acceptance but fell to **4211 MiB free GPU memory** after cold initialization, below the historical 10 GiB target. The public allocation is therefore **168 GiB nominal DeepSeek / 32 GiB nominal Qwen**. Model revisions, quantization, 16K lead context, 65K Qwen engine context, 32K specialist task context, serving slots and gateway admission limits are unchanged. The revised lead provided 10.44 GiB KV cache / 27261 tokens; its physical concurrency remains one. The following measurements use the public allocation.

| Real workflow | Submission to verified output |
|---|---:|
| Atlas, typed question matched and actual local-model grounding verified | 1.22 s |
| Three-slide booth deck, rendered preview and real PPTX | 6.69 s |
| Generated/displayed/decoded FLUX image | 0.74 s |
| Newly generated short travel frontend/backend, booking/persistence/conflict/filter/sort/navigation checks | 311.88 s |

That cycle passed with measured backend overlap and **13451 MiB minimum sampled free HBM**. An additional Atlas/deck/image cycle while complete-travel development was actively generating also passed, with actual four-way backend overlap of 0.389 seconds and **10823 MiB minimum sampled free HBM**. These are bounded samples on this host, not an indefinite-memory or cross-machine guarantee.

The final fresh **complete-travel** build finished in **654.69 seconds**, including its own automated repairs, without coordinator fixes or manual edits to that generated project during the run. All seven product criteria passed, including 30 generated QA cases and real desktop/mobile browser acceptance. The model made 25 calls (24 complete and one failed call recovered through its bounded repair); this run used DeepSeek for backend/QA and the disclosed supplied vector frontend. Earlier retained builds also exercised real Qwen frontend repairs. A separate current-portal browser suite passed **13 end-to-end checks**: account persistence, destination/filter/sort/pagination, favorites, itinerary create/edit/delete, two-user permissions, server quotes, real demonstration reservations, invalid/duplicate requests, logout/login persistence, admin records/inventory, 375px layout, Factory preview and backend explorer.

Additional completed checks:

- **140 Factory source regressions** and **17 controller/gateway/booth fixtures** passed. These fixtures are explicitly separate from GPU acceptance.
- Two independent Atlas browser contexts created distinct valid PNG/PDF exports using the bundled fonts.
- The full React editor opened the actual generated booth project and its rendered preview. PPTXs opened with python-pptx and contained **21 editable text shapes** across three slides; saved PNGs decoded with Pillow.
- The browser exercised actual Kokoro speech (151200 PCM bytes) and CPU ASR, returning the forecast sentence correctly. Physical microphone/speaker and remote WSS/device quality remain unverified.
- An idle operator view created no inference events. Active models, accounting and resource APIs were connected through the actual UI.
- The separately labeled reference application passed independent backend checks and actual browser booking/persistence after refresh; it never served as a new Factory output.
- The candidate refused every foreign showcase listener before the controlled test window and did not adopt or signal those services.
- Explicit source-policy/syntax/checksum audit and checksum-pinned Gitleaks scan passed. No original Git history, model weights, environments, browser profiles, runtime databases, private photography or old session logs are included.

Acceptance-driven fixes are retained rather than hidden: missing host-font paths were replaced with bundled OFL fonts; retired supplier/prospecting routes were removed from live-demo claims; generated QA request-method/logout ambiguities received precise diagnostics; genuine unknown-route auth interception is now independently detected and routed to the owning sandboxed module; and duplicate travel-contract text was removed from prompts to preserve full-file repair output within the original context bound. Earlier blocked builds remain local evidence and are not counted as successful fresh builds. Generative output can still block or fail; this is a demonstration, not production acceptance for every possible generated application.

Lifecycle and published-download verification are recorded after the frozen candidate checks below. Advanced editor actions/large decks, other operating systems/GPUs, remote physical devices and a fresh driver/toolkit installation are not established by these tests.

### Frozen-candidate lifecycle

Full stop and repeated stop passed. Independent socket checks confirmed all ten service ports and the optional reference port were closed; `nvidia-smi` reported **no GPU compute processes**. Display/driver memory was left alone. The existing driver, kernel, SSH and Tailscale daemon were not replaced or stopped.

The final restart, including the updated hash-pinned NLP dependency verification, frontend rebuild/check and model readiness, completed in **630 seconds** with existing downloads/caches. Two subsequent ordinary `./launch.sh` calls preserved **all ten PIDs**, taking **3.743 and 3.664 seconds**. Post-restart real browser checks passed again: Atlas **2.73 seconds**, displayed image **7.79 seconds**, and three-slide PPTX **7.02 seconds**. The completed travel application also passed its **13 browser/API checks after the service restart**. No test-only registry, publisher credentials or original source folder was used by this installation.

Published repository/archive retrieval and identity checks are reported in the versioned GitHub release notes. The source checksum file and explicit inclusion policy let recipients repeat those comparisons locally.
