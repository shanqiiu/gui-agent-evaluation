#!/usr/bin/env bash
set -e

python -m src.evaluator.repeated_baseline \
  "D:\path\to\payload.json" \
  --output-dir "D:\path\to\baseline_out"
