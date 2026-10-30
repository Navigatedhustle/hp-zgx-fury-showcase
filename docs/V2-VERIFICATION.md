# V2 verification

V2 was validated on 2026-10-30 against the preserved V1 deployment. V1 remains immutable at v1.0.0 / e98c85ee26169a6d745de775feea049ae7a3dc63. Raw browser/run/operational records stay private; this document records the inspectable scope and aggregate results.

## Scope and unchanged contracts

The presentation layer is isolated from the model/gateway state. Model revisions, inference settings, admission limits, APIs, streaming, cancellation, artifact storage and application session ownership are preserved. The only Atlas backend addition mounts the shared local static assets. New booth slides use a neutral light template and official logo asset; historical decks and generated customer applications are not rewritten. The setup stamp now includes editor source so an upgrade rebuilds the editor. Existing source-only regression suites and two setup-stamp regressions cover these changes.

Routes remain: dashboard / on 8080; /operator and /connect on 8080; Atlas / on 8200; presentations /booth and full React editor / on 8765; Factory /devteam and /devteam/build on 8501; images / on 8800. Generated application and backend routes retain their original sandbox/session contracts. Model endpoints remain 8000/8100, gateway 8001, ASR 8202 and TTS 8204. Shared artwork is /showcase-assets. Private networking configuration and raw operational records are deliberately excluded from public documentation.

V1's source/dependency/model and clean-install evidence in VERIFICATION.md is reused for unchanged backend behavior. V2 tests share the existing tested workstation OS/driver/toolkit. No second hardware platform or fresh GPU provision is claimed. Current private serving budgets remain those of the preserved live deployment (176 GiB nominal lead); public launch retains V1's tested 168 GiB public lead allocation. Comparisons use the same live model processes and settings on both sides.

## Functional and visual results

- 140 Factory regressions passed; 19 controller/gateway/booth/setup fixtures passed. After preview-shell changes, 16 relevant route/sandbox fixtures passed again. Frontend lint, TypeScript and production build passed with the original dependency lock.
- 32 primary-page browser combinations passed: home, Atlas, booth, Factory, image, operator, full editor and connection page at 1440/1280/390px in light mode, plus 1440px dark mode. Four methodology-page combinations also passed. No page overflow, page errors, unexpected failed HTTP responses or automated axe 4.11 WCAG 2 A/AA, 2.1 AA or 2.2 AA violations were reported in those checked states.
- Keyboard skip links, named navigation, >=44px header controls, explicit theme persistence and reduced-motion rendering were checked. Scrollable Atlas answers/model details and operator tables received keyboard focus. Native hidden job controls/panels remain hidden. Measured token-pair contrast: blue/white **7.06:1**, body/white **17.40:1**, secondary/gray50 **4.97:1**, dark secondary/panel **10.41:1**. This is tested accessibility evidence, not a complete independent WCAG certification.
- Screenshots were inspected for each primary workflow, home/catalog/differentiators/presenter content, mobile layouts and dark adaptation. Actual completion screenshots and isolated network-failure states were retained. Error injection was limited to a test browser; no fake inference was presented as a result. Axe instrumentation bypassed CSP only in its browser context; production CSP and generated-code isolation were preserved.
- Two independent Atlas sessions produced distinct real grounded result IDs and valid PNG/PDF exports. Actual TTS/ASR returned the forecast phrase. Physical microphones/speakers and external device quality remain unverified.
- Actual booth cancellation and image reload/reconnect passed. Factory reload retained the owner’s active run; another session could not stop it (HTTP 404); the owner’s Stop ended it. An earlier browser-test predicate violated strict CSP after starting a test-owned run; only that known test run was cancelled, its files retained, and the corrected browser check passed.
- Full React editor, rendered deck preview and actual private HTTPS navigation passed. Host browser DNS required a test-local resolver mapping to the host’s private address; certificates and actual private HTTPS transport were used. No DNS/network configuration was modified and no private hostname/address is published.
- Existing complete-travel output from V1 was exercised through the V2 preview shell in the independent installation: **13 desktop/mobile browser/API checks passed**, including two-user permissions, reservations, persistence, admin, Factory preview and backend explorer. This is expressly a retained generated application, not a newly generated V2 full build. Full generation logic/model settings are unchanged and reuse V1's fresh-build evidence.

