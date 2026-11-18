# HP ZGX Nano Collective
## Complete installation, launch and presenter guide

**Public Nano preview: v3.2.0-nano.3 · 18 November 2026**

Repository: https://github.com/Navigatedhustle/hp-zgx-fury-showcase/tree/nano_exec

Release and downloadable source: https://github.com/Navigatedhustle/hp-zgx-fury-showcase/releases/tag/v3.2.0-nano.3

This guide covers the seven-experience Nano Collective hub and the five-scene Executive Stage. Both share one local four-model stack. This is a community demonstration, not an officially supported or endorsed HP or NVIDIA product. HP trademarks remain HP property. All supplied business examples are fictional.

## 1. What you need

Use an HP ZGX Nano G1n / NVIDIA GB10 workstation with 128 GB unified memory, Ubuntu 24.04 ARM64, Python 3.12, an existing working NVIDIA driver and CUDA compiler, and at least **200 GiB free disk** for initial installation. The selected model files total approximately **95.9 GiB**; dependency wheels, browser/compiler caches and outputs require additional space. The original full Fury/GB300 profile is separate and must not be launched on a Nano.

The demonstrated host uses driver 580.173.02 and CUDA toolkit 13.0. These identify the tested configuration, not an instruction to replace an existing driver. The installer never changes GPU drivers, kernel, networking, firewall, AppArmor policy or system services. Use an ordinary logged-in user, with an active user systemd session. Do not run the application or installer with sudo.

Internet is required during setup to obtain pinned dependencies and model files. Subsequent model inference and interface assets are local. Setup duration depends on download speed and compilation; the 6–7 second presenter preparation measurement is **not** a first-install or cold model-loading promise.

For the automatic browser window, sign in to the Nano's local desktop. HDMI is recommended for presenting. A headless SSH installation can use `--no-desktop`; it does not automatically expose the loopback-only application to another computer.

## 2. Install in four commands

Run on the Nano:

```bash
git clone --branch v3.2.0-nano.3 --depth 1 \
  https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git hp-zgx-nano
cd hp-zgx-nano
./install.sh
./launch.sh free
```

The installer checks prerequisites, creates local Python environments, installs pinned packages, builds the pinned llama.cpp engine, downloads and hash-checks the selected model files, installs cached Chromium and recorder components, runs a dependency/CUDA/browser smoke check, and creates the desktop/application shortcut where a desktop exists. It does not start another model stack during its smoke check.

To inspect prerequisites without downloading or installing:

```bash
./install.sh --check
```

For SSH/headless setup:

```bash
./install.sh --no-desktop
FURY_NO_BROWSER=1 ./launch.sh free
```

If ordinary Ubuntu packages are missing, have an administrator install the prerequisites before retrying. A typical package command is:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates xz-utils \
  build-essential cmake pkg-config python3.12-venv \
  bubblewrap apparmor-utils util-linux libsndfile1 \
  libespeak-ng1 fonts-liberation fonts-noto-core xdg-utils wmctrl
