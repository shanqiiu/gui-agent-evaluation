"""
Pipeline orchestrator: preprocess → decompose → copy screenshots → write payload, dedup, stategraph.

环境变量（decomposer 可选）:
    LLM_MODEL_URL   - LLM API 地址（不设置则跳过分解）
    LLM_MODEL_NAME  - 模型名称
    LLM_API_KEY     - API Key（可选）
    RAG_PERSIST_DIR - ChromaDB 持久化目录（默认 src/decomposer/chroma_db/）
    RAG_APP_NAME    - 可选 App 知识域；不设置时跨知识域检索

Usage:
    # 单任务
    python -m src.preprocessor.pipeline <task_dir> --output <output_dir>
    
    # 批量模式
    python -m src.preprocessor.pipeline --batch <base_dir> --output <output_dir>
    
    base_dir:  包含 uuid 子目录的根目录（每个子目录含 utg.json + clearRes.gzip）
    output_dir: 输出目录（默认: base_dir/reorg_output）
    
    gzip/zip 自动解压: clearRes.gzip / clearRes.gz / clearRes.json 均支持
    
输出（每任务）:
    output/<uuid>/
    ├── payload.json          ← /check_e2e 判定接口输入（_image_base_dir 已指向本目录）
    ├── _deduped.json         ← 去冗摘要（人类可读）
    ├── _stategraph.json      ← 状态图（语义层）
    ├── catchDataTurnId0.jpg  ← 截图（以原始目录 catchDataTurnIdN 命名）
    ├── catchDataTurnId1.jpg
    └── ...
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Auto-load .env from project root (if available)
try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from .preprocessor import preprocess
from .write_payload import write_payload
from .write_dedup import write_dedup
from .write_stategraph import write_stategraph

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _run_decomposer(task: Any) -> int:
    """Run LLM+RAG decomposition and populate compatibility planning outputs.
    
    Requires environment variables:
        LLM_MODEL_URL  - OpenAI-compatible API endpoint
        LLM_MODEL_NAME - model name
        LLM_API_KEY    - optional API key; falls back to VLM_API_KEY
    Returns number of checkpoints generated (0 if decomposer unavailable).
    """
    model_url = os.environ.get("LLM_MODEL_URL") or os.environ.get("VLM_MODEL_URL", "")
    model_name = os.environ.get("LLM_MODEL_NAME") or os.environ.get("VLM_MODEL_NAME", "")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("VLM_API_KEY", "")
    task_graph_enabled = _env_flag("TASK_GRAPH_ENABLED")
    status = {
        "attempted": False,
        "status": "not_started",
        "model_name": model_name,
        "model_url_set": bool(model_url),
        "api_key_set": bool(api_key),
        "used_vlm_url_fallback": not bool(os.environ.get("LLM_MODEL_URL")) and bool(os.environ.get("VLM_MODEL_URL")),
        "used_vlm_name_fallback": not bool(os.environ.get("LLM_MODEL_NAME")) and bool(os.environ.get("VLM_MODEL_NAME")),
        "used_vlm_key_fallback": not bool(os.environ.get("LLM_API_KEY")) and bool(os.environ.get("VLM_API_KEY")),
        "checkpoint_count": 0,
        "error": "",
        "response_head": "",
        "quality_status": "not_checked",
        "quality_issues": [],
        "refinement_attempted": False,
        "rag_app_name": os.environ.get("RAG_APP_NAME", ""),
        "task_graph_enabled": task_graph_enabled,
        "graph_status": "not_started" if task_graph_enabled else "disabled",
        "graph_error": "",
        "graph_response_head": "",
        "graph_quality_issues": [],
        "graph_correction_attempted": False,
        "task_graph_schema_version": "",
        "checkpoint_source": "legacy",
    }
    task.decomposer_status = status
    if not model_url or not model_name:
        status["status"] = "skipped_missing_config"
        if task_graph_enabled:
            status["graph_status"] = "skipped_missing_config"
        status["error"] = "LLM_MODEL_URL/LLM_MODEL_NAME or VLM fallback not set"
        log.info("  decomposer: skipped (%s)", status["error"])
        return 0

    try:
        from src.decomposer.decomposer import Decomposer
        from src.decomposer.projection import (
            migrate_checkpoints_to_task_graph,
            project_checkpoints,
        )
        from src.decomposer.schema import encode_task_graph
    except ImportError:
        status["status"] = "import_failed"
        status["error"] = "src.decomposer not importable"
        log.warning("  decomposer: unavailable (%s)", status["error"])
        return 0

    d = Decomposer(model_url=model_url, model_name=model_name, api_key=api_key)
    status["attempted"] = True
    app_name = os.environ.get("RAG_APP_NAME") or None
    graph = None
    checkpoints: list[dict[str, Any]] = []

    if task_graph_enabled:
        try:
            graph = d.decompose_graph(
                task.instruction,
                app_name=app_name,
                top_k=5,
            )
        except Exception as exc:
            status["graph_status"] = "exception"
            status["graph_error"] = str(exc)
            log.warning("  decomposer: TaskGraph generation failed (%s)", exc)
        else:
            status["graph_response_head"] = getattr(d, "last_response_head", "")
            status["graph_quality_issues"] = list(
                getattr(d, "last_quality_issues", [])
            )
            status["graph_correction_attempted"] = getattr(
                d, "refinement_attempted", False
            )
            if graph is None:
                status["graph_status"] = "invalid"
                status["graph_error"] = getattr(d, "last_error", "")

        if graph is not None:
            task.task_graph = encode_task_graph(graph)
            checkpoints = project_checkpoints(graph)
            status["graph_status"] = "ok"
            status["task_graph_schema_version"] = graph.schema_version
            status["checkpoint_source"] = "graph_projection"

    if not checkpoints:
        try:
            checkpoints = d.decompose(
                task.instruction,
                app_name=app_name,
                top_k=5,
            )
        except Exception as exc:
            status["status"] = "exception"
            status["error"] = str(exc)
            log.warning("  decomposer: LLM call failed (%s)", exc)
            return 0

        if task_graph_enabled and checkpoints:
            try:
                graph = migrate_checkpoints_to_task_graph(
                    task.instruction,
                    checkpoints,
                )
            except Exception as exc:
                status["graph_status"] = "migration_failed"
                status["graph_error"] = str(exc)
                log.warning("  decomposer: checkpoint migration failed (%s)", exc)
            else:
                task.task_graph = encode_task_graph(graph)
                status["graph_status"] = "fallback_migrated"
                status["task_graph_schema_version"] = graph.schema_version
                status["checkpoint_source"] = "legacy_fallback"

    status["response_head"] = getattr(d, "last_response_head", "")
    status["quality_issues"] = getattr(d, "last_quality_issues", [])
    status["refinement_attempted"] = getattr(d, "refinement_attempted", False)
    status["quality_status"] = "ok" if not status["quality_issues"] else "warning"
    if not checkpoints:
        status["status"] = "empty"
        status["error"] = getattr(d, "last_error", "") or "LLM returned no checkpoints"
        log.warning("  decomposer: no checkpoints generated (%s)", status["error"])
    else:
        status["status"] = "ok" if not status["quality_issues"] else "ok_with_warnings"

    task.checkpoints = checkpoints
    status["checkpoint_count"] = len(checkpoints)
    log.info("  decomposer: %d checkpoints generated", len(checkpoints))
    return len(checkpoints)


def _copy_screenshots(
    task: Any, task_dir: Path, screenshot_dir: Path
) -> int:
    """Copy screenshots from catchDataTurnIdN/ to output dir, named by parent dir."""
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for step in task.steps:
        if not step.screenshot_path:
            continue
        src = task_dir / step.screenshot_path
        if not src.is_file():
            continue
        parent_name = Path(step.screenshot_path).parent.name
        if not parent_name or parent_name == ".":
            parent_name = Path(step.screenshot_path).stem
        dst = screenshot_dir / f"{parent_name}.jpg"
        shutil.copy2(src, dst)
        step.screenshot_path = dst.name
        copied += 1
    return copied


def run_pipeline(
    task_dir: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, str]:
    """
    Run the full preprocessing pipeline for a single task.
    
    Returns:
        {
            "payload": str,     # path to payload.json
            "dedup": str,       # path to _deduped.json
            "stategraph": str,  # path to _stategraph.json
        }
    """
    task_dir = Path(task_dir)
    if not task_dir.is_dir():
        raise FileNotFoundError(f"Task directory not found: {task_dir}")

    if output_dir is None:
        output_dir = task_dir / "reorg_output"
    else:
        output_dir = Path(output_dir)

    task_uuid = task_dir.name
    log.info("=" * 60)
    log.info("Preprocessing pipeline: %s", task_uuid)

    # ── Step 1: Preprocess ──────────────────────────────
    log.info("[1/6] Parsing utg.json + clearRes ...")
    task = preprocess(task_dir)
    log.info("  instruction: %s", task.instruction[:60])
    log.info("  action steps: %d (raw: %d)", task.total_action_steps, task.total_raw_steps)
    log.info("  OCR pages: %d, actionPurposes: %d",
             len(task.ocr_pages), len(task.action_purposes))

    # ── Step 2: Decompose (optional) ─────────────────────
    log.info("[2/6] Decomposing instruction (LLM+RAG) ...")
    _run_decomposer(task)

    # ── Step 3: Copy screenshots ─────────────────────────
    log.info("[3/6] Copying screenshots to output ...")
    screenshot_dir = output_dir / task_uuid
    n_copied = _copy_screenshots(task, task_dir, screenshot_dir)
    log.info("  copied: %d screenshots", n_copied)

    # ── Step 4: Write payload ───────────────────────────
    log.info("[4/6] Writing payload.json ...")
    payload_path = _task_out(output_dir, task_uuid, "payload.json")
    write_payload(task, payload_path, image_base_dir=str(screenshot_dir))
    log.info("  -> %s", payload_path)

    # ── Step 5: Write dedup ─────────────────────────────
    log.info("[5/6] Writing _deduped.json ...")
    dedup_path = _task_out(output_dir, task_uuid, "_deduped.json")
    write_dedup(task, dedup_path)
    log.info("  -> %s", dedup_path)

    # ── Step 6: Write stategraph ────────────────────────
    log.info("[6/6] Writing _stategraph.json ...")
    sg_path = _task_out(output_dir, task_uuid, "_stategraph.json")
    write_stategraph(task, sg_path)
    log.info("  -> %s", sg_path)

    log.info("Done: 3 output files generated")

    return {
        "payload": str(payload_path),
        "dedup": str(dedup_path),
        "stategraph": str(sg_path),
    }


def run_batch(
    base_dir: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Batch process all task directories under base_dir.
    
    Expected structure:
        base_dir/
        ├── <uuid-1>/
        │   ├── utg.json
        │   ├── clearRes.gzip    (or .gz / .json)
        │   └── catchDataTurnId*/
        ├── <uuid-2>/
        │   └── ...
        └── ...
    
    Returns summary dict with counts and error list.
    """
    base = Path(base_dir)
    if not base.is_dir():
        raise FileNotFoundError(f"Base directory not found: {base_dir}")

    if output_dir is None:
        output_dir = str(base / "reorg_output")
    output_path = Path(output_dir)

    # Collect uuid subdirectories (skip output dir, __pycache__, hidden)
    task_dirs = sorted(
        [d for d in base.iterdir() if d.is_dir()
         and not d.name.startswith('.')
         and d.name not in (output_path.name, '__pycache__')],
        key=lambda d: d.name,
    )

    if not task_dirs:
        log.warning("No task directories found in %s", base_dir)
        return {"total": 0, "ok": 0, "error": 0, "errors": []}

    log.info("=" * 60)
    log.info("Batch Preprocessing Pipeline")
    log.info("=" * 60)
    log.info("Input dir:  %s", base_dir)
    log.info("Output dir: %s", output_dir)
    log.info("Tasks found: %d", len(task_dirs))
    log.info("")

    results: list[dict[str, Any]] = []
    ok_count = 0
    err_count = 0
    errors: list[dict[str, Any]] = []

    for i, task_dir in enumerate(task_dirs, 1):
        uuid = task_dir.name
        try:
            result = run_pipeline(task_dir, output_path)
            results.append({"uuid": uuid, "status": "ok", **result})
            ok_count += 1
        except Exception as e:
            err_count += 1
            errors.append({"uuid": uuid, "status": "error", "error": str(e)})
            log.error("  [%d/%d] %s FAILED: %s", i, len(task_dirs), uuid, e)

        if i % 50 == 0:
            log.info("  Progress: %d/%d | OK: %d | Error: %d", i, len(task_dirs), ok_count, err_count)

    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("Batch Complete")
    log.info("Total: %d | OK: %d | Error: %d", len(task_dirs), ok_count, err_count)
    if errors:
        log.info("Errors: %d tasks failed", err_count)
        for e in errors[:5]:
            log.info("  - %s: %s", e["uuid"], e["error"])
        if len(errors) > 5:
            log.info("  ... and %d more", len(errors) - 5)
    log.info("=" * 60)

    return {
        "total": len(task_dirs),
        "ok": ok_count,
        "error": err_count,
        "errors": errors,
    }


