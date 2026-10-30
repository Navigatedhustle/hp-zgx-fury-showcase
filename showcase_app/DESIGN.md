# Fury booth interface

Lead lockup: official HP mark + HP ZGX Fury, followed by “powered by NVIDIA GB300”. Asset provenance is in assets/PROVENANCE.md. All visual assets and fonts are served locally; no CDN is needed. The event's approval documentation is not part of this repository.

Shared system: assets/design.css and ui.py. Archivo 400/700 for type, IBM Plex Mono for compact labels. Charcoal canvas #101112, surfaces #191b1d / #222527, white #f5f6f7, secondary text #b1b8bd. Green #a4d943 is reserved for primary actions and active work; blue denotes completed results and illustrative assumptions, amber denotes queues, pink denotes failures. Labels and borders distinguish states beyond color. Standard spacing follows 8px increments, panels use 24–28px padding, action targets are at least 44px, focus rings are visible.

Launcher: four equal choices, one primary action per card. Preview artwork is explicitly illustrative; the local image sample is labeled prebuilt. Product render and logos are unmodified official HP source assets.

Generation workspaces: native multiline brief, plain Enter adds a line, Ctrl/Cmd+Enter submits. Submit disables duplicate work immediately. Real request states drive queued / running / complete / failed styling. No timer estimates progress or tokens. Motion is decorative while a confirmed stage is active and never adds inference calls. Reduced-motion disables animations. Results retain editable export / image download, preview, retry, and launcher navigation.

Agent Factory: original SVG figures with five role silhouettes. The first three occupy a parallel group, then paths lead to the writer and same-model reviewer. A 0.7-second Streamlit fragment reads engine snapshots; it does not advance state or call a model. Queued, generating, complete, failed and cancelled/stopped are rendered separately. A live text summary outside the iframe supports screen readers. Existing Stop / Reset and audit exports remain authoritative.

Operator: on wide displays, measured work sits beside a clearly marked illustrative scenario. Narrow screens stack them. Source gateway events are the sole aggregate ledger; Agent Factory source calls upsert the same IDs. Slide ledger is diagnostic and never added again. Text output rate is known completed output / known completed text request wall time; images are excluded. Active and queued are actual health snapshots. Missing connections clear counters and scaled volume. Unknown usage remains visible.

Scenario: monthly multiplier × actual text-token mix × editable dated API price range. Local costs require hardware, amortization, powered hours, whole-system power, electricity, hosting, network and operations. Explicit zero is valid; blank is missing. Costs are assumptions and include no quality-equivalence claim. Image economics remain outside text. No payback is claimed.

Atlas: source inference, WebSocket, voice capture and playback code were left intact. Only navigation, authentic HP asset, focus targets, reduced motion and responsive header/footer CSS changed.
