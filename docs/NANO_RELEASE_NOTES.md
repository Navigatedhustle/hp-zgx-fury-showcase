# Nano Collective v3.2.0-nano.3

18 November 2026 · Public Nano preview · Branch `nano_exec`

The presenter close now turns the show's recorded text-token ledger into a visible team-scale scenario: 10 customer workflows per employee per day, 200 employees, 30 days per month and 12 months per year. Output/input totals and persistent monthly/yearly bar charts compare standard frontier text API fees with assumed Nano electricity. The source date, promotional-rate limits, exclusions and editable electricity assumptions are visible.

This release also includes the previously local Nano reliability and presenter improvements: preserve completed Rush work while retrying failures; clearer service/memory errors and recovery controls; native fullscreen and return-to-Free-Mode controls; contextual, locally reviewed fictional pilot images; the briefing cover embedded in the exported first slide; and the downloadable four-image pilot proposal kit. Model identities, memory reserves and bounded queues are preserved.

## Downloads

- **HP-ZGX-Nano-v3.2.0-nano.3-share-kit.zip** — source folder, three-page quickstart PDF, seven-page complete guide PDF, presenter card, release notes and internal checksums. Start with `START-HERE.pdf`.
- **HP-ZGX-Nano-Quickstart.pdf** — concise fresh-Nano install and first-run instructions.
- **HP-ZGX-Nano-Complete-Guide.pdf** — installation, operating controls, model/license details, headless use, recovery and qualification limits.
- **HP-ZGX-Nano-Presenter-Card.pdf** — one-page presenter pacing and controls.
- **hp-zgx-fury-showcase-v3.2.0-nano.3.zip / .tar.gz** — allowlisted source archives.
- **SHA256SUMS** — hashes of the downloadable release assets.

Models, Python environments, compiled tools, credentials, browser profiles, runtime logs, private session artifacts and recordings are not included. Initial installation downloads approximately 95.9 GiB of pinned model files plus dependencies; reserve 200 GiB free disk. Use the tested Ubuntu 24.04 ARM64 / 128 GB GB10 profile with a working NVIDIA driver and CUDA toolkit.

## Install

```bash
git clone --branch v3.2.0-nano.3 --depth 1 \
  https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git hp-zgx-nano
cd hp-zgx-nano
./install.sh
./launch.sh free
```

Open http://127.0.0.1:18808/free on the Nano. For the share kit, extract it, open Terminal in its source subfolder, restore executable bits if your ZIP extractor drops them, then run install and launch. Do not run the installer with sudo. The guide covers administrator-managed OS prerequisites. The current Nano branch is separate from the Fury/GB300 default branch.

## Validation

- 262 hardware-independent Nano/controller/gateway/booth/installer tests passed.
- Seven existing JavaScript frontier-cost tests passed; the 262 tests include four new Nano projection checks.
- Closing-screen browser checks passed at five viewport sizes; 1280×720 through 1920×1080 fit without scrolling, while 1024×768 uses contained vertical scrolling. Tests used labeled illustrative counts, not model inference.
- Source integrity, publication allowlist, exact staged-blob audit and secret scans are required before publishing. The kit is extracted and checked against its source hashes, with installer entry points and PDF contents inspected.

Prior live hardware results are retained in `docs/verification/nano_reliability.json` and related records. A fresh-device cold install, new full hardware acceptance, ten-show qualification and a 45-minute idle test were not repeated for this release. This remains a preview, not a newly hardware-qualified build.

## Pricing scope

The chart uses the 18 November 2026 standard short-context rates from official OpenAI, Anthropic and Google sources. Annual values are 12 30-day months at those dated rates, not a future bill forecast. Gemini 4 Carbon's promotional rate expires November 30. Cloud bars cover text tokens only; vision, image generation, audio, tools, taxes and discounts are excluded. Tokenizers, reasoning and outputs differ. Nano electricity defaults to 200 devices at 140 W, eight hours/day, $0.15/kWh ($1,008/month; $12,096/year). Power is assumed, not measured; hardware/support and unselected powered hours are excluded. No fleet capacity claim is made.

## Upgrade

Finish/cancel jobs, preserve outputs you need and run `./launch.sh stop`. Fetch tags, select the reviewed Nano tag, rerun its installer and relaunch. Do not overwrite local edits or copy process registries between installations. Recreate the desktop shortcut after moving the installation. Existing recordings must be recreated for the new build. Older releases remain unchanged.
