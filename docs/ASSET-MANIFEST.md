# Distribution assets and downloads

## V3 selected creative profile (2026-11-06)

The official [Wan2.2-TI2V-5B card](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B/blob/921dbaf3f1674a56f47e83fb80a34bac8a8f203e/README.md) declares Apache-2.0. Qualification uses the same model in its publisher's [official Diffusers serialization](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers/blob/b8fff7315c768468a5333511427288870b2e9635/README.md), pinned to `b8fff7315c768468a5333511427288870b2e9635` (31.85 GiB download, converted to BF16 for the transformer at load; VAE FP32). Both cards were inspected directly; Apache-2.0 has no annual-revenue threshold. This is the selected same-backbone profile; measured qualification and failed trials are preserved in docs/verification/v3_memory_plan.json.

The pinned [FLUX.2 klein 4B card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/e7b7dc27f91deacad38e78976d1f2b499d76a294/README.md) was rechecked: Apache-2.0, including reference editing. The existing Qwen card at the revision listed below was rechecked and declares Apache-2.0. No additional vision model is loaded.

Reviewed but not selected: `lightx2v/Wan2.2-Lightning` at `18bccf8884ec0a078eed79785eb4ef13ea16ce1e` declares Apache-2.0, but its published weight files target A14B, not the 5B candidate. Its metadata mentioning 5B is not proof of compatible weights. The `quanhaol/Wan2.2-TI2V-5B-Turbo` card does not state an explicit model license; no weights from that repository are used. No LTX 2 model or excluded brand is used. A model is selected only after measured qualification.

