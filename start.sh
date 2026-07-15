#!/usr/bin/env bash
set -e

# MODE=single: run one raw task directory and one baseline.
# MODE=batch: run all task directories under RAW_BASE_DIR, then baseline all payload.json files.
MODE="${MODE:-batch}"

# Edit these paths on the server before running.
RAW_TASK_DIR="D:\path\to\raw_task_dir"
RAW_BASE_DIR="D:\path\to\raw_task_base_dir"
PREPROCESS_OUT="D:\path\to\preprocess_out"
TASK_UUID="task_uuid"
BASELINE_OUT="D:\path\to\baseline_out"

if [[ "${MODE}" == "single" ]]; then
  PAYLOAD_PATH="${PREPROCESS_OUT}/${TASK_UUID}/payload.json"

  python -m src.preprocessor.pipeline \
    "${RAW_TASK_DIR}" \
    --output "${PREPROCESS_OUT}"

  python -m src.evaluator.repeated_baseline \
    "${PAYLOAD_PATH}" \
    --output-dir "${BASELINE_OUT}"
elif [[ "${MODE}" == "batch" ]]; then
  python -m src.preprocessor.pipeline \
    --batch "${RAW_BASE_DIR}" \
    --output "${PREPROCESS_OUT}"

  python -m src.evaluator.repeated_baseline \
    --batch "${PREPROCESS_OUT}" \
    --output-dir "${BASELINE_OUT}"
else
  echo "Unsupported MODE: ${MODE}. Use MODE=single or MODE=batch." >&2
  exit 2
fi
