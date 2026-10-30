#!/usr/bin/env bash
# Reference vLLM launch for the REVIEW model on the GB300 (Linux) — the critic, the pairwise A/B judge,
# the eval judge and the grounding pass. Runs alongside serve_qwen.sh, which keeps the authoring work.
#
# Why a second model at all:
#   1. A model that scores its own output is the weakest signal in the pipeline. Qwen writing the slide and
#      Qwen grading it systematically over-rates Qwen's own habits. A different family is worth more here
#      than a bigger model of the same one.
#   2. Gemma 4 26B A4B activates ~4B parameters per token, so judgement is cheap enough to afford the things
#      that are currently switched off for cost: more repair rounds, GENERATE_BEST_OF_A > 1, a grounding pass.
#   3. Two servers means two KV caches. The app has two byte-stable system prefixes — skillpack.system_prompt()
#      (~17k tokens) and review_system_prompt() — and on one server they evict each other. Split, both stay hot.
#
# Why these flags:
#   --max-model-len 32768     the review prefix is small, but three 1600x900 screenshots are not. 32k is the
#                             checkpoint's documented window; `python -m app.cli probe` warns below 24k.
#   --limit-mm-per-prompt     the critic sends 3 images (step 0, final step, original render) and the A/B
#                             judge sends 2. The checkpoint defaults to 4; 8 leaves room without wasting memory.
#                             The planner's 16-thumbnail batches stay on the authoring server.
#   --enable-prefix-caching   every review call shares review_system_prompt() byte for byte.
#   --gpu-memory-utilization  the two servers carve up one GPU statically. Give the author the larger share
#                             (0.55 there) and this one the rest; they will fight if both are left at 0.85.
#   --max-num-seqs 16         QA_CONCURRENCY slides can be in the critic at once, each with retries.
set -euo pipefail

MODEL="${MODEL:-RedHatAI/gemma-4-26B-A4B-it-NVFP4}"
PORT="${PORT:-8081}"

vllm serve "$MODEL" \
  --host 0.0.0.0 --port "$PORT" \
  --max-model-len 32768 \
  --enable-prefix-caching \
  --max-num-seqs 16 \
  --gpu-memory-utilization 0.30 \
  --limit-mm-per-prompt '{"image": 8}'

# Then, in .env on the laptop:
#   VLM_BASE_URL=http://gb300:8081/v1
#   VLM_MODEL=RedHatAI/gemma-4-26B-A4B-it-NVFP4
# and confirm both servers with:
#   cd backend && ..\.venv\Scripts\python -m app.cli probe
#
# Leaving VLM_BASE_URL empty puts every stage back on the authoring server — the single-model setup, unchanged.
