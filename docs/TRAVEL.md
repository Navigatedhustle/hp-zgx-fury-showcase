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

Hardware acceptance commands (after launch):

```bash
.venv/bin/python ops/acceptance/showcase.py --wait-idle
# For a finished complete-travel run whose ID you obtained above:
.venv/bin/python ops/acceptance/travel-portal.py --run YOUR_RUN_ID
```

These browser checks perform demonstration writes in the selected run; use test-owned runs. Reports/screenshots remain private under `reports/`. API schema and examples appear in Factory's Backend panel; preview requests use the actual generated code, not mock responses.
