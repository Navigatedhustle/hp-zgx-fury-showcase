# Source ownership and third-party notices

## V3 qualification runtime additions

Wan2.2-TI2V-5B uses its publisher's Apache-2.0 Diffusers serialization; pinned revisions and reviewed model-card links are in `docs/ASSET-MANIFEST.md` and `config/creative-models.json`. Downloaded weights are not redistributed in Git or source archives.

ImageIO-FFmpeg 0.8.1's Python wrapper is BSD-2-Clause. Its separately executed ARM64 FFmpeg binary reports GPL-3.0-or-later; commercial use is permitted without an annual-revenue threshold. The wheel and binary are installed into local environments, not bundled in Git or release ZIPs. Exact download/binary hashes and version are in `config/creative-tools.json`; upstream source and terms: https://github.com/imageio/imageio-ffmpeg and https://ffmpeg.org/legal.html.

Wan text normalization additionally uses ftfy 6.3.1 (Apache-2.0) and wcwidth 0.2.13 (MIT), pinned in the model environment lock. The creative worker calls the host's existing libnuma interface for its own CPU allocation policy; no host policy or library is redistributed or changed.

The source distribution follows the existing Atlas MIT license. The preserved ownership record states that first-party ownership across the discovered projects was confirmed by the owner on 2026-10-10; the owner explicitly authorized public distribution on 2026-10-30. This license covers project-authored integration, examples, prompts and generated demonstration code. It does not license third-party names, marks, weights or dependencies beyond their own terms.

HP, NVIDIA, GB300, DeepSeek, Qwen and other names identify their respective products/owners. This community demonstration does not imply support, endorsement or a trademark license. Product photos and vendor logos with no recorded redistribution permission were excluded and replaced by neutral original diagrams. Historical source comments may mention brand styling; included neutral assets govern this public build.

Vendored Chart.js retains `build/sources/atlas-gpt-main/static/chart.LICENSE.md`. Archivo, IBM Plex Mono, and Liberation Sans are under SIL OFL 1.1; complete notices are in `licenses/`. Font copies in the app, presentation runtime and editor are covered by those notices. The labeled synthetic image sample and vector artwork are demonstration assets supplied by this project. Private runtime destination photography is excluded.

Models are downloaded separately under their upstream licenses; exact sources and revisions are in [the asset manifest](docs/ASSET-MANIFEST.md). Upstream model cards/licenses download alongside weights where available. Python dependencies include FastAPI (MIT), PyTorch (BSD-style), vLLM/diffusers/transformers/Playwright (Apache-2.0), NumPy (BSD), Pillow (MIT-CMU), SQLAlchemy (MIT), python-pptx (MIT) and sherpa-onnx/Kokoro (Apache-2.0). Chromium and its third-party notices accompany the Playwright browser download. These are not relicensed by this repository.

The frontend bundles React/React DOM (MIT), Vite tooling (MIT), dnd-kit (MIT), Radix (MIT), TanStack Query (MIT), Sigma/Graphology (MIT), and Lucide (ISC), among others. Exact versions and registry integrity values are in package-lock.json. `licenses/npm/` retains installed npm license/notice files, and `licenses/dependency-inventory.json` records installed dependency license metadata. Metadata is an inventory, not legal advice or a blanket compatibility claim. Source release excludes environments and node_modules; dependencies are installed from upstream distributions with their original notices.

Inactive historical Atlas engines and optional presentation model launch scripts are retained as source for context; their models are not active requirements. Historical Atlas LICENSES.md describes those old variants and must not be interpreted as the current launch profile. Use the root asset manifest for active requirements.

## Local visual validation and artwork

The enterprise visual review uses unmodified axe-core 4.11.0 from Deque Systems, distributed under Mozilla Public License 2.0. Its original copyright header and license are retained in `build/sources/fury_agent_factory/vendor/axe/`. It runs locally during browser validation, without telemetry or an external service.

The fictional Mediterranean hero is original AI-created supplied artwork, generated for this project on 5 November 2026. Its prompt/origin are documented in `build/sources/fury_agent_factory/travel_portal/assets/PROVENANCE.md`. Original destination SVG illustrations are authored in `travel_art.py`. These public illustrative assets are distinct from private runtime photography and from live image generation during a visitor's build.

## HP identity in V2

The official HP Electric Blue logo with white keyline is an unchanged asset supplied by the owner for this HP demonstration. HP trademarks remain HP property; the source MIT license does not cover the mark or confer general trademark permissions. No licensed HP fonts are distributed.
