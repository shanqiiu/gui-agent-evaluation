"""
Pipeline orchestrator: preprocess → copy screenshots → write payload, dedup, stategraph.

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
    ├── 0.jpg                 ← step 0 截图
    ├── 1.jpg                 ← step 1 截图
    └── ...
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from .preprocessor import preprocess
from .write_payload import write_payload
from .write_dedup import write_dedup
from .write_stategraph import write_stategraph

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _copy_screenshots(
    task: Any, task_dir: Path, screenshot_dir: Path
) -> int:
    """Copy screenshots from catchDataTurnIdN/ to output dir as {step_index}.jpg."""
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for step in task.steps:
        if not step.screenshot_path:
            continue
        src = task_dir / step.screenshot_path
        if not src.is_file():
            continue
        dst = screenshot_dir / f"{step.step_index}.jpg"
        shutil.copy2(src, dst)
        step.screenshot_path = f"{step.step_index}.jpg"
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
    log.info("[1/5] Parsing utg.json + clearRes ...")
    task = preprocess(task_dir)
    log.info("  instruction: %s", task.instruction[:60])
    log.info("  action steps: %d (raw: %d)", task.total_action_steps, task.total_raw_steps)
    log.info("  OCR pages: %d, actionPurposes: %d",
             len(task.ocr_pages), len(task.action_purposes))

    # ── Step 2: Copy screenshots ─────────────────────────
    log.info("[2/5] Copying screenshots to output ...")
    screenshot_dir = output_dir / task_uuid
    n_copied = _copy_screenshots(task, task_dir, screenshot_dir)
    log.info("  copied: %d screenshots", n_copied)

    # ── Step 3: Write payload ───────────────────────────
    log.info("[3/5] Writing payload.json ...")
    payload_path = _task_out(output_dir, task_uuid, "payload.json")
    write_payload(task, payload_path, image_base_dir=str(screenshot_dir))
    log.info("  -> %s", payload_path)

    # ── Step 4: Write dedup ─────────────────────────────
    log.info("[4/5] Writing _deduped.json ...")
    dedup_path = _task_out(output_dir, task_uuid, "_deduped.json")
    write_dedup(task, dedup_path)
    log.info("  -> %s", dedup_path)

    # ── Step 5: Write stategraph ────────────────────────
    log.info("[5/5] Writing _stategraph.json ...")
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

