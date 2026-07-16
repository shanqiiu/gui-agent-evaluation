# GUI Agent Evaluation Project Notes

## Current Project State

The default evaluation path is the independent baseline, not `src/oracle`.

Current chain:

```text
src.preprocessor.pipeline
  -> payload.json
  -> src.evaluator.repeated_baseline
  -> ab_report
  -> state_sequence
  -> intent_matches
  -> checkpoint_alignments
  -> verification_report
  -> repeated_prediction
  -> baseline_result
```

`src/oracle` is legacy Darwin reference only. Do not add new baseline logic under `src/oracle` unless the task explicitly asks for legacy compatibility.

## Important Modules

| Module | Role |
|---|---|
| `src/preprocessor` | Raw task parser and payload writer |
| `src/decomposer` | LLM + RAG checkpoint generator |
| `src/common` | Image hydration, ABValidator, repeated detector |
| `src/evaluator/repeated_baseline.py` | Main baseline orchestration |
| `src/evaluator/state_evidence.py` | Aggregated state and visual/OCR evidence |
| `src/verifier/alignment.py` | Intent recall and checkpoint-to-step alignment |
| `src/verifier/verifier.py` | Screenshot/VLM checkpoint verification |
| `src/oracle` | Legacy Darwin service |

## Design Rules

- Keep generic modules app/domain agnostic.
- Do not hardcode ecommerce/search/filter/product-style intents.
- Do not evenly distribute checkpoints across steps.
- Use real screenshot Base64 for VLM calls; do not pass file paths as image content.
- `agent_purpose` is an intent signal, not ground truth.
- Checkpoint judgment is two-stage: intent recall first, execution verification second.
- Missing evidence should produce `uncertain` or `unmatched_intent`, not silent success.
- Keep `.env` uncommitted.

## Main Commands

Preprocess one task:

```bash
python -m src.preprocessor.pipeline <task_uuid_dir> --output <preprocess_out>
```

Preprocess batch:

```bash
python -m src.preprocessor.pipeline --batch <raw_base_dir> --output <preprocess_out>
```

Run one baseline:

```bash
python -m src.evaluator.repeated_baseline <payload.json> --output-dir <baseline_out>
```

Run batch baseline:

```bash
python -m src.evaluator.repeated_baseline --batch <preprocess_out> --output-dir <baseline_out>
```

Regression tests:

```bash
python -m pytest src\verifier src\evaluator src\common\test_common.py
```

## Environment

`src.evaluator.repeated_baseline` auto-loads `.env`.

```env
VLM_MODEL_URL=http://host/v1/chat/completions
VLM_MODEL_NAME=qwen3-vl-8b
VLM_API_KEY=...

LLM_MODEL_URL=http://host/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=...
```

If `LLM_*` is absent, the baseline falls back to `VLM_*` for intent reranking.

## Documentation

`docs/01-*.md` is the source of truth. Topic docs under `docs/` are aligned with the current baseline, while literature/resource/case-insight docs are background only.
