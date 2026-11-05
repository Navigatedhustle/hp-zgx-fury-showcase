# Conference presenter guide — V2

The v2.3 visual edition upgrades new generated travel applications and the supplied Guided interface. Keep the distinction explicit: short builds generate application code live, with labeled supplied artwork; complete travel supplies its frontend and generates backend/QA. Focus product expands the checked application while retaining compact progress/token information. Existing saved applications keep their original files.

Atlas's voice orb responds to actual local speech and microphone audio. It enlarges while speaking/listening, pauses with audio and rests after speech. Hold it using a pointer, Space or Enter to ask; pause/resume/mute and typed questions remain available. Refresh the browser to load the new renderer. Reduced-motion settings and hidden-workspace rendering limits are respected. Physical microphone/speaker quality still depends on the presenting device.

On each device, open `/stations` on the dashboard host. Choose Economics, Why HP, or Interactive and press Assign this screen. This stores only that browser's role. Bookmark `/operator`, `/why-hp`, or `/demos` for direct access. Present fullscreen is optional; use its Exit control or Escape.

Recommended arrangement: one large Economics display, one Why HP display, and two visitor laptops on All demos. The laptops can choose different demos independently. Shared inference remains bounded: one Live Factory build, two development requests, four gateway admissions with an Atlas reserve. More endpoints do not increase those limits.

The chooser keeps its opened workspaces mounted. All demos switches views without cancelling their jobs or disconnecting their streams. Refresh reconnects using the same browser session; a new browser cannot inherit private Factory controls. Direct component bookmarks remain supported; their All demos link opens a chooser tab to preserve the original work.

Factory opens in short travel mode from the conference chooser. Live creates new code using the original models and checks. Guided is clearly recorded and produces no live inference. Application, Backend, and Development tabs share one retained preview and its original isolated backend. Refresh validated preview only when ready to move to a newer checked version.

Economics counts actual terminal live calls with reported usage, including known usage of failed calls. Final output totals can jump as responses finish; there is no invented live token rate. Recorded playback is excluded. API estimates reprice observed text tokens, and GPU energy includes measured session idle power. GPU electricity is not the complete Fury power bill or ROI. Expand Assumptions for dated sources and browser-local tariff/currency settings.

An authorized presenter can reset only the event window through the host shell:

```bash
.venv/bin/python ops/event-session.py reset --name "My conference"
```

For a browser reset, retrieve a private presenter code in your SSH terminal using `.venv/bin/python ops/event-session.py presenter-code`. Enter it only in the protected reset form. Keep it out of shared documentation. Reset affects every Economics display's counter window, not station assignments, jobs, or artifacts. Clearing a station assignment is a separate local action on `/stations`.

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
