# Decomposer: LLM + RAG Checkpoint Generation

This module generates structured checkpoints from a natural-language task. It is used by the preprocessor to populate `_checkpoints` and `step_level_instruction` in `payload.json`.

## Current Role

The decomposer is not a verifier. It only proposes expected checkpoints. Actual achievement is judged later by:

1. `match_checkpoint_intents`
2. `align_checkpoints_to_steps`
3. `CheckpointVerifier`

## Environment

```env
LLM_MODEL_URL=http://host/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=...
```

If `LLM_*` is not configured in the baseline stage, `src.evaluator.repeated_baseline` can fall back to `VLM_*` for intent reranking. The decomposer itself still expects LLM config when decomposition is enabled.

## Knowledge Ingestion

```bash
python src/decomposer/knowledge_store.py --ingest src/decomposer/app_knowledge/
```

## Programmatic Usage

```python
from src.decomposer import Decomposer

d = Decomposer(
    model_url="http://host/v1/chat/completions",
    model_name="qwen3-8b",
    api_key="",
)

checkpoints = d.decompose(
    instruction="open the target setting page",
    app_name="settings",
    top_k=5,
)
```

Expected checkpoint shape:

```json
{
  "name": "open target page",
  "required": true,
  "preconditions": "home page is visible",
  "expected_state": "target page title and core controls are visible"
}
```

## Preprocessor Integration

Use:

```bash
python -m src.preprocessor.pipeline <task_dir> --output <out_dir>
python -m src.preprocessor.pipeline --batch <raw_base_dir> --output <out_dir>
```

When decomposition succeeds:

- `_checkpoints` contains structured checkpoint objects.
- `step_level_instruction` is a readable `name->name` sequence.
- `_decomposer` records attempted/status/model/config metadata.

## RAG Notes

- RAG knowledge improves checkpoint quality but is not achievement evidence.
- Missing RAG should fall back to pure LLM decomposition when LLM is configured.
- Empty checkpoint lists are invalid and should be retried.
