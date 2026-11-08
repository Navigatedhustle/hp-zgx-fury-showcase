# V3.1.0 presenter script

## The customer skin moment — 20 seconds

“Who is in the room today? I’ll choose the official mark, check the colors and prepare every station. This is still HP ZGX Fury, built for your conversation. The models, security boundaries and generated applications stay the same. Your brand stays on screen and out of downloads.”

Open the demo and use the palette button directly. Presenter controls and settings do not require a PIN or station assignment. Confirm identity/logo, preview, and Apply. Pre-cache before an event or upload offline. [Full steps and privacy](CUSTOMER_SKIN.md).

Show the separate kWh chart on `/economics`. Cloud values require sourced, same-workload estimates; the display reports more **or less** electricity rather than assuming cloud consumes more. A higher API bill is not evidence of higher energy consumption.

Start at http://localhost:8080. Show the eight workload cards and the live GPU/HBM/Grace/power/token counters. “These are local measurements. The external AI counter covers this gateway, not every packet on the machine.”

| One-minute demo | Action and evidence |
|---|---|
| Atlas | Ask the 8-point Commit win-rate question. Show the grounded result, evidence and real audio-reactive orb. Explain that all business data is synthetic. Export the executive brief. |
| Presentations | Keep the included local-AI brief, press Create, inspect the three-slide preview and download editable PowerPoint. It is a draft requiring review. |
| Agent Factory | Choose short Live and automatic review. Start once, explain Plan → Build → Verify → Ready, then return after the real build. Open its tested application/backend. For a one-minute predictable story choose explicitly recorded Guided mode. |
| Image Studio | Choose a style, seed and ratio; generate, then change the batch to show serial variants. Use Send to Video for continuity. |
| Vision Lab | Pick the chart sample and Analyze. Compare actual values with the extraction and executive brief; samples are fictional. |
| Translate Desk | Use the brief sample, select a target and Translate. Compare pages and download PDF/DOCX/TXT. Show the advisory review and disclose clean reflow and variable language quality. The ten-page sample takes longer. |
| Video Studio | Choose text or an Image Studio reference, then generate five seconds. Show real steps, frames, model/adapters and elapsed time. This is a fixed proven preset. |
| Action Trailer | Read consent before camera access. Choose an original PG genre, capture once and show screenplay/keyframes/clips as they finish. Generation exceeds a minute. Tap final fullscreen with sound, then Done to visibly delete photo and video. |

## Cloud vs Local

Open `/economics` and show the Fury power versus cloud API bars. Change runtime or tariff, then edit the monthly workload. Explain that the initial 1,200 W, 40 hours and $0.25/kWh are illustrative inputs; the local bar excludes hardware/support. Cloud provider electricity is bundled into API charges. The graph is a cost scenario, not equal-quality or throughput evidence. Expand the dated official rates for details.

## Fury Rush

Press **Launch Fury Rush** once. “Six workflows are submitting through their real controls. One Factory build remains the global limit; visible queues preserve the workstation's admission limits.” Show DeepSeek/Qwen/FLUX lanes and measured throughput. Open completed workspaces without abandoning Factory. Wait for every tile to reach complete or failed; a failed tile is a real failure, not a canned replacement. The longest workload is the live Factory build.

## Privacy and recovery

Only Action Trailer's consented camera collects a visitor photo. No consent means no camera. Its photo and media are local, temporarily stored outside the repository, and deleted on Done/New/explicit deletion/idle/service startup. The browser receives a private preview; only localhost offers the final station download. Physical camera/microphone and remote device behavior require site validation.

Inspect `/models`, `/performance`, `/economics` and `/secure` for pinned identities, resources, sourced scenarios and code evidence. Electricity is GPU-only energy, not total ownership cost; cloud examples have different outputs/capabilities.

If a job fails, show its real state, preserve the evidence and retry only within the stated bounds. Inspect `./launch.sh status` and active jobs before guarded recovery. Do not restart a busy shared workstation or kill a process by port. All networking remains site-managed.

Historical presenter guidance follows for retained V2 features.

# Conference presenter guide — V2

The v2.3 visual edition upgrades new generated travel applications and the supplied Guided interface. Keep the distinction explicit: short builds generate application code live, with labeled supplied artwork; complete travel supplies its frontend and generates backend/QA. Focus product expands the checked application while retaining compact progress/token information. Existing saved applications keep their original files.

Atlas's voice orb responds to actual local speech and microphone audio. It enlarges while speaking/listening, pauses with audio and rests after speech. Hold it using a pointer, Space or Enter to ask; pause/resume/mute and typed questions remain available. Refresh the browser to load the new renderer. Reduced-motion settings and hidden-workspace rendering limits are respected. Physical microphone/speaker quality still depends on the presenting device.

