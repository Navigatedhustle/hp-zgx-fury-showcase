# V2 verification

Candidate validation is being completed before v2.0.0 publication. V1 remains immutable at v1.0.0 / e98c85ee26169a6d745de775feea049ae7a3dc63. This file will record the final acceptance results before release.

## Scope and unchanged contracts

The presentation layer is isolated from the model/gateway state. Model revisions, inference settings, admission limits, APIs, streaming, cancellation, artifact storage and application session ownership are preserved. The only Atlas backend addition mounts the shared local static assets. New booth slides use a neutral light template and official logo asset; historical decks and generated customer applications are not rewritten. The setup stamp now includes editor source so an upgrade rebuilds the editor. Existing source-only regression suites and two setup-stamp regressions cover these changes.

Routes remain: dashboard / on 8080; /operator and /connect on 8080; Atlas / on 8200; presentations /booth and full React editor / on 8765; Factory /devteam and /devteam/build on 8501; images / on 8800. Generated application and backend routes retain their original sandbox/session contracts. Model endpoints remain 8000/8100, gateway 8001, ASR 8202 and TTS 8204. Shared artwork is /showcase-assets. Private networking configuration and raw operational records are deliberately excluded from public documentation.

V1's source/dependency/model and clean-install evidence in VERIFICATION.md is reused for unchanged backend behavior. V2 tests share the existing tested workstation OS/driver/toolkit. No second hardware platform or fresh GPU provision is claimed. Current private serving budgets remain those of the preserved live deployment (176 GiB nominal lead); public launch retains V1's tested 168 GiB public lead allocation. Comparisons use the same live model processes and settings on both sides.
