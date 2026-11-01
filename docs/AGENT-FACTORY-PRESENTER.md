# Agent Factory presentation

Choose a mode and project, press Start once, follow Plan → Build → Verify → Ready, then open the application. Advanced controls hold retained-run recovery, reset and optional human review. Technical details contain the original role/task dependency evidence, model identities, files and logs. The supplied full travel frontend is disclosed; the backend and QA are generated in Live mode. Short projects generate frontend code too. The editorial short project uses a different design brief against the same API contract.

## Live build

The existing DeepSeek V4 Flash lead and Qwen3.6 27B specialist serve actual requests. Complete travel tickets execute sequentially against preceding merged files. Short builds can overlap independent tickets within the existing two-request cap. Stage labels summarize actual task/check states; no animated worker implies an extra model request.

Start saves a durable job before its worker starts. A browser disconnect does not cancel it. The same browser profile/cookies reconnects; another profile cannot inherit its job or inspect its execution stream. One live Factory build is admitted, and another gets HTTP429. Generated application account authorization is enforced in its backend. Deliberately shared application URLs remain separately usable, with their own app sign-in; they do not grant run controls or private orchestration access.

The first travel preview requires independent backend acceptance, generated QA and a browser bootstrap check. Full browser/persistence acceptance determines completion. There is no cumulative token cutoff. Travel QA has a bounded8192-token per-call allowance constrained by exact prompt/context headroom; ordinary lead tickets retain6000. Rejected syntax is staged read-only for its retry and never promoted. Backend integration must start and answer its real sandbox health request before merging; QA discovery errors return to the repair loop. A checked preview stays pinned to its version's files and backend while new versions build; the presenter explicitly refreshes to promote the visitor's view. A later failed check retains working versions. Refresh can reset the visitor's in-progress form, so do it between interactions. Business state persists in the per-run database.

## Guided demonstration

Guided mode replays a curated authentic successful travel run: twelve recorded model requests, corresponding checked application files and sanitized milestones. The original run lasted about429.8seconds and is compressed into120seconds. Recorded events, timing and endpoint totals are labeled throughout. No model requests or live output/GPU rates are produced by playback. The curated application artifact replaces private runtime imagery with public local vector scenes; its generated backend and recorded usage are unchanged. It is available immediately and uses fresh per-run demonstration data. Playback and using the artifact are separate activities. Four recordings are admitted at a time; the functional backend has its existing bounded CPU request slots.

## Metrics

- Cumulative input: sum of endpoint prompt_tokens for this run's unique requests, including repeated context. Missing usage is explicitly unavailable.
- Cumulative output: sum of endpoint completion_tokens, including the serving engine's reported output categories. Final endpoint totals are authoritative. An interrupted request without a final response has only a last observed lower bound; the unresolved total is marked unavailable.
- Current output generation rate: sum of observed per-request output-token increments in a five-second observation window for currently generating requests. Requests share the same observation window; completed calls do not keep animating. Final-only usage cannot establish a live rate. This is distinct from output divided by whole-job elapsed time, which includes waiting and tools.
- Generating / queued: current request states for this run, not unrelated gateway work or idle logical roles.
- Elapsed: wall time from durable job start to terminal event, including tools/waits. Terminal elapsed freezes and stored usage survives reconnect/restart. Resuming a sustained run retains its original start.
- Model identity: readiness checks compare serving aliases, loaded paths and pinned revisions. The detailed panel displays the evidence and distinguishes unknown identity.

SSE retains one-second sampling, ordered job/event identifiers, timestamps and browser reconnect. Reconnect sends an authoritative snapshot rather than replaying token increments into cumulative counters. Main updates omit large code diffs/history, and token-only samples do not rebuild the detailed DOM. Detailed code is fetched when requested. No browser animation creates inference requests. Reduced motion disables visual activity effects.

## Recovery

Cancel stops only the current browser's job; accepted upstream work can take time to release. Keep checked output open during repairs. Resume retained run continues sustained travel from merged files. A short blocked run can be rerun. Service restart reconciles interrupted jobs, preserving artifacts and app data. Use launch status/diagnostics/recover only after checking current work. Recordings never resume as live inference after restart.
