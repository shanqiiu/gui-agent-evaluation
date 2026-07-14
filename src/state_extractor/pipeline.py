"""
End-to-end state extraction pipeline.

Orchestrates the complete flow:
  1. Parse: utg.json + clearRes → AlignedStep list
  2. Resolve: classify actionPuroses, resolve target names  
  3. Detect: identify state boundaries
  4. Aggregate: group into KeyStates, merge/clean
  5. Build: construct StateGraph with transitions and metrics

Usage:
    from state_extractor.pipeline import extract_states
    
    task_data = {"utg": {...}, "clearres": {...}}
    graph = extract_states(task_data, task_uuid="...")
    print(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2))
"""

from __future__ import annotations

import json
from typing import Any

from .models import PipelineContext
from .parser import parse_and_align, parse_instruction
from .resolver import classify_all_purposes, resolve_all_targets
from .boundary import detect_boundaries
from .aggregator import aggregate_states
from .graph import build_graph


def extract_states(
    utg: dict,
    clearres: dict | None = None,
    *,
    task_uuid: str = "",
) -> dict:
    """
    Extract state graph from utg.json and optional clearRes data.
    
    This is the main entry point for the state extraction pipeline.
    
    Args:
        utg: Complete utg.json data dict
        clearres: Optional dict with keys:
            - action_purposes: list[str]
            - ocr_pages: list[dict] (clearRes rawPage entries)
        task_uuid: Task identifier
    
    Returns:
        StateGraph as JSON-compatible dict (matching v2.0 output format)
    """
    clearres = clearres or {"action_purposes": [], "ocr_pages": []}

    # Build context
    instruction = parse_instruction(utg)
    ctx = PipelineContext(
        task_uuid=task_uuid,
        instruction=instruction,
        utg_nodes=utg.get("nodes", []),
        utg_steps=utg.get("stepData", []),
        utg_edges=utg.get("edges", []),
        clear_res_pages=clearres.get("ocr_pages", []),
        action_purposes=clearres.get("action_purposes", []),
    )

    # Step 1: Parse & align
    aligned = parse_and_align(ctx)
    ctx.aligned_steps = aligned

    # Step 2: Classify & resolve
    classify_all_purposes(aligned)
    resolve_all_targets(aligned)

    # Step 3: Detect boundaries
    boundaries = detect_boundaries(aligned)
    ctx.boundaries = boundaries

    # Step 4: Aggregate states
    states = aggregate_states(aligned, boundaries)
    ctx.merged_states = states

    # Step 5: Build graph
    graph = build_graph(
        states=states,
        task_uuid=ctx.task_uuid,
        instruction=ctx.instruction,
        total_steps=len(aligned),
    )
    ctx.graph = graph

    return graph.to_dict()


def run_pipeline(task_data: dict[str, Any]) -> dict:
    """
    Convenience wrapper that takes a complete task data dict.
    
    Args:
        task_data: {
            "task_uuid": str,
            "instruction": str,  # optional, will be parsed from utg if missing
            "utg": dict,
            "clearres": dict,    # optional
        }
    
    Returns:
        StateGraph dict
    """
    return extract_states(
        utg=task_data["utg"],
        clearres=task_data.get("clearres"),
        task_uuid=task_data.get("task_uuid", ""),
    )
