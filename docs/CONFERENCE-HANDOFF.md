# Conference V2 continuation

Read AGENTS.md, ARCHITECTURE.md, CONFERENCE.md, HP-DESIGN.md, HP-CLAIMS.md, and CONFERENCE-VERIFICATION.md. This is a presentation/telemetry layer on the original controller, applications, sandbox and gateway. Preserve model pins, concurrency, artifacts and private access.

Routes: `/stations` assigns a browser-local role; `/operator` Economics; `/why-hp` Why HP; `/demos` retained interactive chooser. No server-global selected view exists. Monitor data is shared, navigation is not. Event reset is separate from station reset.

Validation commands: `bash ops/test-source.sh`; `.venv/bin/python ops/acceptance/conference.py --output /private/evidence`; `.venv/bin/python ops/acceptance/showcase.py --wait-idle --width 1366 --height 768 --atlas-drop 11 --output /private/evidence`. Wait for idle before application recovery. Never start a second model stack or cancel another presenter's work. Raw evidence and owner cookies must remain outside publication input.

Packaging uses the explicit distribution list and SOURCE-SHA256SUMS. Review selected source and redistributable assets, refresh the inclusion/checksum manifest, run source/secret checks, then package v2.2.0. Preserve all previous tags/releases. Rollback is the idle/backed-up v2.1.1 sequence in CONFERENCE.md. Site-specific URLs, checkpoints, runtime backups, raw evidence and current progress belong in the external private handoff, not this public file.