On each device, open `/stations` on the dashboard host. Choose Economics, Why HP, or Interactive and press Assign this screen. This stores only that browser's role. Bookmark `/operator`, `/why-hp`, or `/demos` for direct access. Present fullscreen is optional; use its Exit control or Escape.

Recommended arrangement: one large Economics display, one Why HP display, and two visitor laptops on All demos. The laptops can choose different demos independently. Shared inference remains bounded: one Live Factory build, two development requests, four gateway admissions with an Atlas reserve. More endpoints do not increase those limits.

The chooser keeps its opened workspaces mounted. All demos switches views without cancelling their jobs or disconnecting their streams. Refresh reconnects using the same browser session; a new browser cannot inherit private Factory controls. Direct component bookmarks remain supported; their All demos link opens a chooser tab to preserve the original work.

Factory opens in short travel mode from the conference chooser. Live creates new code using the original models and checks. Guided is clearly recorded and produces no live inference. Application, Backend, and Development tabs share one retained preview and its original isolated backend. Refresh validated preview only when ready to move to a newer checked version.

Economics counts actual terminal live calls with reported usage, including known usage of failed calls. Final output totals can jump as responses finish; there is no invented live token rate. Recorded playback is excluded. API estimates reprice observed text tokens, and GPU energy includes measured session idle power. GPU electricity is not the complete Fury power bill or ROI. Expand Assumptions for dated sources and browser-local tariff/currency settings.

Reset the event window through the host shell:

```bash
.venv/bin/python ops/event-session.py reset --name "My conference"
```

For a browser reset, open **Assumptions & presenter controls** on `/operator`, enter an event name and confirm **Reset event session**. No PIN or presenter code is required. Reset changes the shared counter window and restores the default skin, preserving station assignments, jobs and artifacts. Clearing a station assignment is a separate local action on `/stations`.

## Working demo flows

Open the home page, then choose Demos for direct launch actions. All examples use fictional data. Ask the customer which task and operating constraint matters first.

1. Atlas: copy the forecast question. Inspect grounding, compare a scenario, export PNG/PDF. Explain that inference supports the analytical tools; a fluent answer still needs review.
2. Presentations: use the catalog brief, generate three slides, inspect preview, download/edit the PPTX. Explain the first-draft use case.
3. Agent Factory: start automatic short travel mode. Inspect real model requests, tasks and tests. Show the application and backend. Complete mode supplies its frontend and generates backend/QA; disclose that. A prebuilt reference is never a new generation.
4. Image Studio: use the botanical prompt. Inspect/download the image. Discuss quality and human review.

For shared AI, start the Factory build first, then submit the other three workflows while it generates. Separate sessions retain ownership; one Factory build is admitted globally. Show actual activity in Operator. Simultaneous submission is not proof of backend overlap; the acceptance harness records execution intervals.

Talk track: “Which of these tasks would benefit from local model access? Where would the system sit? Who operates its models? What must be tested before deployment?” Use Why HP ZGX Fury for the sourced system/software discussion. Toolkit/Runtime are available HP capabilities; this demo runs its existing gateway/vLLM stack.

Before a session, run ./launch.sh status; confirm all ten ready and no prior active Factory job. Never cancel another user's work. Factory reconnects in the same browser session; its Stop button cancels only that session's run. Capacity errors are expected when another build owns the system. Inspect error evidence before retrying.

Recovery: ./launch.sh diagnostics, then guarded ./launch.sh recover agent once idle. Do not restart the entire model stack to recover a tab. Health alone does not prove successful generation. Keep access private. Physical microphone/speaker and remote browser permissions depend on the presenting device.

Expected timing varies with input, caches and queues. Allow several minutes for short development; complete travel takes longer. See VERIFICATION.md and V2-VERIFICATION.md for observed results and scope.

## Hardened release operations

Use the [fresh Fury guide](FRESH_FURY_GUIDE_v3.1.0.md) and its [PDF](FRESH_FURY_GUIDE_v3.1.0.pdf) for installation and site validation. Keep approved users on localhost, SSH or the organization’s private HTTPS network. Presenter controls remain directly available without a PIN. Host/Origin rejections indicate a mismatched deployment hostname; configure its exact approved name rather than weakening guards. Queues, upload/parser/connection limits and isolated previews can reject unsafe or oversized work with a visible error. Review the result and wait for available capacity.

Only fictional Northwind screenshots are distributed. Check actual cameras, microphones, speakers and remote devices at your site; same-host automated browser tests do not certify them. For security reports use [private vulnerability reporting](https://github.com/Navigatedhustle/hp-zgx-fury-showcase/security/advisories/new), with visitor data and credentials removed.