```

This command does not install a GPU driver or CUDA toolkit. Use the vendor-provisioned workstation for those. Browser system-library requirements vary; if setup reports missing Chromium libraries, inspect:

```bash
.venv/bin/python -m playwright install-deps --dry-run chromium
```

Have the administrator install the reported OS libraries. On this supported Ubuntu configuration, the existing `chrome` AppArmor profile must permit Chromium's own sandbox/user namespaces. `./install.sh --check` checks that the profile can be selected. If local policy blocks the browser, ask the administrator for a narrowly scoped browser policy. Do not disable the browser sandbox or AppArmor to make the demo start.

## 3. What the release includes

The public source contains the Free Mode and presenter interfaces, official owner-supplied HP keyline logo, the original robot hero and robot/vector glyphs, fictional samples, deck renderer, model manifests, dependency/build pins, installer, portable desktop launcher, operation commands, tests and this guide. It also retains the separately documented Fury source and its notices.

The robot hero is supplied interface artwork created with imagegen; it is not a FLUX output generated during your session, and is not counted as live inference. It is bundled at `showcase_app/assets/nano-agent.png`. An original SVG fallback is also included. HP's logo is unchanged, separately covered by its trademark notice rather than the source MIT license.

Model weights, virtual environments, compiled tools, browser profiles, credentials, event recordings, generated outputs and private logs are not published. Setup obtains the model files from immutable upstream revisions and verifies the recorded hashes. No API key is embedded or required for local inference. Any optional personal download token belongs only in your environment and must not be committed.

| Local model | Role | Selected delivery |
|---|---|---|
| gpt-oss-120b | Executive reasoning and agent planning | MXFP4 GGUF |
| Qwen3.6-35B-A3B | Writing, code, vision and translation | Q4_K_XL GGUF and F16 vision projector |
| FLUX.2 klein 4B | Images | BF16 transformer with the pinned FP8 text encoder |
| Kokoro 82M | English narration | CPU speech lane; Michael and Heart |

Exact revisions, files, sizes and hashes are in `config/model-files.json`; runtime choices are in `config/gb10.json`. Model licenses and third-party notices are preserved. No smaller or alternate model is silently substituted.

## 4. Everyday launch and desktop shortcut

Open the **HP ZGX Nano Experience** desktop icon. It loads the shared stack if necessary and opens or focuses the local experience center. The installer also adds the application-menu entry. If a file manager does not honor the trusted flag, right-click the desktop file and select Allow Launching or Trust.

The terminal equivalent is:

```bash
cd hp-zgx-nano
./launch.sh free
```

The hub address on the Nano is **http://127.0.0.1:18808/free**. The launcher uses its installed cached Chromium rather than assuming Firefox or a separate system browser is installed. To suppress automatic browser opening, prefix the command with `FURY_NO_BROWSER=1`.

To recreate the shortcut after moving/reinstalling the checkout:

```bash
./launch.sh desktop
```

Keep the installation directory in place after creating the shortcut, or recreate it at the new location. Every installation has its own state and process registry. Never run two model stacks on this GPU.

## 5. Explore the seven experiences

Choose a card, change its inputs, and run it. Navigation retains workspace controls and output frames within the current page session. Jobs continue when you switch workspaces. Form inputs and Atlas conversation state are not a permanent personal account; the latest 50 job records/outputs are retained locally across service restarts.

| Experience | Try this | Output and boundaries |
|---|---|---|
| Atlas | Ask about risks and next steps for fictional Northwind, then a follow-up | Grounded local account assistant, source references and text export; general knowledge is not web-verified |
| Presentations | Supply a short briefing and choose 3–8 slides | Previews, slide text/notes editing and editable PPTX/JSON; no PowerPoint import |
| Agent Factory | Describe a small browser tool | Planned, locally generated HTML/CSS/JavaScript, sandboxed preview and source download; no generated server or external packages |
| Image Studio | Describe an original subject, style, size and seed | Sequential batches of 1/2/4 PNGs; each image is reviewed locally for unwanted lettering |
| Vision Lab | Choose a fictional whiteboard/chart or public demonstration image | Real Qwen image analysis and text export; no visitor-camera workflow |
| Translate Desk | Paste text or load TXT, DOCX or text PDF, then choose a language | Page-aware translation and TXT/DOCX output; clean text reflow rather than source-layout preservation |
| Voice Studio | Enter English text and choose Michael or Heart | Local 24 kHz WAV narration and playback |

Translation accepts documents up to 500 KB, 9,000 extracted characters and four PDF pages. Scanned PDFs need OCR and are not accepted. Voice input is limited to 900 characters and is English-only. Image review and generated-app smoke checks are fallible; review results, calculations, translation quality and factual claims before use.

Only use public or fictional demonstration material. The Nano profile intentionally excludes Video Studio and Action Trailer: it has no video model or consented visitor-camera pipeline. No real customer records or visitor photos are needed.

## 6. Run Nano Rush

Set the inputs in Atlas, Presentations, Agent Factory, Image Studio, Vision and Translate. Choose **Launch Nano Rush**, review the six inputs, and launch. These are real workflows, not a fixed recorded demo. Open Jobs & outputs or individual workspaces to follow progress and download results.

The manager admits at most 12 unfinished jobs, with three general workers and one speech worker. The image lane has one active renderer and a bounded queue. Starting Rush does not lift those limits. Cancellation stops the owned task and drains pending image work before allowing a mode switch. Completed outputs can be deleted from Jobs & outputs.

Close unrelated memory-heavy applications before a live demonstration. Unified CPU/GPU memory is shared, and image rendering can stop at its existing memory-reserve guard rather than risking the system. A clear error is preferable to a false completed output.

## 7. Presenter Mode and fast preparation

From the Free Mode sidebar, select **Presenter Mode** after current work finishes or is cancelled. Alternatively:

```bash
./launch.sh stage
```

Presenter Mode is at **http://127.0.0.1:18808/stage**. The CLI stage command opens the existing native presenter kiosk. The sidebar opens the presenter in its current browser window. Both use the same resident models.

The Ready screen shows eight core checks, real per-lane progress, elapsed preparation time, a visible Start presentation button, audio/projector options and the verified-backup count. Fast preparation checks real language, vision, speech and a presenter-size image render. It avoids generating the entire show twice. With models already resident, observed preparation was approximately **6.9–8.6 seconds**; an observed Start click reached the opening scene in **0.12 seconds**. Performance varies with memory pressure and caches. The current source reliability update measured 6.9–8.6 seconds with models resident. Cold model loading is separate.

| Scene | What you demonstrate |
|---|---|
| Open | Four resident local lanes, the compact Nano and measured local system counters |
| Nano Agent | A fictional account assignment, five-slide briefing with its generated cover applied to slide 1, and bilingual draft |
| Vision | The supplied fictional whiteboard, extracted actions/owners/dates and executive readout |
| Rush | Six actual parallel/queued workflows, a working ROI app and a downloadable four-image pilot proposal kit |
| Close | Recorded text tokens scaled to 10 customers × 200 employees × 30 days × 12 months, with monthly/yearly frontier API and Nano electricity bar charts |

The closing comparison stays visible until you advance or leave. It uses the live show's text-token ledger (input and output), excluding warmup, recorded playback and vision/image-review requests. One show is repeated once per customer: **10 customers per employee per day × 200 employees = 2,000 workflows/day; × 30 = 60,000/month; × 12 = 720,000/year**. Output, input and combined token totals appear for each period. Cloud costs use both input and output rates, not output rates alone.

**Assumptions & pricing sources** opens dated official OpenAI, Anthropic and Google rates and editable Nano electricity inputs. Defaults are **200 Nanos (one per employee), 140 W average wall power, 8 powered hours/day, $0.15/kWh**: $1,008/month or $12,096 across 12 30-day months. Power and runtime are assumptions, not measurements or capacity qualification. Nano has no token fees; hardware and support are excluded. Cloud bars represent text API fees only, excluding vision, generated images, audio, tools, discounts and taxes; tokenizers, reasoning and model outputs differ. Annual figures hold the 2026-11-18 rates constant across 360 days. Gemini 4 Carbon's promotional $2 input / $10 output per million expires November 30, with published $4 / $20 rates from December 1; the chart is a dated annualized comparison, not a forecast. Changing electricity assumptions affects only this browser's current presentation view.

Generated presenter illustrations follow the fictional Northwind administrative planning-pilot story. The briefing cover depicts a meeting suite. Rush supplies a CIO briefing opener, private administrative workspace, team workshop and pilot-planning background, each labeled with its intended use. **Download 4 images** exports the PNGs, a usage README and a manifest with hashes. The briefing download contains its reviewed cover. These are proposed concept illustrations, not photographs of a customer or proof of deployment. Local vision checks both subject relevance and unwanted lettering before release; one regeneration is permitted per image. Free Mode's starter image brief also supports the Northwind pilot proposal; edited prompts remain visitor-directed.

**Exit full screen** is available in the presenter header and Free Mode's top bar when fullscreen is active. It restores the native demo window without changing scenes or clearing work. The same control becomes **Full screen** to enter again. In a standard browser, this toggles webpage fullscreen; if you entered browser fullscreen using F11, use F11 to leave it.

**Back to Free Mode** is available in the top bar of every presenter scene, with a larger button on the closing comparison in step 05. It ends the current presentation, stops its unfinished work and clears its session outputs before opening Free Mode. It does not run another rehearsal or reload the resident models. Download any presenter outputs you want to keep before leaving.

If a Rush task fails, successful results stay visible and the scene reports the actual completed count. **Retry unfinished work** keeps those results and retries only failed/interrupted tasks under a new run identity; unavailable owned services are recovered first. **Continue** advances the show, and **Back to Free Mode** remains available. A missing optional backup does not erase completed work. A failed Agent/Vision scene offers **Retry this scene**. Preparation and idle-check errors offer **Retry preparation**. Idle image review has a bounded two-boolean response budget, separate from the eight-token text keep-alive probes. Free Mode retains form inputs and provides **Run again** for failed/cancelled jobs.

If Free Mode reports a local model unavailable, **Recover local models** appears in its top bar. Finish or cancel active jobs first, then use it to recover the unavailable services while keeping inputs and completed outputs. The closing scene can still show session results when a worker is offline. Opening a stale `/stage` link while Free Mode owns the stack returns to the active Free Mode hub; use **Presenter Mode** in its navigation to switch explicitly.

The image renderer restores checkpoint weight sharing after FP8 quantization and uses small decode tiles to reduce memory pressure. Memory reserve guards, bounded queues and local artwork review remain enforced. Preparation now tests the Rush image dimensions and its stricter reserve. A transient allocation failure gets one automatic cleanup retry; persistent failures remain visible with a specific recovery action.

The UI does not fabricate token throughput or report the decorative robot as model work. Recorded playback is labelled separately. The default fast live session can start without video backups. If a live workflow fails and a current verified clip is unavailable, the failure stays visible; no stale recording is substituted.

## 8. Clicker, keyboard and protected shows

| Key/action | Behavior |
|---|---|
| Start button, Right, Page Down, Space or Enter | Advance |
| Left or Page Up | Back |
| V | Select/toggle a verified current backup if one exists |
| Hold R for two seconds | Reset the current segment |
| B or period | Toggle black screen |
| `/stage/keys` | Check the actual clicker's press/release events |

Standard keyboard navigation and controls remain usable. The display check needs at least a 1280×720 CSS viewport; use native display resolution at 100% zoom. The revised layouts were checked at 720p, 768p, 1080p, 1200p and in larger layout replays. Audio defaults off. If you enable it, check HDMI output with the AV team and wait for preparation to complete.

For a protected event, enable **Require verified backups**. Start then waits for all five clips to match this source build. Record the build on a native 1920×1080 display:

```bash
./launch.sh stage record
```

Recording performs the full two-pass rehearsal, records real work and verifies the files. It can take considerably longer than fast preparation. Runtime source/profile changes require fresh recordings; a public download does not include another machine's recordings.

Optional full rehearsal without recording:

```bash
./launch.sh stage rehearse
./launch.sh stage status
```

Fast functional readiness is not full keynote/event qualification. Rehearse the entire show and emergency controls on the actual event hardware and display.

## 9. Status, stop and recovery

```bash
./launch.sh free status
./launch.sh stage status
./launch.sh stop
```

Status lists owned processes and model readiness. Stop uses the existing identity-checked controller; it does not kill unknown PIDs. To reset a presenter session:

```bash
./launch.sh stage reset
```

To repair missing setup files, rerun `./install.sh`. Interrupted downloads retain local metadata and are verified on retry. Setup may need internet; normal inference runs with the offline model settings. Do not launch setup in parallel with active demonstration jobs.

If a process is not responding, inspect `logs/stage.log`, `logs/image.log`, `logs/text.log`, `logs/lead.log`, `logs/tts.log` and the reported controller status. Desktop-launch errors are in `state/desktop-launch.log`. Logs and job artifacts are private local data; review before sharing. Do not stop a foreign port listener by guessing a PID. Identify and stop its owning application normally.

If a browser window does not open, sign in to the local desktop, visit the loopback URL, and run `.venv/bin/python ops/nano-setup-smoke.py`. This checks installed imports, CUDA, engine interfaces and sandboxed Chromium without loading a second model stack.

## 10. Data, privacy and security

Model inference is local and services bind to loopback ports. This project does not set up a public web server or change network exposure. Remote access requires a separately administered secure route; no networking changes are performed by these install commands.

Runtime outputs are installation-local and shared by users of that station. `state/free-mode/` holds Free Mode jobs; `state/stage/` holds presenter state and outputs. Browser profiles and optional event branding remain local. The public repo excludes credentials, runtime databases, model weights, visitor media, logs and backups. Generated browser apps run in an opaque iframe with a networkless content-security policy; the installed Chromium sandbox stays enabled.

The official HP logo and generated decorative robot are supplied UI assets, distinct from real model outputs. Model and third-party license notices remain in the repository. Do not imply that the community demo or generated answers are certified by HP, NVIDIA or model authors.

## 11. Update and rollback

Finish/cancel all jobs, preserve any outputs you need, and stop the owned stack before changing runtime source. Never change a checkout underneath a running presenter session.

```bash
./launch.sh stop
git fetch --tags origin
# Select a reviewed Nano release tag, then rerun its installer.
./install.sh
./launch.sh free
```

The guide's clone command pins v3.2.0-nano.3 for reproducibility. A future update should name an explicit reviewed Nano tag in `git switch --detach TAG` between fetch and install. To roll back, stop and select the prior known-good Nano tag, then rerun its installer. Existing Fury releases are for different hardware profiles and are not an automatic Nano rollback target.

Do not copy process registries between installations. Recreate the desktop shortcut after moving the installation. Keep recordings matched to their build. Do not delete model files merely to free memory; stop unused workloads instead.

## 12. Validation and release limits

The v3.2.0-nano.3 release reran **262 hardware-independent Nano/controller/gateway/booth/installer tests** and **seven JavaScript cost-chart tests** successfully. The new closing economics screen passed browser layout and interaction checks at 1920×1080, 1366×768, 1280×720, 1440×900 and 1024×768; the smaller viewport uses contained vertical scrolling. Those browser checks used explicitly illustrative token counts and did not run model inference. [Economics verification](verification/nano_economics.json).

Prior 10 November hardware evidence covers two normal five-scene shows, recovery of a third show after an intentionally stopped image service while preserving five completed Rush results, and all seven Free Mode experiences. See [the reliability record](verification/nano_reliability.json). This release did not repeat a fresh-device cold installation, full hardware acceptance, ten-show qualification or a 45-minute idle test. No zero-swap claim is made. Earlier dependency-environment and interface checks remain in [the Nano UI record](verification/nano_collective_ui.json); they are prior results, not newly repeated checks.

The separately documented Fury/GB300 profile and its historical Factory test limits are not Nano hardware acceptance. Publication allowlist, exact source/archive checks and secret scans are separate from hardware qualification.

A fresh source/archive check and installer dependency smoke test do not establish that every new driver/OS combination will cold-install successfully. The release retains the tested hardware profile and pinned model identities. If a prerequisite or checksum fails, stop and fix the named issue; never bypass a safety check or silently change models.
