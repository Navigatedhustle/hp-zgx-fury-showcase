# HP ZGX Fury — V3 Mission Control

Eight local AI experiences share one GB300 workstation, with real model routing, visible queues and measured hardware telemetry. V3 is a review branch; no V3 tag or release is published. Existing releases remain immutable.

This community demonstration uses fictional business data. HP and NVIDIA names identify the tested hardware; this project is not an officially supported or endorsed HP or NVIDIA product. Their marks remain their owners' property.

```bash
git clone --branch v3 https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git
cd hp-zgx-fury-showcase
./launch.sh
```

Open **http://localhost:8080**. Mission Control provides eight launch cards, retained workspaces, model lanes, jobs, a Model Hub, performance history and sourced cloud cost scenarios. **Fury Rush** submits six real workflows through their original controls: Factory, Atlas, Presentations, Vision, Translate and Image Studio. Work remains bounded by the existing queues.

| Experience | Local address | What to demonstrate |
|---|---|---|
| Atlas | http://localhost:8200 | Ask how an 8 percentage point Commit win-rate drop changes Q4 profit. Inspect synthetic grounding, the real audio-reactive orb and executive export. |
| Presentations | http://localhost:8765/booth | Generate three slides from a brief; inspect and download editable PowerPoint. Full editor retained. |
| Agent Factory | http://localhost:8501/devteam | Automatic short Live build: real local development, sandbox tests, functional preview and visual acceptance. Guided mode is clearly labeled recorded playback. |
| Image Studio | http://localhost:8800 | Five styles, four ratios, seed and sequential batches of 1/2/4. Download or Send to Video. |
| Vision Lab | http://localhost:8080/experience/vision | Five original fictional image samples; actual Qwen extraction followed by a lead-lane executive brief. |
| Translate Desk | http://localhost:8080/experience/translate | PDF, DOCX or TXT into 34 language choices, page navigation and PDF/DOCX/TXT downloads. |
| Video Studio | http://localhost:8080/experience/video | True text-to-video or reference image-to-video: 121 frames at 24 fps, 1280×704 or 832×480. |
| Action Trailer | http://localhost:8080/experience/trailer | Consent, camera capture, an original three-shot PG screenplay, reference keyframes, local clips, narration and soundtrack. |

Translate uses **clean text reflow**, with advisory terminology review; original document layout is not preserved. Every extracted text line, number and product code is checked before completion. Scanned PDFs require OCR and are rejected; fictional document images can be tried in Vision. Language quality varies and needs human review.

Video uses the pinned Wan2.2 TI2V 5B backbone with named Apache-2.0 LongLive-Plug adapters, four inference steps and CFG 1. No model is silently substituted. The proven video preset is five seconds; trailer assembly may visibly cut to two shots when its time budget is exceeded. Fullscreen playback with sound needs a user tap.

Action Trailer is the only real visitor-photo workflow. Consent precedes camera access. Photos and generated media stay in per-session storage outside the repository, are processed only by local models, and are deleted on Done, New visitor, explicit deletion, 15 minutes idle and service startup. Polling does not extend retention. The browser receives a private preview; final download is restricted to localhost on the station. Use localhost or an operator-configured private HTTPS context for camera access. Vision and other uploads are for fictional/public demonstration material.

**Tested host:** Ubuntu 24.04 ARM64, NVIDIA GB300 with 256703 MiB HBM and **494.15 GiB usable physical Grace memory (NUMA node 0)**. Linux reports about 743.65 GiB aggregate memory because it includes HBM as NUMA node 1. That aggregate is not physical Grace capacity. Preflight requires at least 480 GiB physical Grace and 700 GiB combined Linux-visible capacity. Other hardware/platforms are unverified. Reserve 350 GiB free disk initially; model assets total about **227.566 GiB**, plus dependencies, compiler caches and generated outputs. [Prerequisites](docs/PREREQUISITES.md).

Setup creates pinned local environments, verifies model files, builds the editor and waits for service readiness. First installation and cold NVIDIA compilation need internet and can take tens of minutes. Subsequent launches reuse caches and identity-checked healthy services. No GPU driver, kernel, firewall, networking or boot-service changes are made. Weights, environments, runtime databases, cookies, photos and private evidence are excluded from Git and source archives.

```bash
./launch.sh status
./launch.sh diagnostics          # local operational details; review before sharing
./launch.sh recover agent        # guarded recovery after workloads are idle
./launch.sh stop                 # identity-checked shutdown
./launch.sh setup                # resume interrupted setup
./launch.sh desktop              # optional desktop shortcut
```

DeepSeek retains its 16K context and one sequence; Qwen retains its 65K context and four sequences. Gateway admission remains four total, three ordinary and one reserved for Atlas. Factory admits one build and at most two development calls. FLUX and Wan share one creative process and one active GPU slot, with three queue slots; idle modules are offloaded to physical Grace. The 10 GiB HBM reserve is preserved. Short lead requests visibly route to Qwen when DeepSeek is busy, with requested/actual model and reason in the ledger.

Telemetry comes from native GPU/CPU/memory counters and vLLM output-token deltas, using one shared collector and cached SSE. External AI requests count instrumented gateway destinations, not all machine traffic. Cloud vs Local includes a [frontier API cost bar chart](docs/CLOUD-COMPARISON.md) with editable whole-system power, runtime and tariff assumptions; provider electricity stays bundled into API prices. Measured session energy is GPU-only; electricity is not total ownership cost. Cloud prices are dated official scenarios with output/capability differences disclosed. [Architecture](docs/ARCHITECTURE.md) · [Verification](docs/V3_VERIFICATION.md).

Conference stations remain at `/stations`; assignments belong to each browser. Use the actual CSS viewport at 100% zoom, principally 1366×768, plus 1280×720, 1440×900, 1920×1080 and shorter laptop cases. Workspaces use contained scrolling. Fullscreen is optional.

[Quickstart](QUICKSTART.md) · [Presenter script](docs/PRESENTER.md) · [V3 launch guide](docs/V3_LAUNCH_GUIDE.md) · [Launch PDF](docs/V3_Launch_Guide_v3.0.0.pdf) · [Models and licenses](docs/ASSET-MANIFEST.md) · [Third-party notices](THIRD_PARTY_NOTICES.md) · [Remote access](docs/REMOTE-ACCESS.md) · [MIT source license](LICENSE)

## Upgrade and rollback

Prior releases v2.2.0, v2.1.1, v2.1.0 and v2.0.0 remain available and immutable. V1 also remains available as v1.0.0 (commit e98c85ee26169a6d745de775feea049ae7a3dc63). Preserve runtime outputs and wait until all users/jobs are idle before switching a release. Never start two model stacks on this GPU.

For a Git checkout with clean tracked source:

```bash
./launch.sh stop
git fetch --tags origin
git switch --detach v2.3.0
./launch.sh
```

To roll back:

```bash
./launch.sh stop
git switch --detach v2.2.0
./launch.sh setup  # restore the preceding conference release
./launch.sh
```

For archive installs, keep the previous release directory and its own environments/output. Stop the current installation through its own launcher, then launch the previous one. Do not copy process registries between directories. Back up outputs first; this UI release changes no application database schema.

V2.0 predates Guided demonstration. Use a fresh browser profile when presenting a prior release; retained recorded artifacts remain recorded and must not be described as newly generated.