def _task_out(base: Path, uuid: str, filename: str) -> Path:
    """Build output path: <base>/<uuid>/<filename>"""
    d = base / uuid
    d.mkdir(parents=True, exist_ok=True)
    return d / filename


def main():
    parser = argparse.ArgumentParser(
        description="Data preprocessing pipeline (single or batch)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m src.preprocessor.pipeline <task_dir>                        # single task\n"
            "  python -m src.preprocessor.pipeline --batch <base_dir>                # batch all tasks\n"
            "  python -m src.preprocessor.pipeline --batch <base_dir> -o my_output/  # batch + custom output\n"
        ),
    )
    parser.add_argument(
        "task_dir", nargs="?", default=None,
        help="Single task directory (with utg.json + clearRes.gzip)",
    )
    parser.add_argument(
        "--batch", "-b", metavar="BASE_DIR",
        help="Batch mode: process all uuid subdirectories under BASE_DIR",
    )
    parser.add_argument(
        "--output", "-o", metavar="DIR",
        help="Output directory (default: task_dir/reorg_output or base_dir/reorg_output)",
    )
    args = parser.parse_args()

    try:
        if args.batch:
            run_batch(args.batch, args.output)
        elif args.task_dir:
            run_pipeline(args.task_dir, args.output)
        else:
            parser.print_help()
            sys.exit(1)
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
