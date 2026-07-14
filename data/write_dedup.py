"""
write_dedup.py: NormalizedTask → _deduped.json.

Replaces extract_utg.py's dedup logic. Uses rawPage-resolved control names
for enriched target fields in both steps[] and nodes[].actions[].
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .models import NormalizedTask, NormalizedStep


_IMG_RE = re.compile(r'(catchDataTurnId\d+|home|end)/temp_image-screenshot-origin\.jpg')


def write_dedup(task: NormalizedTask, output_path: str | Path) -> dict:
    """
    Generate _deduped.json from NormalizedTask.
    """
    output_path = Path(output_path)

    # ── Build steps ────────────────────────────────────────
    dedup_steps = _build_steps(task)

    # ── Build nodes ────────────────────────────────────────
    dedup_nodes = _build_nodes(task)

    # ── Build edges ────────────────────────────────────────
    dedup_edges = _build_edges(task)

    result = {
        "instruction": task.instruction,
        "steps": dedup_steps,
        "nodes": dedup_nodes,
        "edges": dedup_edges,
    }

    # Metrics
    raw_json = json.dumps(result, ensure_ascii=False)
    result["_meta"] = {
        "output_size_bytes": len(raw_json),
        "node_count": len(dedup_nodes),
        "edge_count": len(dedup_edges),
        "step_count": len(dedup_steps),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    return result


def _build_steps(task: NormalizedTask) -> list[dict]:
    out = []
    for step in task.steps:
        entry: dict[str, Any] = {
            "stepId": step.step_id,
            "action_type": step.action_type,
        }
        if step.action_start_box:
            entry["start_box"] = step.action_start_box
        if step.action_end_box:
            entry["end_box"] = step.action_end_box
        if step.action_target:
            entry["target"] = step.action_target
        if step.action_direction:
            entry["direction"] = step.action_direction
        if step.cost_time_ms:
            entry["cost_time"] = str(step.cost_time_ms)
        if step.step_type:
            entry["type"] = step.step_type
        if step.action_purpose:
            entry["purpose"] = step.action_purpose
        out.append(entry)
    return out


def _build_nodes(task: NormalizedTask) -> list[dict]:
    seen_ids: set = set()
    nodes = []
    for step in task.steps:
        nid = step.node_id
        if not nid or nid in seen_ids:
            continue
        seen_ids.add(nid)

        n: dict[str, Any] = {
            "id": nid,
            "label": step.node_label,
            "shape": step.node_shape,
        }

        # Image
        if step.screenshot_path:
            m = _IMG_RE.search(step.screenshot_path)
            if m:
                n["image"] = m.group(0)
            elif step.screenshot_source.startswith("/rest/"):
                n["image"] = "[rest_image]"
            else:
                n["image"] = step.screenshot_path

        # Actions (from directives, enriched with rawPage target)
        if step.action_type and step.action_type not in ("unknown", "noop"):
            actions: list[dict[str, Any]] = [{
                "type": step.action_type,
                "target": step.action_target,
            }]
            if step.action_start_box:
                actions[0]["start_box"] = step.action_start_box
            if step.action_end_box:
                actions[0]["end_box"] = step.action_end_box
            n["actions"] = actions

        if step.action_purpose:
            n["purpose"] = step.action_purpose

        nodes.append(n)
    return nodes


def _build_edges(task: NormalizedTask) -> list[dict]:
    edges = []
    for step in task.steps:
        if step.edge_from is None:
            continue
        e: dict[str, Any] = {
            "from": step.edge_from,
            "to": step.edge_to,
        }
        if step.cost_time_ms:
            e["costTime"] = f"{step.cost_time_ms}ms"

        # Events
        parsed_events = []
        for evt in step.edge_events:
            pe: dict[str, Any] = {"event_str": evt.get("event_str", "")}
            parsed = _parse_event_type(evt.get("event_type", ""))
            if parsed:
                pe["action"] = parsed
            parsed_events.append(pe)
        if parsed_events:
            e["events"] = parsed_events

        # View images
        simplified = []
        for img in step.edge_view_images:
            m = _IMG_RE.search(img)
            if m:
                simplified.append(m.group(0))
        if simplified:
            e["view_images"] = simplified

        edges.append(e)
    return edges


def _parse_event_type(raw: str) -> dict | None:
    if not raw:
        return None
    evt: dict | None = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            evt = parsed[0]
        elif isinstance(parsed, dict):
            evt = parsed
    except (json.JSONDecodeError, TypeError):
        return None
    if evt is None:
        return None

    etype = evt.get("type", "")
    if etype == "click":
        start_box: list[int] = []
        points = evt.get("points")
        if isinstance(points, list) and len(points) >= 2:
            start_box = [int(points[0]), int(points[1])]
        else:
            bounds = evt.get("bounds")
            if isinstance(bounds, list) and len(bounds) >= 4:
                start_box = [int((bounds[0]+bounds[2])/2), int((bounds[1]+bounds[3])/2)]
        result: dict[str, Any] = {"type": "click", "target": evt.get("nodeText", "")}
        if start_box:
            result["start_box"] = start_box
        return result
    if etype == "scroll custom":
        return {"type": "scroll", "direction": "custom", "points": evt.get("points")}
    if etype == "clarify":
        return {"type": "clarify", "message": evt.get("setText", "")}
    return None


# Alias for backward compatibility with NormisedTask's attribute name
NormisedStep = NormalizedStep