Additional compatible candidates were found during qualification: [LongLive-Plug few-step](https://huggingface.co/Efficient-Large-Model/LongLive-Plug-Wan2.2-TI2V-5B-few-step/blob/38a6ec4e8f5b644749d3072bfe1ac383d00951c0/README.md) at `38a6ec4e8f5b644749d3072bfe1ac383d00951c0` and [its CFG adapter](https://huggingface.co/Efficient-Large-Model/LongLive-Plug-Wan2.2-TI2V-5B-cfg/blob/fa1f9280778aa27c8038fe06e29fb5f2ed6be451/README.md) at `fa1f9280778aa27c8038fe06e29fb5f2ed6be451`. Both pinned cards were inspected directly and declare Apache-2.0, with no annual-revenue limit. Initially paused at the three-failure stop rule, these hash-verified adapters subsequently passed owner-authorized resumed hardware qualification and are selected at weights 1.0 and 0.5. Publisher integration documentation and its Apache-2.0 license were inspected at [NVlabs/LongLive revision 2426358](https://github.com/NVlabs/LongLive/tree/242635807b4ebb89fa2609a84df7eacde6aed92f/LongLive-Plug); no upstream training/inference code was executed or redistributed. Gate status and measured failures are in `docs/verification/v3_memory_plan.json`.

The creative owner retains FLUX and the candidate in one process with idle modules resident in Grace memory through Diffusers/Accelerate CPU offload. On this host, aggregate Linux memory includes HBM as NUMA node 1; Grace is CPU NUMA node 0 (494.15 GiB usable). The worker binds its own future CPU allocations to Grace and materializes CPU weights there to prevent fallback into HBM. CPU residency is reported separately from active GPU placement; DeepSeek/Qwen engine allocations, contexts, sequence counts and gateway admission remain unchanged. Only one creative GPU job executes at a time. Downloads, benchmark fixtures and generated output remain outside publication.

Media output uses the pinned `imageio-ffmpeg` 0.8.1 ARM64 wheel (BSD-2-Clause wrapper; separately executed FFmpeg binary GPL-3.0-or-later, no revenue threshold). `config/creative-tools.json` records its upstream download and binary hashes. The binary stays in local environments and is not redistributed in source ZIPs. Wan prompt cleaning uses ftfy 6.3.1 (Apache-2.0) and wcwidth 0.2.13 (MIT).

The exact release inclusion list is `config/distribution-files.json`; `SOURCE-SHA256SUMS` records source hashes. `config/model-files.json` records every downloaded model file, byte count, immutable revision and upstream SHA-256 (LFS) or Git blob SHA-1. No model weights are put in Git or the launch ZIP.

Included: frontend/backend source, the actual presentation prompt pack and examples, Factory role/orchestration/sandbox/preview code, Atlas synthetic schema/data generators, fictional supplier/document seeds, maintained vector travel portal, separate prebuilt generated backend reference, local UI artwork/fonts, dependency locks, build tools, controller, tests and operating documentation. The prebuilt image sample is clearly labeled; it is not used as live inference output. Vendor product photos/logos and optional private travel imagery have been removed/replaced with original neutral/vector artwork. Font licenses and Chart.js notice are preserved. Atlas PNG/PDF exports use bundled Liberation Sans 2.1.5 (from the Ubuntu fonts-liberation package, SIL OFL 1.1) so they do not depend on a workstation-only font path.

| Setup download | Immutable revision | Format / inference engine | License | Selected size |
|---|---|---|---|---:|
| [unsloth/Qwen3.6-27B-NVFP4](https://huggingface.co/unsloth/Qwen3.6-27B-NVFP4) | ccdaab7e68af2409599b8949a8f2685703c9bae5 | NVFP4 compressed weights, FP8 KV; vLLM 0.31.0, CUDA PyTorch 2.13.0+cu132 | Apache-2.0 | 21.83 GiB |
| [nvidia/DeepSeek-V4-Flash-NVFP4](https://huggingface.co/nvidia/DeepSeek-V4-Flash-NVFP4) | e3cd60e7de98e9867116860d522499a728de1cf9 | Mixed NVFP4 MoE expert (groups of 16) / FP8-base checkpoint; FP8 KV; vLLM 0.31.0, PyTorch 2.13.0+cu130 | MIT | 156.75 GiB |
| [black-forest-labs/FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) | e7b7dc27f91deacad38e78976d1f2b499d76a294 | BF16 diffusers 0.41.0, PyTorch 2.13.0+cu132 | Apache-2.0 | 14.89 GiB |
| [csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26](https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26) | 672fbf1b30579d6585301139bb363f42a0ad4a24 | English int8 ONNX, sherpa-onnx CPU | Apache-2.0 | 0.14 GiB |
| [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | f3ff3571791e39611d31c381e3a41a3af07b4987 | v1 weights, af_heart Atlas voice and am_michael narrator voice; Kokoro 0.9.4 CUDA | Apache-2.0 | 0.31 GiB |

The additional required English linguistic model is [spaCy en_core_web_sm 3.8.0](https://github.com/explosion/spacy-models/releases/tag/en_core_web_sm-3.8.0), an unquantized CPU model used by Misaki for Kokoro pronunciation (MIT). Its official release-wheel URL and SHA-256 are recorded in `config/auxiliary-models.json` and enforced by the direct URL in the model-environment lock. It installs automatically with the other pinned dependencies.

These exact repositories/revisions were queried without authentication. All were public/ungated at preparation. A clean setup disables implicit Hugging Face tokens and calls the official source directly. If access policy changes, accept any upstream terms yourself and optionally supply your **own** `HF_TOKEN` through the launching process environment, never in source, a chat message or a release file. No silent model substitution is supported. The full DeepSeek profile is the default.

Downloader: `./launch.sh setup` or `.venv/bin/python ops/download-models.py`. It retains Hugging Face partial download metadata, reports model totals/progress, verifies newly downloaded bytes, and caches verification against file timestamps and expected hashes. Explicit full rehash: `.venv/bin/python ops/download-models.py --verify-only`. Verification errors are fatal. The downloader excludes duplicate root FLUX single-file weights; the complete diffusers subfolders are selected.

The first cold engine launch also obtains architecture-specific FlashInfer kernels from NVIDIA’s public `edge.urm.nvidia.com` service and compiles local kernels. The pinned FlashInfer 0.7.0.post1 package identifies its upstream kernel revision (observed attention revision `2d6a5a029eefcc388ec0ceb87efb55d8bcce5c3c` and MoE revision `1d145b82ac60add55ea213863523f12d63005651`) and fetches upstream checksums. These cache in the launching user’s `.cache/flashinfer`; this is an additional first-start internet requirement, separate from Hugging Face model downloads. It was exercised with an empty user cache during clean installation. Triton/compiler caches can also live under the launching user’s home. No publisher cache is required.

Setup also downloads version-pinned Python wheels (locks in `ops/`), Node 24.22.0 (SHA-256 in bootstrap), uv 0.13.1 (SHA-256 in bootstrap), Chromium from the pinned Playwright package and locked npm dependencies. It extracts Ubuntu Python headers locally from the recipient's configured OS repository. Wheels/browser/system dependencies retain upstream terms. No GPU driver, CUDA toolkit or kernel is redistributed. There are no bundled containers: the tested deployment uses three project-local Python environments.

Excluded: personal credentials, SSH keys, authentication/browser profiles, network identity state, original Git history, internal planning documents, customer outputs, model caches/weights, old run logs/databases, private runtime image bundles, environments and machine reports. The reference consists only of reviewed source and fictional seed logic, with a newly initialized database when run.

## V2 identity assets

Bundled hp-logo-keyline.png is the owner-supplied official HP HEX PNG, unchanged (source and SHA-256 in showcase_app/assets/PROVENANCE.md). HP trademark rights apply separately from MIT source licensing. Raw logo/stripe ZIPs and licensed HP fonts are excluded. The optional stripe is unused. All shared shell assets render locally without external fonts or marketing services.

## v2.1 recorded demonstration

The curated `build/sources/fury_agent_factory/examples/recorded-travel/` directory is an explicitly supplied application artifact with sanitized recorded events and endpoint usage from a successful development run. It includes no prompts, databases, sessions or GPU telemetry. Redistribution replaces private runtime destination images with the maintained public vector scenes; backend source and recorded usage remain unchanged. See its PROVENANCE.md and recording.json file checksums. Guided mode uses fresh fictional data and labels the compressed playback throughout. The final release also includes the Colorado deployment PDF, its HTML source, screenshots and presenter/verification guides.

### Resumed candidate qualification

After the owner authorized continuation and simplification, the two pinned Apache-2.0 LongLive-Plug adapters entered qualification. They are fused once into the matching 300 Wan linear modules on Grace before GPU offload, using Diffusers 0.41.0’s native Wan key conversion. The few-step weight is 1.0 and CFG weight 0.5; both adapter alpha/rank ratios are 1. BF16 base weights and both FP32 deltas are accumulated in FP32 and cast once to BF16. Checksums, complete tensor/module coverage, shapes and finite values are checked before serving. No PEFT dependency, alternate backbone, extra resident GPU engine, or model download during a visitor job is introduced. Every video job and health response names the adapters and profile; qualification and selection are recorded in docs/verification/v3_memory_plan.json.

## V3 narrator and document exports

The existing [Kokoro card](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md) was directly rechecked on 2026-11-06 and declares Apache-2.0, including commercial use without an annual-revenue ceiling. The added `voices/am_michael.pt` is 523435 bytes, SHA-256 `9a443b79a4b22489a5b0ab7c651a0bcd1a30bef675c28333f06971abbd47bd37`, at that same pinned revision. Atlas retains af_heart. Unknown voices are rejected; no silent voice substitution is used.

Document parsing uses pypdf (BSD-3-Clause) and python-docx (MIT); sample PDFs use ReportLab (BSD-style). Exports use local Chromium and installed Noto Unicode fonts for script shaping; font availability/translation quality may differ on another host. No PyMuPDF dependency is used. Samples are original fictional source described in assets/PROVENANCE.md. All these software licenses permit commercial use without an annual-revenue threshold.

## GB10 stage qualification assets (2026-11-08)

These assets are candidates under measurement, not a claim of stage readiness. The existing GB300 records remain unchanged under the `gb300` section of `config/model-files.json`. GB10 downloads require `--profile gb10`. Qwen qualification proceeds Q8_0, Q6_K, then Q4_K_XL; unselected quants are not downloaded. Every GB10 file uses SHA-256, including model cards and configuration. Public source contains no weights.

The publisher and converter model cards were read directly at the immutable revisions below. All four model publishers declare Apache-2.0. The [original gpt-oss card](https://huggingface.co/openai/gpt-oss-120b/blob/b5c939de8f754692c1647ca79fbf85e8c1e70f8a/README.md) describes 117B total and 5.1B active parameters; the [original Qwen card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/blob/345d467b117d1fd5eda9b879a5988de9ae5f47a7/README.md) describes 35B total, 3B active and a vision encoder. FLUX uses the distilled four-step 4B model. Kokoro is v1.0, 82M parameters. No ASR or video assets are selected by the GB10 downloader.

### [ggml-org/gpt-oss-120b-GGUF](https://huggingface.co/ggml-org/gpt-oss-120b-GGUF/blob/7200b74bea78b0a2964ef9f3897eefa401e890ff/README.md)

Revision `7200b74bea78b0a2964ef9f3897eefa401e890ff`; license Apache-2.0.

| File | Bytes | SHA256 |
|---|---:|---|
| `README.md` | 496 | `db1fe98191c12ab2cb5d91512326fe487c57fc48ba54c174570c124c53142c16` |
| `gpt-oss-120b-MXFP4.gguf` | 63387346208 | `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d` |

### [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/blob/a483e9e6cbd595906af30beda3187c2663a1118c/README.md)

Revision `a483e9e6cbd595906af30beda3187c2663a1118c`; license Apache-2.0.

| File | Bytes | SHA256 |
|---|---:|---|
| `README.md` | 66568 | `1aabbfa45b14118f4e11a0c107f6789625afb6f4227ff82efc45cdb27acc3a6f` |
| `Qwen3.6-35B-A3B-Q8_0.gguf` | 36903140320 | `d1a395809f65a43a13ad119eb4e7acdef1ac6d68120f39902c8ab96e72794a59` |
| `Qwen3.6-35B-A3B-UD-Q6_K.gguf` | 29308320736 | `4fe53b148b46f9b88830e2a3055c5b15c3a4d1e3ddc9a1384a108d8b9d59f043` |
| `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | 22360456160 | `707a55a8a4397ecde44de0c499d3e68c1ad1d240d1da65826b4949d1043f4450` |
| `mmproj-F16.gguf` | 899283680 | `8971ee4f331ff0a4c609374f32984b3d4e6dc086c0aa35f1d637fad1829e887f` |

### [black-forest-labs/FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/e7b7dc27f91deacad38e78976d1f2b499d76a294/README.md)

Revision `e7b7dc27f91deacad38e78976d1f2b499d76a294`; license Apache-2.0.

| File | Bytes | SHA256 |
|---|---:|---|
| `LICENSE.md` | 9584 | `ca02bc51900ab07789d1b70283329e7137f5af98f5161c23a1c81fc38a4af1fe` |
| `README.md` | 9991 | `bd447051cf2db4bf67b992e563d89c35ebf1123f009c063361a222ab14e1c4f7` |
| `model_index.json` | 446 | `51a76cb1cf3ed37423a1128c79c22faee8e6fbe7f5aaeb737f0a258930dbaac0` |
| `scheduler/scheduler_config.json` | 486 | `067afb012cef64553a763447d1efd93daeffcc0123ca7e25b09f8de20b90762e` |
| `text_encoder/config.json` | 1536 | `214b4c29a0d975e9fddf9994a5673f22cb2c4c5750352f9227c2c3251ebeab40` |
| `text_encoder/generation_config.json` | 214 | `4347b1aeed2b2b78bc059920a0b7f5fec71482e1344952b76d7665d638d71f13` |
| `text_encoder/model-00001-of-00002.safetensors` | 4967215360 | `8c0506e7f4936fa7e26183a4fd8da4e2bdbc5990ba64ae441f965d51228f36ea` |
| `text_encoder/model-00002-of-00002.safetensors` | 3077766632 | `82f2bd839378541b0557bfabaf37c7d3d637071fdcb73302dedd7cf61162ce07` |
| `text_encoder/model.safetensors.index.json` | 32855 | `06b3d5319b6d76d1a4a2433419180016cfd54ed62d086a5e6567a809f8c82634` |
| `tokenizer/added_tokens.json` | 707 | `c0284b582e14987fbd3d5a2cb2bd139084371ed9acbae488829a1c900833c680` |
| `tokenizer/chat_template.jinja` | 4168 | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` |
| `tokenizer/merges.txt` | 1671853 | `8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5` |
| `tokenizer/special_tokens_map.json` | 613 | `76862e765266b85aa9459767e33cbaf13970f327a0e88d1c65846c2ddd3a1ecd` |
| `tokenizer/tokenizer.json` | 11422654 | `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4` |
| `tokenizer/tokenizer_config.json` | 5404 | `443bfa629eb16387a12edbf92a76f6a6f10b2af3b53d87ba1550adfcf45f7fa0` |
| `tokenizer/vocab.json` | 2776833 | `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910` |
| `transformer/config.json` | 541 | `09733c74a3da6d17dd0a0472a091a8950c7c6935889c32c16cc800ede05029de` |
| `transformer/diffusion_pytorch_model.safetensors` | 7751109744 | `9f29f9edcfdae452a653ffb51a534ca4decd389952c225724ff3b94042612a6e` |
| `vae/config.json` | 821 | `0d6dfb69ae95a5e2ac9836284bbb63d8b38ce67b25ba2dff380752b2a10ab948` |
| `vae/diffusion_pytorch_model.safetensors` | 168120878 | `ca70d2202afe6415bdbcb8793ba8cd99fd159cfe6192381504d6c4d3036e0f04` |

### [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md)

Revision `f3ff3571791e39611d31c381e3a41a3af07b4987`; license Apache-2.0.

| File | Bytes | SHA256 |
|---|---:|---|
| `README.md` | 6348 | `91dcabced89db6f109b8786642f50402d3ee87450e8189589b6f85520e7f4d78` |
| `config.json` | 2351 | `5abb01e2403b072bf03d04fde160443e209d7a0dad49a423be15196b9b43c17f` |
| `kokoro-v1_0.pth` | 327212226 | `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4` |
| `voices/af_heart.pt` | 523425 | `0ab5709b8ffab19bfd849cd11d98f75b60af7733253ad0d67b12382a102cb4ff` |
| `voices/am_michael.pt` | 523435 | `9a443b79a4b22489a5b0ab7c651a0bcd1a30bef675c28333f06971abbd47bd37` |

### llama.cpp for GB10

[llama.cpp](https://github.com/ggml-org/llama.cpp/tree/7d7f0287530bc8981690f361d8c1627dbae1c99a) is pinned to `7d7f0287530bc8981690f361d8c1627dbae1c99a`. Its MIT LICENSE was read directly; SHA256 `94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d`. Build target CUDA `sm_121`, Release, six compiler workers, server and benchmark targets. Build products and upstream checkout remain ignored under `.tools/`. This does not modify system CUDA, drivers or the GB300 engines.

The deterministic `git archive --format=tar` source SHA256 for this llama.cpp commit is `96b30678d8996513b4b041e8c7cdde1dea86d23bbbf94a40d04d37b6e157ebd8`, enforced by `ops/build-gb10-llama.py`. The pinned upstream spells non-mmap loading `--load-mode none`; it removed the historical `--no-mmap` flag. Qualification compares default auto against this equivalent with lazy loading and automatic fitting disabled.

### Optional GB10 FLUX text encoder FP8 remedy

The source FLUX weights and revision above remain the input, with only the text encoder linear weights converted locally to FP8 E4M3 per row. Transformer weights and compute activations remain BF16. This is an explicit candidate profile until measured qualification passes. The transformation is `torchao.quantization.quantize_(text_encoder, Float8WeightOnlyConfig(set_inductor_config=False))`, version 2. No alternate checkpoint or remote code is loaded.

TorchAO 0.18.0 is BSD-3-Clause. Its [license](https://github.com/pytorch/ao/blob/5f2baf9d575cf732362594c998c399902942531f/LICENSE) was read directly on 2026-11-08; immutable source revision `5f2baf9d575cf732362594c998c399902942531f`, license SHA256 `67901e351baeaa5aef967cccd0886ba679f085df8673d1ecd49592bf284115af`. The ARM64-compatible pure Python wheel `torchao-0.18.0-py3-none-any.whl` is pinned to SHA256 `5c2b4485341bf28b7fed2c4fc95b9f298e209f41685350f067de85527a05585e` in `config/gb10-build.json` and the GB10 model lock. PyTorch supplies the underlying tensor operations; no binary extension is substituted.

The GB10 lock excludes optional multilingual phonemizer backends and uses the existing pure English Kokoro service and pinned MIT spaCy tagger. Local Python headers are extracted into the ignored project tools directory; host Python, CUDA and drivers are unchanged.

### GB10 PyTorch wheel and local compilation headers

PyTorch2.13.0+cu130 core BSD-3-Clause [LICENSE](https://github.com/pytorch/pytorch/blob/cf30153c4c131c8164ee7798e5022d810682e2cb/LICENSE) was read at immutable source revision`cf30153c4c131c8164ee7798e5022d810682e2cb`. Source LICENSE SHA256`bd018feef8825e88181c84eb7e3aa4eafb8f08a20d9fd6ef948569610c4a3e43`; official ARM64 CPython3.12 wheel SHA256`5ebd552c887e707c8e64927aceb8377ca2e81588c4e7494bcd23cb8ac0aca14d`, now hash-pinned by direct URL in the GB10 lock. Installed bundled license notices remain with the environment; environments and binaries are not release files.

Local Python headers are extracted from Ubuntu`libpython3.12-dev` version`3.12.3-1ubuntu0.17`, ARM64 package SHA256`945ad3f651f683c11e72d19d804b1cff097308dcffa01057635cba038f875164`. This is an ignored build input and does not change host Python, CUDA or packages.

### GB10 conditioning execution, 2026-11-09

The pinned FLUX.2 klein pipeline consumes intermediate Qwen hidden states 9, 18 and 27. GB10 retains the entire original text encoder and all parameters, but forwards its base encoder to avoid computing the unused vocabulary logits. Real 4B encoder hidden states and a same-seed 1344×768 render were exactly equal to the original execution (zero pixel difference). Peak allocated CUDA memory fell from 16,781,654,528 to 15,319,996,928 bytes. This is recorded in `docs/verification/gb10_encoder_equivalence.json`; it is not a replacement checkpoint or a model-size reduction. Fury execution remains unchanged.

### GB10 weight loading, 2026-11-09

The same pinned MIT llama.cpp supports direct I/O (`--load-mode dio`) to avoid duplicate clean weight pages during upload. No source revision, model or quant changed. A GB10-only per-file cache advisory applies `POSIX_FADV_DONTNEED` through read-only descriptors after upload, limited to regular weights listed in the pinned GB10 manifest. It neither writes files nor changes global cache, swap or kernel settings. The actual buffered lead comparison released 53.82 GiB of duplicate clean cache while retaining the resident model; both direct native lanes passed actual throughput, tool-call and vision checks. Full workload acceptance is still blocked by old global swap-ins, as documented in the memory report.

### GB10 stage backup recorder sources, verified 2026-11-09

The stage uses permissive source headers for H.264 MP4 encoding. The `veryfast` preset maps to minih264 speed 8, at 30 fps and GOP 30. The existing Playwright FFmpeg decodes the native kiosk capture; downloaded sources and built binaries remain outside the release. All source and license files were read and hashed at immutable revisions.

| Source | Revision | License | Header SHA256 |
|---|---|---|---|
| [minih264](https://github.com/lieff/minih264) | `b0baea7a80ef9d12da97301dd1099b8791b5ba43` | CC0-1.0 | `661afe7802b4e1174e8389632f3ee437b903e036a9c91a7f035830947c6a7aae` |
| [minimp4](https://github.com/lieff/minimp4) | `2a3014a7753cfcba4442adeb469431967238fe6a` | CC0-1.0 | `9d122076cc23e5f4a7560ce4056c7d84484a8b8bf094d27c8f652f11fc725ce7` |
| [stb](https://github.com/nothings/stb) | `4e9b368bfc071e97206ea5c6adba68dd0cbf8897` | MIT | `594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3` |

Every downloaded file, including the license texts, is SHA256-pinned in `config/gb10-build.json`. CC0 licenses include a broad public-license fallback; stb uses its MIT option.

### Local stage and presenter card font

Arial resolves locally to Liberation Sans from Ubuntu `fonts-liberation` version `1:2.1.5-3`. Its SIL Open Font License 1.1 permits use and embedding. No remote font is requested. The installed regular font SHA256 is `4659bc0c58c5028dd488ec928d41d9265db43d9b669fc14ca8b0832daca7b144`; the package copyright notice SHA256 is `f32df582a2aab128c07b2f7e36e7b928dc5f6bd82657b905c04f91459f9e5cf9`. The generated presenter PDF embeds the local subset. The stage uses the system font stack and does not distribute a new font file. Source: [Liberation fonts 2.1.5](https://github.com/liberationfonts/liberation-fonts/tree/2.1.5).

### GB10 stage margin candidate

The same Apache 2.0 Qwen3.6 GGUF repository and pinned revision `a483e9e6cbd595906af30beda3187c2663a1118c` also provides `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, 22134528992 bytes, SHA256 `ac0e2c1189e055faa36eff361580e79c5bd6f8e76bffb4ce547f167d53e31a61`. The pinned model card and Apache license already reviewed for Q4 XL apply to this quant. The immutable upstream LFS SHA256 was fetched on 2026-11-09, and the existing downloader must verify the actual file before qualification. This candidate is being measured because the native kiosk recorder exposed insufficient margin with Q4 XL; it is not selected until the exact vision and memory gates pass. The headline gpt-oss model and all context and parallel floors stay unchanged.

The selected GB10 stage quant remains Q4_K_XL after the bounded allocator clean-baseline qualification passed. Q4_K_M was checksum verified and passed both vision samples but its development memory trial failed before the loader and allocator correction; it is retained only as a measured candidate. See docs/verification/gb10_gate1.md and gb10_memory_plan.json.

### GB10 generated artwork text policy

Cover and Rush artwork use fixed wordless abstract landscape prompts and the already pinned Qwen vision lane to review original pixels before publication. No additional third party asset or checkpoint is introduced. `docs/verification/gb10_text_free_images.json` records real positive-control rejection, five accepted live renders and their SHA256 values. Runtime candidates, accepted images and backup footage stay excluded from Git and releases.
