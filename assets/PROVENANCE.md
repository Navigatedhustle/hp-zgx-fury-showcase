# V3 fictional sample provenance

The five editable SVG images in `showcase_app/assets/vision-{chart,whiteboard,document,defects,scene}.svg` are original code-authored fixtures distributed under this repository's MIT license. They contain fictional quantities, plans, documents and illustrated objects. No photographs, real people, customer records, external images, model-generated raster media or third-party brands were used. The browser rasterizes them locally when sending a sample to Qwen vision.

`examples/v3/operations-plan.txt` and `examples/v3/product-brief.txt` are original fictional documents under the same MIT license. `showcase_app/samples.py` renders the operations sample as ten distinct numbered PDF pages and the product brief as two pages. PDF files are generated on this machine from included source; they are not bundled runtime artifacts.

All video qualification portraits, reference edits and generated clips remain outside Git and source archives. Action Trailer visitor photos, keyframes, audio and videos remain only in the private per-session temporary directory and follow AGENTS.md deletion rules. UI screenshots committed for verification must not contain real visitor media.

## GB10 stage vision qualification

`samples/stage/vision/whiteboard.png` and `chart.png` are original deterministic drawings from `ops/render-gb10-samples.py`, authored for this repository under MIT. They use the existing local Liberation Sans font. Northwind and every owner, action, date, count and chart value are fictional test data; no photograph, real account, employee, event detail or external image is used. `expected.json` is the exact extraction truth for model quality qualification. The whiteboard is a marker-style drawing and must be described as a shipped sample, never a live camera capture.
