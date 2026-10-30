#!/usr/bin/env bash
# Reference vLLM launch for the EMBEDDING model on the GB300 (Linux) — optional. It ranks reference-document
# passages by meaning (app/llm/embed.py, pipeline/reference.slide_reference). Without it the app ranks by
# shared words only, and everything else works exactly the same.
#
# Reference only now that ZRT serves the models: what matters is that the model is served as a *pooling*
# model, not a chat model. If `zrt serve` has no way to pass these flags, the label will answer /v1/chat
# but not /v1/embeddings, and `python -m app.cli probe` reports the embedding endpoint as down.
#
# The model: a community NVFP4 quantization of Qwen/Qwen3-Embedding-4B (Apache-2.0, llm-compressor, 2.7 GB).
# Its card reports 97-98% of the BF16 MTEB score and this exact command on vLLM 0.26. It is a personal
# upload, not a vendor release — if it gives trouble, ironbcc/Qwen3-Embedding-4B-NVFP4A16 (weights-only
# quantization, same family) or the unquantized Qwen/Qwen3-Embedding-0.6B (1.2 GB) are drop-in.
#
# Why these flags:
#   --runner pooling --convert embed   serve hidden states as embeddings on /v1/embeddings.
#   --max-model-len 8192               a passage is ~400 tokens and a query less; 8k is generous and cheap.
#   --gpu-memory-utilization 0.05      it is tiny next to the author and review models; do not let it take
#                                      vLLM's default 90% of the card.
# The app cuts vectors to EMBED_DIM itself (the model is Matryoshka-trained), so no --pooler-config is needed.
set -euo pipefail

MODEL="${MODEL:-ironbcc/Qwen3-Embedding-4B-NVFP4}"
PORT="${PORT:-8082}"

vllm serve "$MODEL" \
  --host 0.0.0.0 --port "$PORT" \
  --runner pooling --convert embed \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.05
