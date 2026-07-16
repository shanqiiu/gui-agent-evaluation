# GUI Agent Evaluation

This project evaluates GUI Agent execution traces with an independent baseline. The current default path no longer depends on `src/oracle`; the old Darwin service is kept as legacy reference only.

## Current Pipeline

```text
raw task data
  -> src.preprocessor.pipeline
  -> payload.json + screenshots + dedup/stategraph artifacts
  -> src.evaluator.repeated_baseline
  -> ab_report
  -> state_sequence
  -> intent_matches
  -> checkpoint_alignments
  -> verification_report
  -> repeated_prediction
  -> baseline_result
```

The important design change is the two-stage checkpoint flow:

1. Intent recall: match `_checkpoints` against actual `agent_purpose`, action text, page descriptions, and aggregated state evidence.
2. Execution verification: verify only recalled candidates with real screenshots and VLM evidence.

If intent recall fails, the checkpoint is marked `unmatched_intent`; the verifier does not randomly bind it to a screenshot step.

## Quick Start

### Preprocess one task

```bash
python -m src.preprocessor.pipeline D:\path\to\raw_task_dir --output D:\path\to\preprocess_out
```

### Preprocess a batch

```bash
python -m src.preprocessor.pipeline --batch D:\path\to\raw_task_base_dir --output D:\path\to\preprocess_out
```

### Run one baseline

```bash
python -m src.evaluator.repeated_baseline D:\path\to\preprocess_out\task_uuid\payload.json --output-dir D:\path\to\baseline_out
```

### Run batch baseline

```bash
python -m src.evaluator.repeated_baseline --batch D:\path\to\preprocess_out --output-dir D:\path\to\baseline_out
```

`start.sh` wraps the same commands and supports:

```bash
MODE=single bash start.sh
MODE=batch bash start.sh
```

## Environment

`src.evaluator.repeated_baseline` auto-loads `.env` from the repo root.

```env
VLM_MODEL_URL=http://host/v1/chat/completions
VLM_MODEL_NAME=qwen3-vl-8b
VLM_API_KEY=...

LLM_MODEL_URL=http://host/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=...
```

Usage rules:

- `VLM_*` is used by AB validation and checkpoint screenshot verification.
- `LLM_*` is used by decomposer and optional intent reranking.
- If `LLM_*` is absent, the baseline falls back to `VLM_*` for intent reranking.
- Do not commit `.env`.

## Preprocessor Output

For each task:

```text
output/<task_uuid>/
- payload.json
- _deduped.json
- _stategraph.json
- catchDataTurnId*.jpg
- ...
```

`payload.json` contains:

| Field | Meaning |
|---|---|
| `instruction` | User task |
| `step_level_instruction` | Human-readable checkpoint sequence |
| `_checkpoints` | Structured checkpoint list |
| `agent_purposes` / `_action_purposes` | Agent self-reported step intentions |
| `_ocr_pages` / `_ocr_page_index` | rawPage/OCR evidence |
| `seq_info` | Actual action and screenshot sequence |
| `_image_base_dir` | Base directory for screenshot hydration |

## Baseline Output

| File | Meaning |
|---|---|
| `ab_report.json` | AB page/action validation output |
| `intent_matches.json` | Intent-level checkpoint recall candidates |
| `checkpoint_alignments.json` | Candidate-to-step alignment result |
| `verification_report.json` | VLM checkpoint achievement report |
| `state_sequence.json` | Aggregated state, OCR, and visual evidence |
| `repeated_prediction.json` | Repeated-action baseline result |
| `baseline_result.json` | Full combined output |

## Module Status

| Module | Status |
|---|---|
| `src/preprocessor` | Current data preprocessing path |
| `src/decomposer` | LLM + RAG checkpoint generation |
| `src/common` | Shared AB validation, image hydration, repeated detector |
| `src/evaluator` | Current baseline orchestration |
| `src/verifier` | Intent recall, alignment, checkpoint VLM verification |
| `src/oracle` | Legacy Darwin service, not the default baseline path |
| `src/state_extractor` | Legacy/prototype state extractor; new baseline uses `src/evaluator/state_evidence.py` |

## Tests

Primary regression command:

```bash
python -m pytest src\verifier src\evaluator src\common\test_common.py
```

## Documentation Index

| Document | Purpose |
|---|---|
| `docs/01-*.md` | Source-of-truth technical plan |
| `docs/*repeated*.md` / repeated-action topic doc | Repeated-action design |
| `docs/*planning*.md` / planning-failure topic doc | Planning-failure design |
| `docs/02-*.md` | Literature notes, not implementation spec |
| `docs/03-*.md` | Resource index, not implementation spec |
| `docs/GUI_Agent_*.md` | Taxonomy and research insight |
