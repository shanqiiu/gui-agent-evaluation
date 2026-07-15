#!/usr/bin/env bash
set -e

# Edit these paths on the server before running.
TASK_DIR="D:\path\to\raw_task_dir"
PREPROCESS_OUT="D:\path\to\preprocess_out"
TASK_UUID="task_uuid"
PAYLOAD_PATH="${PREPROCESS_OUT}\${TASK_UUID}\payload.json"
BASELINE_OUT="D:\path\to\baseline_out"

python -m src.preprocessor.pipeline \
  "${TASK_DIR}" \
  --output "${PREPROCESS_OUT}"

python -m src.evaluator.repeated_baseline \
  "${PAYLOAD_PATH}" \
  --output-dir "${BASELINE_OUT}"
