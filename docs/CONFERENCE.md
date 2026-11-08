# Conference operation and economics

## Three independent screen roles

The dashboard service on 8080 serves `/operator` (Economics), `/why-hp` (Why HP), `/demos` (interactive chooser), `/stations` (assignment), and `/presenter` (short walkthrough). The root is a default chooser or restores a browser-local assigned passive role. A direct bookmarked URL always wins. The existing private HTTPS proxy on 443 serves these same paths. Demo service ports remain unchanged.

Assignments use `localStorage` key `fury-station-v2`; no server variable selects a global screen. Different devices/profiles are independent. Same-origin tabs in one browser share an assignment preference, but no storage listener remotely navigates an already-open tab. Changing a role takes effect only in the window where Assign is pressed. Clear assignment removes only that browser preference.

The chooser lazily opens the selected existing application in a retained frame. Returning to All demos hides, rather than unloads, the workspace, preserving streams, active jobs, and previews. Each application keeps its existing cookies, APIs, worker, queue, reconnect and cancellation behavior. Direct component links remain valid. Factory's Application/Backend/Development tabs do not replace its checked preview. Preview refresh still requires the original explicit action.

## Laptop layout and accessibility

Test the browser's content viewport at 100% zoom, not the physical panel resolution. Primary: 1366×768 CSS pixels. Additional: 1280×720, 1440×900, 1920×1080; reduced-height 1366×640 and 1280×620 account for browser chrome and scaling. The shared logo keeps its supplied 48px size and 12px clear space; the shell is 72px high. Measured visualViewport height drives the available workspace height. No scale transform, zoom change, automatic fullscreen, or removal of essential controls is used.

Expandable settings and evidence are retained. Long conversations, source evidence, code, backend output and generated applications use contained scrolling. Tab controls support keyboard arrows, named panels, visible focus, and reduced motion. Mobile widths may use natural document scrolling. Optional fullscreen is explicit and can be exited with the visible control or Escape.

## Measurement definitions

`/api/event` returns aggregate data only: current event window, measured token totals, anonymous activity counts, energy, and price scenarios. It never includes prompts, generated application source, private run controls, or another visitor's content. `/api/live` remains available for existing operator integrations, using the same cached service sample. One sampler runs every five seconds on the existing dashboard process; opening more viewers does not start models or more samplers.

Tokens: each gateway `events.id` identifies one physical upstream request. Source-ledger imports upsert the same identity; their totals are never added separately. Only terminal live text requests with reported numeric usage are counted. Output can be counted when known; API repricing requires both input and output. Missing/unfinished usage is unavailable, never zero-filled. Recorded Guided calls have no gateway inference requests and are excluded. Image/audio output is not assigned a text-token API equivalent.

Time range: requests must start on or after the current event reset. Requests already in flight at reset are outside the new window. Event history survives dashboard restart. Reset creates a new session; it does not delete old measurement sessions, the gateway ledger, artifacts, jobs, or application data.

Energy: default input is `nvidia-smi power.draw`, explicitly GPU-only. Integrate adjacent real readings using `(previous W + current W) / 2 × elapsed seconds / 3600000`. Missing readings, backward clock jumps, and gaps over 20 seconds are unmeasured. Downtime is not filled with the last instantaneous power. Measured coverage is shown; idle energy within the session is included. A GPU reading cannot establish whole-system electricity consumption.

Optional whole-system input: set `FURY_POWER_METER_FILE` on the host to an absolute path produced by your actual wall-meter integration. Its JSON must contain finite nonnegative `watts` and a Unix `timestamp` no more than 15 seconds old. An unavailable configured meter stays unavailable; it never silently changes to GPU scope. Different scopes are accumulated separately. No wall meter is bundled or claimed tested on this host; parsing, freshness, scope changes, and missing measurements have fixture coverage.

Electricity estimate = measured-scope kWh × presenter-supplied tariff. Defaults are USD 0.25/kWh, a planning assumption, not a verified tariff. Currency and explicit currency-per-USD conversion are stored in that browser; no live exchange feed is required. Hardware, cooling beyond meter scope, staffing, hosting, utilization and amortization are excluded. No ROI or break-even figure is displayed.

## Sourced API scenarios

Prices are locally cached in `config/event-pricing.json`, verified 2026-11-04. Standard text rates in USD per million input/output tokens:

| Model | Input | Output | Official source |
|---|---:|---:|---|
| GPT-6 Astra | 10 | 50 | https://developers.openai.com/api/docs/models/gpt-6-astra |
| Claude Opus 5.5 | 4 | 20 | https://platform.claude.com/docs/en/about-claude/pricing |
| Gemini 4 Argon | 2 | 10 | https://aistudio.google.com/docs/pricing#gemini-4-argon |

GPT-6 Astra requests above 272K input use 20/75 for the full request. Gemini's promotion ends 2026-11-30; the cached rule changes to 4/20 on 2026-12-01 without internet. No local cache hit is treated as proof of provider cache eligibility. Cache discounts/writes, batch, tools, taxes and regional premiums are excluded. Tokenizers, thinking usage, model quality, latency and task success differ; this is a pricing scenario, not a bill or measured quality comparison. No paid provider request populates the graph.

## Presenter authorization

Event reset is available through `.venv/bin/python ops/event-session.py reset --name "Event"` or the browser's **Assumptions & presenter controls** form. No presenter code, PIN, account or role assignment is required. The browser asks for confirmation. Reset starts a new shared counter window and restores the default skin, preserving jobs, artifacts and station assignments. Unrelated website origins cannot submit browser mutations.

## Rollback

Wait for all jobs to become idle and back up runtime outputs before changing releases. Choose this rollback only when required; status/start/stop are separate operating choices.

```bash
./launch.sh stop
git switch --detach v2.1.1
./launch.sh setup
./launch.sh
```

Existing model downloads and generated applications remain in their ignored runtime directories. The additive event database can remain unused by the previous release. Do not copy process registries between installations. No Tailscale policy or Serve-route rollback is needed for this UI release.
