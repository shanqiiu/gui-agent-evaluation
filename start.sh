#!/usr/bin/env bash
set -e

python -m src.evaluator.repeated_baseline \
  "D:\path\to\payload.json" \
  --vlm-model-url "http://your-vlm-host/v1/chat/completions" \
  --vlm-model-name "qwen3-vl-8b" \
  --output-dir "D:\path\to\baseline_out"
