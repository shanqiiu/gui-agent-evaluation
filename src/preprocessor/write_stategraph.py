"""
write_stategraph.py: NormalizedTask → _stategraph.json.

Delegates to src/state_extractor for the core state extraction pipeline.
The NormalizedTask provides pre-aligned data (AlignedStep equivalent).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .models import NormalizedTask


def write_stategraph(task: NormalizedTask, output_path: str | Path) -> dict:
    """
    Generate _stategraph.json from NormalizedTask.
    
    Converts NormalizedSteps into AlignedSteps internally for the
    state_extractor pipeline, then outputs the StateGraph dict.
    """
    output_path = Path(output_path)
    graph = _build_full_graph(task)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    return graph


def _build_full_graph(task: NormalizedTask) -> dict:
    """Build full StateGraph using state_extractor pipeline."""
    # Guard: these imports may fail if state_extractor is not installed
    try:
        from state_extractor.models import AlignedStep, OCRNode
        from state_extractor.resolver import classify_all_purposes, resolve_all_targets
        from state_extractor.boundary import compute_ocr_fingerprint, detect_boundaries
        from state_extractor.aggregator import aggregate_states
        from state_extractor.graph import build_graph
    except ImportError:
        return _build_minimal_graph(task)

    # Convert NormalizedStep → AlignedStep
    aligned = []
    for ns in task.steps:
        ocr_root = None
        if ns.ocr_page_index >= 0 and ns.ocr_page_index < len(task.ocr_pages):
            page = task.ocr_pages[ns.ocr_page_index]
            if page.get("nodes"):
                ocr_root = OCRNode.from_raw(page["nodes"][0])

        aligned.append(AlignedStep(
            step_id=ns.step_id,
            step_index=ns.step_index,
            action_type=ns.action_type,
            action_start_box=ns.action_start_box,
            action_end_box=ns.action_end_box,
            action_target=ns.action_target,
            action_content=ns.action_content,
            action_purpose=ns.action_purpose,
            purpose_classification="",
            screenshot_path=ns.screenshot_path,
            screenshot_phash="",
            ocr_tree_root=ocr_root,
            cost_time_ms=ns.cost_time_ms,
            step_data_raw=ns.action_raw_str,
        ))

    classify_all_purposes(aligned)
    resolve_all_targets(aligned)
    boundaries = detect_boundaries(aligned)
    states = aggregate_states(aligned, boundaries)
    graph = build_graph(states, task.task_uuid, task.instruction, len(aligned))
    return graph.to_dict()


def _build_minimal_graph(task: NormalizedTask) -> dict:
    """Build a minimal StateGraph when state_extractor is not available."""
    return {
        "task_uuid": task.task_uuid,
        "instruction": task.instruction,
        "total_steps": task.total_action_steps,
        "state_graph": {
            "states": [],
            "transitions": [],
            "start_state": "",
            "end_state": "",
        },
        "metrics": {},
    }
