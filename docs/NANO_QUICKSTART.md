# HP ZGX Nano Experience
## Fresh Nano setup • Start here

**Release v3.2.0-nano.3 · 18 November 2026**

A local AI demo with seven interactive experiences and a five-scene presenter show. This is a community demonstration, not an officially supported HP or NVIDIA product.

### 1. Check the Nano

Use an **HP ZGX Nano / NVIDIA GB10, 128 GB unified memory, Ubuntu 24.04 ARM64**. You need a working vendor-provided NVIDIA driver and CUDA toolkit, Python 3.12, a normal logged-in desktop user, and **at least 200 GiB free disk**. A display with a **1280 × 720 or larger CSS viewport** at 100% browser zoom is required for Presenter Mode.

Connect to the internet for installation. The model download alone is approximately **95.9 GiB**, plus dependencies and build caches. Initial download, compilation and cold model loading take time; do not interpret fast presenter preparation as first-install time. No paid cloud API key is required.

### 2. Install and launch

Open Terminal on the Nano. Run these commands as your normal user:

```bash
git clone --branch v3.2.0-nano.3 --depth 1 \
  https://github.com/Navigatedhustle/hp-zgx-fury-showcase.git hp-zgx-nano
cd hp-zgx-nano
./install.sh
./launch.sh free
```

Setup checks prerequisites, creates local environments, downloads pinned model files, verifies hashes, builds the inference engine, installs the browser and creates the **HP ZGX Nano Experience** desktop shortcut. It does not replace the GPU driver or change networking. Never run install/launch with sudo.

The demo opens at **http://127.0.0.1:18808/free** on the Nano. A successful installation and four ready model lanes are your starting point. The first cold launch is slower than later launches.

**Using the download kit instead?** Extract the share-kit ZIP with your file manager, open Terminal inside its `hp-zgx-fury-showcase-v3.2.0-nano.3` source folder, then run:

```bash
chmod +x install.sh launch.sh showcase ops/nano-desktop.sh
./install.sh
./launch.sh free
```

Keep the extracted folder in place; the shortcut points to that installation. You still need internet for the initial model/dependency downloads. The kit contains source and guides, not preloaded models.

<!-- pagebreak -->

# Try the demo
## From first launch to the closing story

### 3. Explore Free Mode

Choose **Atlas**, **Presentations**, **Agent Factory**, **Image Studio**, **Vision Lab**, **Translate Desk** or **Voice Studio**. Start with the included fictional examples. Click Run/Create, inspect the result and download what you want to keep. **Jobs & outputs** shows progress. Nano Rush launches six real workflows together using the existing bounded queues.

The four local models are gpt-oss-120b, Qwen3.6-35B-A3B, FLUX.2 klein 4B and Kokoro 82M. Video is not part of this Nano profile. Use public or fictional demonstration content and review generated results.

### 4. Start Presenter Mode

Finish or cancel active jobs, then choose **Presenter Mode** in the sidebar. Wait for the readiness checks, click **Start presentation**, and advance with **Right arrow**, **Page Down**, **Space** or **Enter**.

| Scene | What to show |
|---|---|
| Open | Four local models, the Nano and cloud-call counter |
| Agent | Fictional Northwind account brief, five slides, cover image and bilingual follow-up |
| Vision | Whiteboard actions, owners, dates and executive readout |
| Rush | Six workflows, working app, generated image kit and live queue states |
| Cloud vs local | Actual text tokens scaled across customers and employees, with monthly/yearly cost bars |

**Left arrow / Page Up:** go back. **Hold R for 2 seconds:** reset a scene. **B or period:** black screen. **Full screen / Exit full screen:** change the view. **Back to Free Mode:** end the presentation and return to the hub; download presenter outputs first because exiting clears that session.

### Explain the cloud-versus-local chart

The final scene stays visible. It uses the show's recorded text input/output tokens and repeats that work for **10 customers per employee per day × 200 employees × 30 days = 60,000 workflows per month**, then **× 12 = 720,000 per year**. The year's scenario is 360 days.

The monthly and yearly bars compare dated OpenAI, Anthropic and Google text API prices with **Nano electricity only and $0 per-token fees**. Open **Assumptions & pricing sources** to inspect rates and change electricity assumptions.

Electricity defaults: **200 Nanos, one per employee; 140 W each; 8 hours/day; $0.15/kWh**. That is **$1,008/month and $12,096/year**. These are editable assumptions, not measured wall power or capacity qualification. Hardware/support are excluded. Cloud bars exclude vision, images, audio, tools, discounts and taxes; model outputs differ. Annual figures hold the 18 November rates constant. Gemini's promotional rate ends November 30; this is not a future bill forecast.

<!-- pagebreak -->

# Keep it running
## Daily use, troubleshooting and sharing

### Everyday commands

Run commands from your installation folder:

```bash
./launch.sh free           # Open the interactive demo
./launch.sh stage          # Open the presenter kiosk
./launch.sh free status    # Inspect owned services and readiness
./launch.sh stage reset    # Reset the presenter session
./launch.sh stop           # Stop only this installation's owned stack
```

Use the desktop shortcut after setup. Run **one model stack at a time** on the Nano. Normal inference and interface assets are local; setup and missing-dependency repair need internet. Do not run setup during active jobs.

### If installation stops

Run `./install.sh --check` and address the named failed prerequisite. Ask your administrator to install ordinary Ubuntu prerequisites if needed:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates xz-utils \
  build-essential cmake pkg-config python3.12-venv \
  bubblewrap apparmor-utils util-linux libsndfile1 \
  libespeak-ng1 fonts-liberation fonts-noto-core xdg-utils wmctrl
```

The administrator command does not install GPU drivers or CUDA. If Chromium libraries are missing, inspect `.venv/bin/python -m playwright install-deps --dry-run chromium` and ask the administrator to install the reported libraries. The existing Chrome AppArmor profile must support Chromium's sandbox. Do not disable the sandbox, AppArmor or checksum checks.

**Interrupted download?** Rerun `./install.sh`; cached downloads are checked. **No browser?** Sign in to the local desktop and open the loopback URL. **Image task failed?** Close unrelated memory-heavy apps and use Retry unfinished work. **A model service failed?** Finish/cancel jobs, then use Recover local models in Free Mode. **Missing recordings?** Leave Require verified backups off for a normal live demo. Before an event, rehearse the entire show on the actual Nano/display.

### Share and update

Release and downloads: https://github.com/Navigatedhustle/hp-zgx-fury-showcase/releases/tag/v3.2.0-nano.3

Source branch: https://github.com/Navigatedhustle/hp-zgx-fury-showcase/tree/nano_exec

The share kit contains this PDF, the complete PDF guide, the source folder, release notes and checksums. Share the kit or the release link; never copy runtime logs, credentials, browser profiles or session data. To verify a downloaded file, put it beside `SHA256SUMS` and run `sha256sum --ignore-missing -c SHA256SUMS`.

For updates, finish all jobs and run `./launch.sh stop` before changing files. Select an explicit reviewed Nano release; rerun its installer. Never force-reset an installation containing your own edits. The complete guide covers updates, headless use, model licenses and backup recording.

**Verification:** This release passed source tests and browser checks for the new cost screen. A fresh-device cold installation was not repeated for this release; prior hardware results and remaining qualification limits are documented in `docs/NANO_GUIDE.md`. Setup prerequisites and model hashes remain enforced.
