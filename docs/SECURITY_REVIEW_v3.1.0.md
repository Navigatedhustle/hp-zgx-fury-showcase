# v3.1.0 security review

Reviewed on the documented Ubuntu 24.04 ARM64 GB300 profile in November 2026. This summary describes repaired areas and residual assumptions without reproduction or exploit instructions. Private test material, runtime records and raw findings are excluded from the repository and release.

| Finding | Severity | Area repaired |
|---|---|---|
| H-001 | Low | Short conference viewport controls and station layouts |
| H-002 | Low | Keyboard skip-link order |
| H-003 | High | Exact HTTP Host allowlists and loopback model transports |
| H-004 | High | Origin checks and JSON/CSRF mutation boundaries across applications and models |
| H-005 | Medium | Browser policies, visitor/customer caching and device permission delegation |
| H-006 | High | Bounded isolated document/logo parsers and quarantined parser output |
| H-007 | High | Generated presentation origin isolation and checked editing/palette bridges |
| H-008 | Medium | Request, connection, queue, upload, consent and sandbox storage limits |
| H-009 | Medium | PID-safe lifecycle signals and bounded model HTTP shutdown |
| H-010 | Medium | Private runtime modes, service core limits and log retention |
| H-011 | Medium | Generated JavaScript parser environment isolation |
| H-012 | Medium | Fail-closed unsupported legacy model/setup entrypoints |
| H-013 | Low | Explicit origins in Factory preview communication |
| H-014 | Medium | Immutable manifests, full SHA256 authentication and explicit verified weight reuse |
| H-015 | Medium | Bounded generated-code output capture before reading |
| H-016 | High | Safe Atlas result/artifact collection |
| H-017 | High | Atlas generated-code process namespace boundary |
| H-018 | Low | Self-contained licensed document/title export fonts |
| H-019 | Low | Bounded Vision executive brief under disclosed busy-lane routing |

Vulnerable Python and JavaScript dependencies were upgraded with compatible locked versions. The serving upgrade retains the selected model files/revisions, serving budgets, contexts and concurrency reservations. The shipped SBOMs inventory every Python lock and the frontend lock. Original advisory severities, duplicate aliases and platform applicability were retained in private audit records; false positives are not counted as repaired vulnerabilities.

## Validation

Source regressions passed: 192 Factory tests, 180 core tests and 7 Node checks, with no required-suite skips. Real-browser verification passed 98 V3 cases, 66 shell cases, 72 conference cases, six orb viewports, 90 Customer Skin layouts and 20 Chromium/Firefox fault cases. Actual model checks cover voice/ASR, isolated Atlas exports, editable slides, all five Vision tasks, document/image injection boundaries, ten-page translation, both Video input modes, three sequential Trailers and deletion/restart privacy, five active model-lane restarts, real network-loss recovery, four-way overlap, six-workflow Fury Rush and a synchronized three-browser soak exceeding 1,813 seconds.

The frozen standalone Factory baseline was 447.174 and 415.431 seconds (mean 431.302; ceiling 474.433). Qualifying post-hardening standalone builds took 306.854 and 304.962 seconds. All four trials were retained: one successful trial included incidental Atlas routing; one generated page failed unchanged navigation QA and was never counted as a successful build. First Rush Vision hit its output bound; the concise brief instruction was bounded explicitly without increasing token/model/concurrency budgets, and the new full Rush passed. Factory prompts, workflow and UX remain unchanged.

All Phase 1 scanners were rerun and reconciled. Secrets/history scans were clean; no open applicable critical/high/medium finding remains. The minimum directly reported free HBM was 22099 MiB, above the 10,240 MiB reserve. Complete retained timings and scope are summarized in [verification/v3.1.0.json](verification/v3.1.0.json).

The baseline and new hardware runs use actual local models. Standalone Factory timing is compared with the fixed two-run baseline rather than a selected fast trial. Health checks, mocks, a retained Guided replay and prerecorded footage are explicitly distinguished from live generation. Browser testing uses independent same-host processes/contexts and a fictional camera fixture; it does not certify a partner's physical devices or network.

Static scanners complement manual review and adversarial probes. Vendor/minified parsing limitations and the unavailable public Starlette rule pack were recorded; explicit local Starlette checks and live request-boundary tests supplement the available packs. A scanner-only clean result is not a security guarantee.

## Accepted assumptions and limits

- The workstation account and approved private-network users are trusted operators. Presenter controls intentionally have no PIN; direct public-internet exposure and hostile multi-tenant hosting are unsupported.
- Explicit Atlas developer execution remains a product behavior, contained in the documented namespace/Landlock/seccomp boundary and read-only fictional database copy. Human review remains necessary.
- Interactive generated slides require scripts and inline styles inside their opaque sandbox. Some trusted legacy Factory bootstrap markup retains an inline-script policy. The optional prebuilt reference bridge is an external same-origin script. Ordinary shell scripts are external assets; source/window/origin checks constrain bridges.
- Persistent sandbox directory limits are monitored with a short polling interval; a burst may briefly exceed the nominal threshold. Namespace temporary filesystems and per-file/process/time limits provide additional bounds.
- Active vLLM requires a compatible setuptools range. The remaining upstream findings concern unsupported Windows/macOS packaging paths, not the supported Ubuntu wheel installation. They were classified by applicability, not falsely described as universally patched. Legacy standalone lock files use patched setuptools.
- The vendor NVIDIA Arm64 SBSA wheel tag can produce a package-metadata compatibility warning. Original wheel metadata is retained; native loading and actual GPU workloads are verified separately. No platform override, driver replacement or model substitution is used.

Read [SECURITY.md](../SECURITY.md) and the [fresh Fury guide](FRESH_FURY_GUIDE_v3.1.0.md) before deployment. Private vulnerability reporting is enabled through GitHub.
