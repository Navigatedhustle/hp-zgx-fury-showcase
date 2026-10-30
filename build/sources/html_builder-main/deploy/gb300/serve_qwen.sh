#!/usr/bin/env bash
# Reference vLLM launch for the GB300 (Linux). Adjust to your existing zrt proxy setup —
# the app only needs an OpenAI-compatible /v1 endpoint that serves the model below.
#
# Why these flags:
#   --enable-prefix-caching   every call shares a ~17k-token system prompt (skill + gold examples); caching it
#                             cuts time-to-first-token on all but the first call.
#   --max-model-len 65536     system prompt ~17k + slide prompt/images ~4k + reply up to 16k, with headroom.
#   --limit-mm-per-prompt     the critic sends up to 3 images (step 0, final step, original slide), but the
#                             planner sends one thumbnail per slide in a batch — up to PLAN_MAX_IMAGES (16)
#                             in a single call. A lower limit here makes vLLM reject the whole plan request.
#   --reasoning-parser qwen3  separates <think> from the answer (the app also strips it if present).
#   --max-num-seqs 16         the app runs up to LLM_MAX_CONCURRENCY=8 requests in parallel.
set -euo pipefail

MODEL="${MODEL:-unsloth/Qwen3.6-27B-NVFP4}"
PORT="${PORT:-8000}"

vllm serve "$MODEL" \
  --host 0.0.0.0 --port "$PORT" \
  --max-model-len 65536 \
  --enable-prefix-caching \
  --max-num-seqs 16 \
  --gpu-memory-utilization 0.85 \
  --limit-mm-per-prompt '{"image": 16}' \
  --reasoning-parser qwen3

# The review model (critic, pairwise A/B, eval judge, grounding) now has its own script and its own
# server: see serve_gemma.sh. Run both. When it is up, drop --gpu-memory-utilization above to ~0.55 so
# the two processes are not both trying to claim most of the GPU.
#
# The 16-image limit above stays on THIS server: the planner's thumbnail batches (PLAN_MAX_IMAGES) are
# authoring work and never move to the review model.
