"""
Pipeline orchestrator: preprocess → write payload, dedup, stategraph.

Usage:
    python -m data.pipeline <task_dir> [--output <output_dir>]

    task_dir:    Single task directory with utg.json + clearRes.gzip
    output_dir:  Output directory (default: task_dir/reorg_output)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from .preprocessor import preprocess
from .write_payload import write_payload
from .write_dedup import write_dedup
from .write_stategraph import write_stategraph

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


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
    output_dir.mkdir(parents=True, exist_ok=True)

    task_uuid = task_dir.name
    log.info("=" * 60)
    log.info("Preprocessing pipeline: %s", task_uuid)

    # ── Step 1: Preprocess ──────────────────────────────
    log.info("[1/4] Parsing utg.json + clearRes ...")
    task = preprocess(task_dir)
    log.info("  instruction: %s", task.instruction[:60])
    log.info("  action steps: %d (raw: %d)", task.total_action_steps, task.total_raw_steps)
    log.info("  OCR pages: %d, actionPurposes: %d",
             len(task.ocr_pages), len(task.action_purposes))

    # ── Step 2: Write payload ───────────────────────────
    log.info("[2/4] Writing payload.json ...")
    payload_path = _task_out(output_dir, task_uuid, "payload.json")
    write_payload(task, payload_path)
    log.info("  → %s", payload_path)

    # ── Step 3: Write dedup ─────────────────────────────
    log.info("[3/4] Writing _deduped.json ...")
    dedup_path = _task_out(output_dir, task_uuid, "_deduped.json")
    write_dedup(task, dedup_path)
    log.info("  → %s", dedup_path)

    # ── Step 4: Write stategraph ────────────────────────
    log.info("[4/4] Writing _stategraph.json ...")
    sg_path = _task_out(output_dir, task_uuid, "_stategraph.json")
    write_stategraph(task, sg_path)
    log.info("  → %s", sg_path)

    log.info("=" * 60)
    log.info("Done: 3 output files generated")

    return {
        "payload": str(payload_path),
        "dedup": str(dedup_path),
        "stategraph": str(sg_path),
    }


def _task_out(base: Path, uuid: str, filename: str) -> Path:
    """Build output path: <base>/<uuid>/<filename>"""
    d = base / uuid
    d.mkdir(parents=True, exist_ok=True)
    return d / filename


def main():
    parser = argparse.ArgumentParser(description="Data preprocessing pipeline")
    parser.add_argument("task_dir", help="Task directory (with utg.json + clearRes.gzip)")
    parser.add_argument("--output", "-o", help="Output directory (default: task_dir/reorg_output)")
    args = parser.parse_args()

    try:
        run_pipeline(args.task_dir, args.output)
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
