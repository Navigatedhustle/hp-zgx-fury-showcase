# Fury V3 launch guide

> Historical V3 review record. Its original authorization and measurements are retained below. For the current v3.1.0 release, use the [fresh Fury guide](FRESH_FURY_GUIDE_v3.1.0.md), [security review](SECURITY_REVIEW_v3.1.0.md) and [current verification](verification/v3.1.0.json).
V3.0.0 Mission Control is an unmerged review branch. No V3 tag or release is published. The owner reviews the PR before any release decision. Existing tags and main remain immutable.

## Prepare and launch

Use the tested Ubuntu 24.04 ARM64 GB300 host: 256703 MiB HBM and 494.15 GiB usable physical Grace memory. Linux aggregate memory is about 743.65 GiB because HBM is included. Preflight requires 480 GiB Grace, 700 GiB combined capacity and 350 GiB initially free disk. Model files total about 227.566 GiB. Keep the existing working driver, CUDA toolkit and bubblewrap isolation.

```bash
git clone --branch v3 https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git
cd hp-zgx-fury-showcase
./launch.sh
```

Open http://localhost:8080. Setup resumes downloads, verifies pinned model hashes, creates local environments, builds the editor and waits for readiness. Cold compilation requires internet and may take tens of minutes. No host driver, kernel, firewall, Tailscale or boot-service changes are made. Weights and environments are never bundled in source archives.

## Present eight experiences

Atlas grounds synthetic analytics with evidence, voice and executive export. Presentations creates a three-slide local draft with editable PowerPoint. Agent Factory short Live builds generate and independently test real frontend/backend code; Guided is explicitly recorded playback. Image Studio provides five styles, four ratios, seed and serial batches.

Vision Lab offers five original fictional image samples with extraction and a grounded brief. Translate Desk accepts PDF/DOCX/TXT, offers 34 language choices and PDF/DOCX/TXT downloads, and checks extracted-line/numeric/code coverage. It reflows text, does not preserve source layout, and gives advisory terminology review. Scanned PDFs are rejected; language quality varies.

Video Studio makes five-second text-to-video or image-to-video clips with Wan2.2 TI2V 5B and named LongLive-Plug adapters. The proven preset is 121 frames at 24 fps, four inference steps, CFG 1, 1280×704 or 832×480. Image Studio's Send to Video action carries a generated reference into the same shared creative lane.

Action Trailer requires consent before camera access. Choose an original PG genre, capture one photo, follow the screenplay/keyframes/clips/narration, then tap to play fullscreen with sound. A slow run visibly cuts from three shots to two. Press Done to delete the photo and media.

## Privacy and bounded concurrency

Only Action Trailer collects a real visitor photo. All processing stays on this Fury, in 0700 temporary session directories outside the repository. The browser receives a private preview; final download is restricted to localhost on the station. Done, New visitor, explicit deletion, 15 minutes idle and service startup delete files and stop owned work. Polling does not extend retention. No visitor media, descriptions, cookies or private evidence belongs in Git, screenshots or source archives. Use fictional/public data elsewhere.

Fury Rush invokes six original Go controls: Factory, Atlas, Presentations, Vision, Translate and Image Studio. Queued/submitted/complete/failed states are real. One shared Factory build remains the global limit; Rush waits if it is busy. Gateway admission stays four total, three ordinary and one Atlas reserve. DeepSeek retains 16K context/one sequence; Qwen retains 65K/four sequences. Short lead requests visibly route to Qwen when DeepSeek is busy. FLUX and Wan share one active creative slot plus three queued. CPU offload stays on physical Grace, preserving the 10 GiB HBM reserve.

## Screens, metrics and local operation

Use `/stations` for browser-local role assignment. Mission Control, Model Hub, Performance, Cloud vs Local, Local and secure, and About share the local shell. Desktop acceptance uses 1366×768, 1280×720, 1440×900 and 1920×1080 CSS content pixels plus shorter laptop/mobile cases. Keep browser zoom at 100%; use contained panels or optional fullscreen.

The shared two-second sampler reports native hardware/process counters and native vLLM output-token deltas. Grace used includes page cache; per-node MemAvailable is not exposed. External AI count covers instrumented gateway destinations, not all machine traffic. GPU energy excludes the rest of the workstation. Dated official cloud prices are scenarios with capability/output differences; electricity is not ownership cost or ROI.

```bash
./launch.sh status
./launch.sh diagnostics
./launch.sh recover agent
./launch.sh stop
./launch.sh setup
```

Inspect active jobs before recovery. Use only identity-checked lifecycle commands. Preserve evidence of failed generation; never substitute a canned success. No second model stack or unknown PID should be stopped. Diagnostics contain private operational information and require review before sharing.

## Verification and handoff

See docs/V3_VERIFICATION.md and docs/verification/v3.json for actual hardware timings, failures, cuts, playback, memory sampling and browser scope. Health checks and mocks do not qualify as hardware acceptance. Physical webcam/microphone/speaker quality and a recipient's remote client require site validation. Private HTTPS depends on the site's existing secure configuration; this upgrade makes no networking changes.

The approved deliverable is branch v3 and an unmerged PR titled V3.0.0 Mission Control. Run the source/secret/publication checks before pushing. config/distribution-files.json and SOURCE-SHA256SUMS explicitly select source; weights, environments, databases, session files, raw logs and generated media remain excluded. Do not publish a V3 tag, release or replacement archive under an old tag.

For rollback, wait for idle and back up runtime outputs, stop through the current launcher's controller, then switch a clean checkout to the retained v2.3.0 tag and run setup/launch. Do not copy process registries between installations. Keep Guided artifacts labeled recorded.

Source and asset terms are in LICENSE, THIRD_PARTY_NOTICES.md and docs/ASSET-MANIFEST.md. HP/NVIDIA marks remain their owners' property; this community demonstration is not an officially supported product.
