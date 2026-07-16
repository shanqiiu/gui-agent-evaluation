Legacy note: this document describes the old `src/oracle` Darwin-compatible service. The current default baseline is `src.evaluator.repeated_baseline`; see repo README and `docs/01-*.md`.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## Project Overview

FuncOracleCheck is a **functional oracle checking service** for GUI automated testing of HarmonyOS apps. It validates whether app UI state changes after user actions (click, swipe, etc.) are functionally correct, using a combination of rule-based image analysis and LLM/VLM AI models.

The project has two running modes:
- **Server mode** — FastAPI HTTP service that accepts test requests from the upstream test orchestration system
- **Benchmark mode** — Local batch evaluation framework for measuring model accuracy against labeled datasets

## How to Run

### Dependencies

Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Server Mode (Production)

Launch the main API server on port 20025 with 48 concurrent worker processes:
```bash
python main.py
```

Or via uvicorn directly:
```bash
uvicorn main:app --host 0.0.0.0 --port 20025 --reload
```

The server mode spawns `CONSUMER_NUMBER` (default 48) multiprocessing workers that consume tasks from a Redis queue. Configuration in `config.py` controls Redis connection, OBS bucket, and thresholds.

### Single Sequence Test (Test Mode)

Set `mode=test` in `conf/run_mode_config.conf`, then:
```bash
python framework.py
```
This runs a single test sample from the path specified in `framework.py` line 34.

### Batch Benchmark Evaluation

Configure `conf/run_benchmark_config.conf` with `benchmark_dir`, `max_workers`, `sliding_mode`, then:
```bash
python framework_batch_eval.py
```

After evaluation,统计 results:
```bash
python GUI_TestFramework_v1/eval/eval.py --result_dir <path> --labeled_dir <path>
```

### Cython Compilation

For production deployment, compile Python to C via Cython:
```bash
python setup.py build_ext --inplace --build-lib=compiled -j 4
```

## Architecture

### Entry Points

| File | Purpose |
|------|---------|
| `main.py` | Main FastAPI server (port 20025). Spawns 48 multiprocess workers + HTTP endpoints |
| `oracle_service.py` | Shared service wrapper used by FastAPI and CLI entries |
| `framework.py` | CLI entry for single sequence test in test mode |
| `framework_batch_eval.py` | CLI entry for batch benchmark evaluation with threaded concurrency |

### API Endpoints (`main.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/get_oracle_check_result` | POST | Core oracle check — receives `AIAssistedScenarioDeterminationModel`, returns result + checkpoints |
| `/upload_funcheck_task` | POST | Submit task to Redis queue for async processing |
| `/get_check_result` | POST | Query single task result from Redis |
| `/get_check_batch_result` | POST | Query batch task results from Redis |
| `/check_single_funck` | POST | Single-step functional check (2 screenshots) |
| `/check_e2e` | POST | E2E sequence functional check |
| `/get_upload_params` | POST | Get OBS upload parameters |

### Core Modules

- **`oracle/function_oracle/`** — `function_oracle_checker.py` contains 3 versions (V1/V2/V3) of `FunctionalOracleChecker`. V3 is the production consumer that pulls tasks from Redis queue, downloads from OBS, runs the check, and stores results back to Redis.
- **`GUI_TestFramework_v1/scripts/`** — The test framework core:
  - `sequence.py` — `HarmonyAppTest` class for multi-step sequence testing. Does AB page validation, sequence splitting, MLLM-based result判定
  - `single_step.py` — `HarmonyAPPSingleStepTest` for 2-screenshot single-step validation
  - `config.py` — Configuration system. Reads `conf/run_mode_config.conf` to switch between test/server mode, then loads `run_benchmark_config.conf` or `run_server_config.conf`. Singleton `Config` class holds project, model, data, and collector settings.
  - `rsync_multi_threads_ab_validator.py` — Multi-threaded AB page可用性 validator with adaptive threading
- **`GUI_TestFramework_v1/api_service/`** — LLM/VLM API integration:
  - `mllm.py` — Unified MLLM request handler supporting 3 sliding modes: `LLM` (LLM only), `VLM` (VLM only), `MIX` (VLM sliding + LLM sliding)
  - `mllm_data_collector/` — Optional request logging hook for debugging MLLM calls
  - `prompts/` — Prompt templates for AB test, intention predicate, sequence split, single image analysis
- **`utils/`** — Shared utilities:
  - `cv_utils.py` — OpenCV image processing (similarity, black/white screen, frosted glass, grayscale variance)
  - `database.py` — `RedisClusterClient` for task queue/results, `OBSDatabaseClient` for S3 storage, `S3DatabaseClient` for local fallback
  - `json_utils.py` — JSON load/save helpers
  - `handling_utils.py` — Action result processing and formatting
  - `layout_utils.py` — Layout tree parsing
  - `prompt_utils.py` — Prompt building utilities
- **`app/models.py`** — Pydantic request/response models (`AIAssistedScenarioDeterminationModel`, `ActionList`, `DataInfo`, etc.)
- **`external_apis/`** — Java JAR engines loaded via JPype1 for layout parsing

### Configuration

Configuration is i**ini-file based** via Python `configparser`:
- `conf/run_mode_config.conf` — Single key `mode` under `[RunConfig]`: `test` or `production`, determines which config file to load
- `conf/run_benchmark_config.conf` — Test mode: MLLM model names/URLs, benchmark directory, sliding mode (`LLM`/`VLM`/`MIX`), eval output path, MLLM data collector settings
- `conf/run_server_config.conf` — Server mode: MLLM model names/URLs, sliding mode
- `config.py` — Global constants: JAR paths, external API URLs (OCR, YOLO, BERT text classification), image similarity thresholds, Redis/OBS credentials, queue names

### Data Flow (Server Mode)

1. Client calls `/upload_funcheck_task` → task pushed to Redis list queue
2. 48 `FunctionalOracleCheckerV3` workers pop tasks from queue
3. Worker downloads ZIP from OBS bucket, extracts screenshots/layouts
4. Worker runs `processing_flow()` → rule-based checks + MLLM判定
5. Result stored in Redis hash key, client polls `/get_check_result`

### Data Flow (Test/Benchmark Mode)

1. Config reads `conf/` files → `Config` singleton built
2. `framework.py` or `framework_batch_eval.py` creates `HarmonyAppTest` per sample
3. `HarmonyAppTest` loads `data.json` from sample dir, runs AB validation → sequence split → MLLM判定 per window
4. Result saved to `output_SLD<mode>_<suffix>/` directory as JSON
5. `eval/eval.py` compares output JSON against labels to compute accuracy

### Sliding Window Modes

The MLLM layer supports three sliding window strategies for processing long sequences:
- **LLM** — All steps sent to LLM, screenshots described textually
- **VLM** — All steps sent to VLM with embedded images
- **MIX** — VLM for initial window, LLM for overflow steps (default)

This is controlled by `sliding_mode` in the config and the `HarmonyAppTest.child_sequence_router()` method.
