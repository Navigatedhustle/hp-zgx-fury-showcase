# Atlas licenses and attribution

Atlas source and generated synthetic data: MIT. No AGPL or non-commercial weights are used at runtime. Model cards and notices are saved in `eval/model-cards/` and in the local Hugging Face snapshots. Downloads are installation-time only.

## Models and bundled runtimes

| Asset | License | Source / status |
|---|---|---|
| NVIDIA Nemotron 3.5 Lightning 30B-A3B BF16 / official Q4_0 GGUF | OpenMDW 1.1 | nvidia official source and ggml-org conversion; primary local brain |
| NVIDIA Nemotron 3.5 ASR Streaming 0.6B INT8 GGUF | OpenMDW 1.1 | NVIDIA model card; primary local recognition |
| NVIDIA Magpie TTS multilingual v2607 | NVIDIA Open Model License | NVIDIA model card; downloaded and tested; inactive after latency fallback |
| NVIDIA NanoCodec decoder | NVIDIA Open Model License | Companion to Magpie |
| Kokoro 82M v1.0 / optional ONNX conversion | Apache 2.0 | hexgrad source and onnx-community conversion; active GPU speech fallback; optional ONNX source inactive |
| Kev-4B adapter and pointer head | Apache 2.0 | jaredpalmer model card; typed decision model |
| Qwen3.5-4B-Base | Apache 2.0 | Backbone for the decision model |
| RF-DETR Nano | Apache 2.0 | Roboflow Nano model; active local person detection |
| llama.cpp | MIT | Bundled ARM64 CUDA binary; upstream licenses retained |
| NeMo-Speech.cpp | Apache 2.0 | Bundled ARM64 CUDA binary; release checksum verified |
| Chart.js 4.5.1 | MIT | Vendored `static/chart.umd.js`, notice `static/chart.LICENSE.md` |
| CMU pronunciation dictionary | BSD-style, permissive commercial use | Local fallback phonemes; notice `models/cmudict.LICENSE` |

The host NVIDIA driver/CUDA stack and installed system fonts are existing platform components, not redistributed as Atlas assets. Browser UI requests Arial/Helvetica only; exported images use the installed metrically compatible Liberation Sans font (SIL Open Font License), and PDF uses locally rendered pixels. No fonts are downloaded at runtime.

Unused phonemizer/GPL and LGPL text-normalization packages brought in during an abandoned fallback experiment were uninstalled. The active Kokoro fallback uses Misaki English (Apache 2.0), the installed English tagger (MIT), and Atlas number formatting (MIT). Its optional multilingual phonemizer imports are bypassed; no GPL phonemizer backend is loaded. The separate CMU/ONNX fallback source is inactive.

## Installed Python environment

Exact installed versions are in requirements.lock. This includes optional/development packages as well as the active stack. License metadata and bundled notices are retained for inspection. Platform dependencies can have permissive PSF, ISC, Zlib or MPL notices; no AGPL or non-commercial model license is present.

