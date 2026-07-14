"""
Data parser: converts raw utg.json + clearRes into AlignedStep list.

This module bridges the gap between the raw data formats and the
structured representations used by the rest of the pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from .models import AlignedStep, OCRNode, PipelineContext


# ── Action type parsing (from stepData.action_type) ───────────────

_ACTION_CLICK = re.compile(r"click\((\[.*?\])\)")
_ACTION_SCROLL = re.compile(r"(scroll|swipe|drag)\((\[.*?\]),\s*(\w+)?\)")
_ACTION_EDIT = re.compile(r"(type|edit)\(")
_ACTION_CLARIFY = re.compile(r"clarify\(")
_ACTION_OPEN = re.compile(r"open\(")
_ACTION_FINISHED = re.compile(r"(finished|done|任务完成)")
_ACTION_BACK = re.compile(r"back\(\)", re.IGNORECASE)

_ACTION_NORMALIZE: dict[str, str] = {
    "edit": "type",
    "preCheckDone": "do-nothing",
    "do_nothing()": "do-nothing",
    "scroll custom": "scroll",
}


def _parse_action_type(action_str: str) -> dict:
    """Parse stepData.action_type raw string → structured action dict."""
    at = action_str.strip().rstrip(";")
    result: dict = {"raw_type": at, "action_type": "", "start_box": [], "direction": ""}

    m = _ACTION_CLICK.search(at)
    if m:
        coords_str = m.group(1).strip("[]")
        parts = [int(x.strip()) for x in coords_str.split(",")]
        result["action_type"] = "click"
        result["start_box"] = parts[:2] if len(parts) >= 2 else []
        return result

    m = _ACTION_SCROLL.search(at)
    if m:
        result["action_type"] = m.group(1)
        coords_str = m.group(2).strip("[]")
        parts = [int(x.strip()) for x in coords_str.split(",")]
        result["start_box"] = parts[:2] if len(parts) >= 2 else []
        if m.group(3):
            result["direction"] = m.group(3)
        return result

    if _ACTION_EDIT.search(at):
        result["action_type"] = "type"
        return result

    if _ACTION_CLARIFY.search(at):
        result["action_type"] = "clarify"
        return result

    if _ACTION_OPEN.search(at):
        result["action_type"] = "open_app"
        return result

    if _ACTION_FINISHED.search(at):
        result["action_type"] = "finished"
        return result

    if _ACTION_BACK.search(at):
        result["action_type"] = "back"
        return result

    if at == "":
        result["action_type"] = "noop"
        return result

    result["action_type"] = at
    return result


# ── Directives parsing ────────────────────────────────────────────

def _parse_directives(raw_directives: str) -> dict:
    """
    Extract action details from raw_item.directives JSON string.
    
    Returns:
        {
            "action_type": str,
            "start_box": [x, y],
            "end_box": [x, y],
            "element_text": str,
            "content": str,
        }
    """
    result: dict = {
        "action_type": "",
        "start_box": [],
        "end_box": [],
        "element_text": "",
        "content": "",
    }
    if not raw_directives or raw_directives in ("{}", ""):
        return result

    try:
        directives = json.loads(raw_directives)
    except (json.JSONDecodeError, TypeError):
        return result

    for cmd in directives:
        if not isinstance(cmd, dict):
            continue
        header = cmd.get("header", {})
        if header.get("namespace") != "SimulatingOperation":
            continue
        if header.get("name") != "ExecuteCommand":
            continue

        payload = cmd.get("payload", {})
        actions = payload.get("actions", [])
        for action in actions:
            act_type = action.get("action", "")
            if act_type:
                result["action_type"] = _ACTION_NORMALIZE.get(act_type, act_type)

            params = action.get("params", {})
            points = params.get("points")
            if isinstance(points, list) and len(points) >= 2:
                result["start_box"] = [int(points[0]), int(points[1])]
                if len(points) >= 4:
                    result["end_box"] = [int(points[2]), int(points[3])]
            else:
                node = params.get("node", {})
                bounds = node.get("bounds") if isinstance(node, dict) else None
                if isinstance(bounds, list) and len(bounds) >= 4:
                    result["start_box"] = [
                        int((bounds[0] + bounds[2]) / 2),
                        int((bounds[1] + bounds[3]) / 2),
                    ]

            node = params.get("node", {})
            if isinstance(node, dict):
                if node.get("text"):
                    result["element_text"] = node["text"]
                if node.get("content"):
                    result["content"] = node["content"]

            set_text = action.get("setText") or params.get("content", "")
            if set_text and not result["content"]:
                result["content"] = set_text

    return result


# ── Step alignment ────────────────────────────────────────────────

def _build_ocr_page_map(ocr_pages: list[dict]) -> dict[int, OCRNode]:
    """
    Map step indices to OCR tree snapshots.
    
    Simplified mapping: assign OCR pages in order, cycling if needed.
    In production, this would use imageId or timestamp matching.
    """
    roots = [OCRNode.from_raw(p["nodes"][0]) if p.get("nodes") else OCRNode(
        id="empty", type="layout", text="", content="", bounds=[0, 0, 1280, 2832],
        confidence=0.0, actions=[], ori_type=""
    ) for p in ocr_pages]
    return {i: roots[i % len(roots)] for i in range(len(roots) * 3)}


def parse_and_align(ctx: PipelineContext) -> list[AlignedStep]:
    """
    Parse utg.json + clearRes into aligned AlignedStep list.
    
    This is the entry point for the parser module.
    """
    utg_nodes = {n.get("id"): n for n in ctx.utg_nodes if n.get("id") is not None}
    step_data = ctx.utg_steps

    action_purposes = ctx.action_purposes
    ocr_pages = ctx.clear_res_pages
    ocr_map = _build_ocr_page_map(ocr_pages)

    aligned: list[AlignedStep] = []
    purpose_idx = 0  # Track purpose index separately since we skip thinking steps

    for idx, step in enumerate(step_data):
        sid = str(step.get("stepId", ""))
        if sid in ("home", "end"):
            continue

        action_str = step.get("action_type", "")
        parsed_at = _parse_action_type(action_str)

        # Look up node for directives
        node = None
        for key in [sid, int(sid) if sid.isdigit() else None, int(sid) if sid.isdigit() else None]:
            if key is None:
                continue
            node = utg_nodes.get(key)
            if node:
                break

        # Parse directives
        directives_info = _parse_directives(
            (node or {}).get("raw_item", {}).get("directives", "{}")
            if node else "{}"
        )

        # Skip thinking/reflection steps: no directives, no real UI action
        action_type = directives_info.get("action_type") or parsed_at.get("action_type") or "unknown"
        if action_type in ("unknown", "noop") and not directives_info.get("start_box"):
            continue

        start_box = directives_info.get("start_box") or parsed_at.get("start_box", [])
        element_text = directives_info.get("element_text", "")
        content = directives_info.get("content", "")

        # Action purpose
        purpose = action_purposes[purpose_idx] if purpose_idx < len(action_purposes) else ""
        purpose_idx += 1

        # Screenshot path
        image_url = (node or {}).get("image", "")
        screenshot_path = _extract_local_path(image_url)

        # OCR tree
        ocr_root = ocr_map.get(idx)

        # Cost time
        cost_time = int(step.get("cost_time", "0")) if step.get("cost_time", "0").isdigit() else 0

        aligned.append(AlignedStep(
            step_id=sid,
            step_index=idx,
            action_type=action_type,
            action_start_box=start_box,
            action_end_box=directives_info.get("end_box", []),
            action_target=element_text,
            action_content=content,
            action_purpose=purpose,
            purpose_classification="",  # filled by boundary module
            screenshot_path=screenshot_path,
            screenshot_phash="",  # computed lazily
            ocr_tree_root=ocr_root,
            cost_time_ms=cost_time,
            step_data_raw=action_str,
        ))

    return aligned


def _extract_local_path(image_url: str) -> str:
    """Extract a local-style path from a REST URL or full path."""
    if not image_url:
        return ""
    turn_match = re.search(r"(catchDataTurnId\d+|home|end)", image_url)
    if turn_match:
        return f"{turn_match.group(0)}/temp_image-screenshot-origin.jpg"
    return image_url


def parse_instruction(utg: dict) -> str:
    """Extract the user instruction from utg.json."""
    # Try nodes first
    for node in utg.get("nodes", []):
        title_str = node.get("title", "")
        if title_str:
            try:
                title = json.loads(title_str)
                inst = title.get("instruction", "")
                if inst and inst.strip():
                    return inst.strip()
            except (json.JSONDecodeError, TypeError):
                pass
    # Try edges
    for edge in utg.get("edges", []):
        title_str = edge.get("title", "")
        if title_str:
            try:
                title = json.loads(title_str)
                inst = title.get("instruction", "")
                if inst and inst.strip():
                    return inst.strip()
            except (json.JSONDecodeError, TypeError):
                pass
    return ""
