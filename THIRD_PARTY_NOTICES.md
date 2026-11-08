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

## V3 selected adapters, narrator and documents

The selected LongLive-Plug few-step and CFG adapters are Apache-2.0 at the immutable revisions in config/creative-models.json. They are fused only into the matching Wan2.2 TI2V 5B backbone. Both model cards and their licenses were directly reviewed; no annual-revenue restriction applies.

Kokoro's added am_michael voice uses the existing Apache-2.0 revision; its exact checksum and reviewed card are in docs/ASSET-MANIFEST.md. Atlas's af_heart voice is retained. pypdf is BSD-3-Clause, python-docx is MIT and ReportLab uses a BSD-style license. Installed Noto fonts retain their upstream SIL OFL terms; no additional licensed HP font is included. The original synthesized trailer soundtrack is created locally from oscillator tones, without a sampled recording. No weights, visitor media or downloaded FFmpeg/browser binaries are redistributed.

## Customer Skin dependencies and trademarks

The operator environment pins CairoSVG 2.9.1 (LGPL-3.0-or-later), cairocffi 1.7.1 (BSD-3-Clause), cssselect2 0.10.1 (BSD-3-Clause), tinycss2 1.5.1 (BSD-3-Clause) and webencodings 0.6.1 (BSD-3-Clause). SVG parsing uses defusedxml 0.7.1 (PSF-2.0), the owner's explicitly approved exception to the new-dependency license allowlist. Original dependency licenses are retained in `licenses/customer-skin/`; installed libraries and the host Cairo library are not bundled in source archives. Sources: https://github.com/Kozea/CairoSVG, https://github.com/Kozea/cairocffi, https://github.com/Kozea/cssselect2, https://github.com/Kozea/tinycss2, https://github.com/Kozea/webencodings, https://github.com/tiran/defusedxml.

Customer marks remain their owners' trademarks. Public-source availability does not grant general trademark rights. Use a customer logo only in a demo for that customer, next to the visible HP ZGX Fury identity, on screen only. Customer logos, names and palettes stay under ignored `state/skin/` and are excluded from source archives, documentation screenshots and downloaded application outputs. The original Northwind Beverages fixture mark is fictional project artwork and may appear in tests and documentation.

## GB10 stage qualification

The separately downloaded llama.cpp source is MIT at revision `7d7f0287530bc8981690f361d8c1627dbae1c99a`; source archive and LICENSE SHA256 are pinned in `config/gb10-build.json`. gpt-oss-120b MXFP4, Qwen3.6-35B-A3B with vision projector, FLUX.2 klein 4B, and Kokoro v1.0 use Apache-2.0 weights, pinned by file SHA256 and model-card revision in `config/model-files.json`. Directly reviewed publisher/converter sources and hashes are in `docs/ASSET-MANIFEST.md`. Source/model downloads and compiled binaries remain local, outside the source distribution. GB10 qualification does not select speech recognition, video, or Agent Factory.