## Sustained concurrency

The unchanged acceptance harness ran **three cycles over 1098.84 seconds (18.31 minutes)**, sustaining Atlas/decks/images while each new short Factory application generated. All **316 workflow results passed**: 114 Atlas, 79 decks, 120 images and three new short applications. Every cycle had measured four-way backend execution overlap (maximum observed simultaneous intersections 0.334/0.400/0.408 seconds). These are actual execution-interval intersections, not inferred from UI animations or submission times.

All 79 downloaded three-slide PPTX files opened and contained **1659 editable text shapes** in total. All 436 saved PNG files decoded. The minimum sampled free HBM was **13750 MiB** on this preserved live serving configuration. Sampling cannot establish every instantaneous minimum or indefinite stability.

| Workflow | V1 single-burst sample | V2 sustained median / p95 |
|---|---:|---:|
| Atlas | 1.10 s | 1.28 / 1.86 s |
| Presentations | 11.02 s | 5.17 / 8.62 s |
| Image | 8.29 s | 0.75 / 1.69 s |
| Short application | 329.13 s | 370.10 / 386.55 s |

These are submission-to-verified-output timings, not model decode benchmarks. The sustained run deliberately submits many more competing requests than the single-burst baseline; cache warming also differs. The short builds made 15/15/16 model calls versus V1's 15. The 12.4% sustained median increase was investigated as a changed-load/repair comparison, not attributed to rendering. All original budgets passed (Atlas/image 15s, decks 45s, short Factory 600s). A further matched single-burst comparison passed after the final application-service restart: Atlas **1.17s**, presentations **8.25s**, images **1.26s**, short application **346.93s**, with two measured four-way overlaps. The build made 15 model calls, as in the baseline. Its 5.4% increase over the one V1 sample is within the 311.88–386.55s V2 range; this small sample does not establish a causal UI performance change. No functional budget regressed. No guaranteed speedup is claimed.

## Distribution and launch

The launch/configuration/model pins, inference settings, locks and verified service-ownership checks are retained. V2 fixes editor upgrade freshness by hashing frontend source in the setup stamp. Its two regression tests prove UI changes invalidate setup while generated build files do not.

A separate clean local clone and Git-free candidate archive matched the explicit source policy/checksums. With an empty home and isolated environment, each actual launcher safely refused all ten foreign service ports without adopting or stopping them. The independent V1 clean-install directory then received the exact candidate source: actual setup rebuilt the editor and verified all 193.91 GiB of its previously independently downloaded pinned model files using its own environments/caches, without publisher credentials. The full portal test ran from that installation on a separate app-only port; it did not load duplicate models.

V1's full empty-cache installation, model initialization and lifecycle evidence remains applicable to unchanged serving/launch paths. V2 did not repeat a second 193.91 GiB download, cold model boot, fresh OS or driver installation. It preserves the working original model processes and privately configured access, while testing changed UI/export/setup behavior directly. Public delivery identity and CI results are recorded in the release notes. No private configuration, runtime output, licensed HP fonts, raw logo archives or session logs are distributed.

## Release identity and rollback

Release v2.0.0 is identified by its annotated Git tag and the exact source hashes in SOURCE-SHA256SUMS. Its public ZIP/TAR and SHA256SUMS use the same explicit inclusion policy. Raw run IDs, private URLs and machine/session records remain in the local handoff, not in this package. README contains clone/archive launch and exact V1 rollback commands. Existing generated applications remain in their runtime directories or the existing terminal-run archive; this release does not rewrite or delete them.

Final idle check: viewing Operator created no new inference ledger entries. Actual TTS returned 151200 PCM bytes and ASR recovered the forecast phrase. The four original model service leader PIDs and private Serve configuration were independently confirmed unchanged; application-only services were restarted only while idle.
