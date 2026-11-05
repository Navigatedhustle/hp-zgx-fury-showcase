# Agent Factory travel workflows

The full [travel product specification](../examples/travel-specification.md) is the exact immutable contract in `travel_spec.py`. It includes accounts/session expiry, searchable listings, favorites, itineraries, server-side quote calculations, demonstration reservations and role-checked inventory administration. Public fictional admin: `admin@example.test` / `DemoAdmin2028!`. Do not enter real records/passwords.

Open http://localhost:8501/devteam. The short demonstration generates a five-hotel booking site with a newly authored frontend/backend and independent QA. Its architecture, backend, frontend, accessibility, integration and repair roles use actual local DeepSeek/Qwen calls. The simulated people/agent roster represents orchestrated roles, not real employees.

Select complete travel mode for the broader specification. Its maintained `travel_portal/` HTML/CSS/JS foundation is **supplied without inference**, explicitly recorded in the run audit. Vector destination scenes are bundled. DeepSeek generates the Python/SQLite modules, architecture and tests. Qwen is the configured specialist for frontend repair tasks when needed; supplied frontend tasks do not count as model calls. The UI does not claim the supplied frontend was generated live. Existing workspaces are never overwritten by foundation initialization. A generated API is exercised in new networkless processes on each request, so acceptance checks prove actual database commits/persistence.

CLI for a session-owned complete run:

```bash
python3 ops/factory-travel.py start
python3 ops/factory-travel.py status
python3 ops/factory-travel.py status --full
python3 ops/factory-travel.py stop
python3 ops/factory-travel.py resume
```

The CLI stores its own private cookies under `state/`; the browser has a different session unless explicitly attached through its watch link. It cannot cancel another visitor's work. Run IDs, source/version/test panels, backend examples and the application URL are shown by the UI/API. Inspect source and errors before resuming a failed run. Automatic mode advances declared review gates, not arbitrary host commands. Long runs can fail or stagnate; each ticket has three attempts and repeated failures block further work; context/output/call limits remain bounded. Sustained mode has no overall token budget.

A successfully accepted development preview can remain available while subsequent candidates fail; it is labeled as a preview. A run reports finished only after its acceptance criteria pass. The maintained portal's visual shell and runtime documentation are included; private locally generated photography, old model responses, session records and old application databases are excluded.

The [prebuilt reference](../examples/reference-travel/README.md) has its own server and database and a permanent label. It demonstrates an existing accepted backend with the supplied vector portal. It never enters the new-run workflow or satisfies a generation acceptance test.

## Enterprise visual edition

Fresh short projects use `enterprise_design.py` to author their actual HTML/CSS/JavaScript with a premium travel identity, rich imagery, real inventory filtering and clear booking controls. A final Visual acceptance ticket applies bounded exact edits to frontend files, then exercises the real backend in empty and populated reservation states. Local axe-core checks and desktop/mobile overflow checks must pass along with the existing booking, conflict and persistence checks. Earlier checked previews remain available during repairs; a failed visual gate does not report Ready.

Short builds may use the supplied fictional hero through `window.furyArtwork.hero` and `--fury-artwork-hero`. The image is pinned and checksum-verified per new run, kept out of model context, and labeled supplied. Preview and independent browser validation receive the same artwork. This adds no network access or live image inference. Existing runs without a pinned image keep their original source/environment. Application code and original SVG details are authored by local models; supplied artwork is not counted as generated code or image output.

Complete-travel and Guided use the visually refreshed supplied frontend, with a fictional Mediterranean hero and six original destination illustrations. Guided retains its original recorded backend, QA and usage; the refreshed frontend is explicitly supplied presentation work. Older generated applications are not overwritten. See the artwork provenance file and enterprise verification for exact testing scope.

Hardware acceptance commands (after launch):

```bash
.venv/bin/python ops/acceptance/showcase.py --wait-idle
# For a finished complete-travel run whose ID you obtained above:
.venv/bin/python ops/acceptance/travel-portal.py --run YOUR_RUN_ID
```

These browser checks perform demonstration writes in the selected run; use test-owned runs. Reports/screenshots remain private under `reports/`. API schema and examples appear in Factory's Backend panel; preview requests use the actual generated code, not mock responses.
