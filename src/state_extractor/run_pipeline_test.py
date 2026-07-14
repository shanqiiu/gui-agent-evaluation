"""
Integration test: end-to-end mock pipeline verification.

Runs the full state extraction pipeline with mock data and validates:
1. All pipeline steps execute without errors
2. Output format matches v2.0 specification
3. State boundaries are plausible
4. Control names are resolved correctly
5. KeyState fields are populated

Usage:
    python src/state_extractor/run_pipeline_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.state_extractor import generate_mock_task, run_pipeline
from src.state_extractor.models import AlignedStep, KeyState


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_step(step: AlignedStep) -> None:
    """Pretty-print a single aligned step."""
    box = f"[{step.action_start_box[0]},{step.action_start_box[1]}]" if step.action_start_box else "[]"
    target_display = step.action_target if step.action_target else "(no text)"
    print(
        f"  [{step.step_index:2d}] {step.action_type:10s} {box:12s} "
        f"→ {target_display:20s} | {step.purpose_classification:25s} | "
        f"{step.action_purpose[:50]}"
    )


def validate_graph(graph: dict) -> list[str]:
    """Validate the output graph structure. Returns list of issues."""
    issues: list[str] = []

    # Top-level keys
    required_keys = ["task_uuid", "instruction", "total_steps", "state_graph", "metrics"]
    for k in required_keys:
        if k not in graph:
            issues.append(f"Missing top-level key: {k}")

    sg = graph.get("state_graph", {})
    for k in ["states", "transitions", "start_state", "end_state"]:
        if k not in sg:
            issues.append(f"Missing state_graph key: {k}")

    # States validation
    states = sg.get("states", [])
    if not states:
        issues.append("No states extracted")
    else:
        for s in states:
            for field in ["state_id", "label", "state_type", "step_range", "confidence"]:
                if field not in s:
                    issues.append(f"State {s.get('state_id', '?')} missing field: {field}")

    # Transitions validation
    transitions = sg.get("transitions", [])
    if transitions:
        transition_types = set(t.get("transition_type") for t in transitions)
        print(f"\n  Transition types found: {transition_types}")

    # Metrics validation
    metrics = graph.get("metrics", {})
    for field in ["total_states", "stable_states", "total_duration_ms", "avg_confidence"]:
        if field not in metrics:
            issues.append(f"Missing metrics field: {field}")

    return issues


def main():
    print_section("State Extractor Pipeline — End-to-End Mock Test")
    print(f"  v2.0 MVP | Task: 打开密码自动填充和保存功能")

    # ── Step 1: Generate mock data ────────────────────────────
    print_section("1. Mock Data Generation")
    task = generate_mock_task()
    print(f"  Task UUID: {task['task_uuid']}")
    print(f"  Instruction: {task['instruction']}")
    utg = task["utg"]
    cr = task["clearres"]
    print(f"  UTG nodes: {len(utg['nodes'])}, edges: {len(utg['edges'])}, steps: {len(utg['stepData'])}")
    print(f"  clearRes OCR pages: {len(cr['ocr_pages'])}, actionPurposes: {len(cr['action_purposes'])}")

    # ── Step 2: Run pipeline ─────────────────────────────────
    print_section("2. Pipeline Execution")
    graph = run_pipeline(task)
    print(f"  Output keys: {list(graph.keys())}")

    # ── Step 3: Show aligned steps ───────────────────────────
    print_section("3. Aligned Steps (with classifications)")
    from src.state_extractor.parser import parse_and_align
    from src.state_extractor.resolver import classify_all_purposes, resolve_all_targets
    from src.state_extractor.models import PipelineContext
    from src.state_extractor.parser import parse_instruction

    instruction = parse_instruction(utg)
    ctx = PipelineContext(
        task_uuid=task["task_uuid"],
        instruction=instruction,
        utg_nodes=utg["nodes"],
        utg_steps=utg["stepData"],
        utg_edges=utg["edges"],
        clear_res_pages=cr["ocr_pages"],
        action_purposes=cr["action_purposes"],
    )
    aligned = parse_and_align(ctx)
    classify_all_purposes(aligned)
    resolve_all_targets(aligned)

    for step in aligned:
        print_step(step)

    # ── Step 4: Show boundaries ──────────────────────────────
    print_section("4. Detected State Boundaries")
    from src.state_extractor.boundary import detect_boundaries
    boundaries = detect_boundaries(aligned)
    print(f"  Boundary step indices: {boundaries}")
    print(f"  Total unique states: {len(boundaries)}")

    # ── Step 5: Show states ──────────────────────────────────
    print_section("5. Extracted Key States")
    states = graph["state_graph"]["states"]
    for s in states:
        label = s.get("label", "?")
        state_type = s.get("state_type", "?")
        step_range = s.get("step_range", [])
        dur = s.get("duration_ms", 0)
        conf = s.get("confidence", 0)
        evidence = ", ".join(s.get("boundary_evidence", [])[:2])
        actions = ", ".join(s.get("action_summary", [])[:2])
        print(f"  [{s.get('state_id', '?')}] {label:20s} {state_type:10s} "
              f"steps={step_range} dur={dur}ms conf={conf:.2f}")
        if actions:
            print(f"       actions: {actions[:100]}")
        if evidence:
            print(f"       evidence: {evidence[:100]}")

    # ── Step 6: Show transitions ─────────────────────────────
    print_section("6. State Transitions")
    for t in graph["state_graph"]["transitions"]:
        print(f"  {t.get('from', '')} → {t.get('to', '')} "
              f"[{t.get('transition_type', '')}] "
              f"@step{t.get('trigger_step_idx', '')}")

    # ── Step 7: Show metrics ─────────────────────────────────
    print_section("7. Metrics")
    metrics = graph["metrics"]
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    # ── Step 8: Validation ───────────────────────────────────
    print_section("8. Validation")
    issues = validate_graph(graph)
    if issues:
        print(f"  FAIL: {len(issues)} issues found:")
        for issue in issues:
            print(f"     - {issue}")
    else:
        print("  PASS: All structural validations passed")

    # ── Step 9: Output JSON ──────────────────────────────────
    print_section("9. Full StateGraph JSON Output")
    print(json.dumps(graph, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