| Package | Version | License metadata |
|---|---|---|
| accelerate | 1.15.0 | Apache |
| addict | 2.4.0 | MIT (bundled LICENSE verified) |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| av | 19.0.1 | BSD-3-Clause |
| babel | 2.18.0 | BSD-3-Clause |
| blis | 1.3.3 | BSD |
| catalogue | 2.0.10 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cloudpathlib | 0.26.0 | License :: OSI Approved :: MIT License |
| cloudpickle | 3.1.2 | BSD-3-Clause |
| confection | 1.3.3 | MIT |
| contourpy | 1.4.0 | BSD-3-Clause |
| csvw | 4.1.0 | Apache 2.0 |
| curated-tokenizers | 0.0.10 | MIT |
| curated-transformers | 0.1.1 | MIT |
| cycler | 0.12.1 | Copyright (c) 2015, matplotlib project (full notice bundled) |
| cymem | 2.0.13 | MIT |
| defusedxml | 0.7.1 | PSFL |
| dlinfo | 2.0.0 | MIT |
| docopt | 0.6.2 | MIT |
| en_core_web_sm | 3.8.0 | MIT |
| fastapi | 0.142.4 | MIT |
| filelock | 4.0.12 | MIT |
| flatbuffers | 25.12.19 | Apache 2.0 |
| fonttools | 4.66.1 | MIT |
| fsspec | 2026.9.0 | BSD-3-Clause |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| h11 | 0.16.0 | MIT |
| hf-xet | 1.7.0 | Apache-2.0 |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httptools | 0.8.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.13.1 | BSD-3-Clause |
| huggingface_hub | 1.33.0 | Apache-2.0 |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| isodate | 0.7.2 | Copyright (c) 2021, Hugo van Kemenade and contributors (full notice bundled) |
| Jinja2 | 3.1.6 | License :: OSI Approved :: BSD License |
| joblib | 1.6.0 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| kiwisolver | 1.5.1 | ========================= (full notice bundled) |
| kokoro | 0.9.4 | Apache License (full notice bundled) |
| language-tags | 1.3.1 | MIT |
| loguru | 0.7.3 | License :: OSI Approved :: MIT License |
| markdown-it-py | 4.2.0 | License :: OSI Approved :: MIT License |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| matplotlib | 3.11.2 | License agreement for matplotlib versions 1.3.0 and later (full notice bundled) |
| mdurl | 0.1.2 | License :: OSI Approved :: MIT License |
| misaki | 0.9.4 | Apache License (full notice bundled) |
| mpmath | 1.3.0 | BSD |
| murmurhash | 1.0.15 | MIT |
| narwhals | 2.26.0 | MIT |
| networkx | 3.7 | BSD-3-Clause |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| onnxruntime | 1.30.0 | MIT License |
| opencv-python-headless | 5.0.0.93 | Apache 2.0 |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| peft | 0.21.2 | Apache |
| pillow | 12.3.0 | MIT-CMU |
| pip | 24.0 | MIT |
| playwright | 1.63.0 | Apache-2.0 |
| pluggy | 1.6.0 | MIT |
| preshed | 3.0.13 | MIT |
| protobuf | 7.36.2 | 3-Clause BSD License |
| psutil | 7.2.2 | BSD-3-Clause |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic_core | 2.46.5 | MIT |
| pyDeprecate | 0.9.0 | Apache-2.0 |
| pyee | 13.0.1 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pyparsing | 3.3.3 | MIT |
| pytest | 9.1.1 | MIT |
| python-dateutil | 2.9.0.post0 | Dual License |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| rdflib | 7.6.0 | BSD-3-Clause |
| referencing | 0.37.0 | MIT |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| reportlab | 5.0.1 | BSD license (see license.txt for details), Copyright (c) 2000-2025, ReportLab Inc. |
| requests | 2.34.2 | Apache-2.0 |
| rfc3986 | 1.5.0 | Apache 2.0 |
| rfdetr | 1.11.2 | Apache License 2.0 |
| rich | 15.0.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| safetensors | 0.8.0 | License :: OSI Approved :: Apache Software License |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| scipy | 1.18.1 | Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers. (full notice bundled) |
| segments | 2.4.0 | Apache 2.0 |
| setuptools | 84.0.0 | MIT |
| shellingham | 1.5.4 | ISC License |
| sherpa-onnx-core | 1.13.8 | Apache-2.0 |
| sherpa_onnx | 1.13.8 | Apache licensed, as found in the LICENSE file |
| six | 1.17.0 | MIT |
| smart_open | 8.0.2 | License :: OSI Approved :: MIT License |
| soundfile | 0.14.0 | BSD 3-Clause License |
| spacy | 3.8.16 | MIT |
| spacy-curated-transformers | 0.3.1 | MIT |
| spacy-legacy | 3.0.12 | MIT |
| spacy-loggers | 1.0.5 | MIT |
| srsly | 2.5.4 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| supervision | 0.30.8 | MIT |
| sympy | 1.14.0 | BSD |
| tenacity | 9.2.1 | Apache-2.0 |
| termcolor | 3.3.0 | MIT |
| thinc | 8.3.13 | MIT |
| threadpoolctl | 3.7.0 | BSD-3-Clause |
| tokenizers | 0.23.2 | License :: OSI Approved :: Apache Software License |
| torch | 2.8.0+cu129 | BSD-3-Clause |
| torchvision | 0.23.0 | BSD |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| transformers | 5.19.0 | Apache 2.0 License |
| triton | 3.4.0 | License :: OSI Approved :: MIT License |
| truststore | 0.10.4 | MIT |
| typer | 0.27.3 | MIT |
| typesafe-sdk | 0.7.2 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uritemplate | 4.2.0 | BSD 3-Clause OR Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| uvloop | 0.23.0 | MIT License |
| wasabi | 1.1.3 | MIT |
| watchfiles | 1.3.0 | MIT |
| weasel | 1.0.0 | MIT |
| websockets | 17.2 | BSD-3-Clause |
| wrapt | 2.5.0 | BSD-2-Clause |

## v2 original code
Canvas orb, code highlighting, kernel sandbox and developer templates are original Atlas code under this repository's MIT license. No new frontend libraries/CDNs.

## v2 embedding snapshot
- `nvidia/llama-nemotron-embed-1b-v2`, revision `113abe4acafa848e77ead9c0623205e511932348`: NVIDIA Open Model License; additional Llama 3.2 Community License terms, including attribution and acceptable use. Model card explicitly states commercial readiness. Used solely for local retrieval, not fine-tuned in this build. [Model card](https://huggingface.co/nvidia/llama-nemotron-embed-1b-v2), [NVIDIA license](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/), [additional license](https://www.llama.com/llama3_2/license/). Local card saved in eval/model-cards. Built with Llama.
- `llama_bidirectional_model.py` and `pooling.py` in that snapshot: Apache-2.0, NVIDIA copyright/SPDX headers retained. Audited local model code imports only torch/transformers; no network code. Loaded with local_files_only and runtime loopback network guard.
