"""
Unified preprocessor: parse utg.json + clearRes → NormalizedTask.

Parses once, produces a single NormalizedTask.  All downstream writers
(payload / dedup / stategraph) consume this task directly.

Resolver function handles the rawPage fallback for icon element names.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from .models import NormalizedStep, NormalizedTask
from .clearres_parser import parse_clearres_light


# ── Regular expressions (from convert_to_check_e2e.py) ───────────

_TURN_RE = re.compile(r"catchDataTurnId(\d+)")
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

# Action types that correspond to real UI operations (consume an actionPurpose)
_REAL_ACTIONS = frozenset({"click", "scroll", "type", "swipe", "drag",
                            "back", "open_app", "long_press", "finished"})


# ── Action type parsing ──────────────────────────────────────────

def _parse_action_type(action_str: str) -> dict:
    at = action_str.strip().rstrip(";")
    result: dict = {"raw_type": at, "action_type": "", "start_box": [], "direction": ""}

    m = _ACTION_CLICK.search(at)
    if m:
        parts = _coords_to_list(m.group(1))
        result["action_type"] = "click"
        result["start_box"] = parts[:2] if len(parts) >= 2 else []
        return result

    m = _ACTION_SCROLL.search(at)
    if m:
        result["action_type"] = m.group(1)
        parts = _coords_to_list(m.group(2))
        result["start_box"] = parts[:2] if len(parts) >= 2 else []
        if m.group(3):
            result["direction"] = m.group(3)
        return result

    if _ACTION_EDIT.search(at):
        result["action_type"] = "type"; return result
    if _ACTION_CLARIFY.search(at):
        result["action_type"] = "clarify"; return result
    if _ACTION_OPEN.search(at):
        result["action_type"] = "open_app"; return result
    if _ACTION_FINISHED.search(at):
        result["action_type"] = "finished"; return result
    if _ACTION_BACK.search(at):
        result["action_type"] = "back"; return result
    if at == "":
        result["action_type"] = "noop"; return result
    result["action_type"] = at
    return result


def _coords_to_list(s: str) -> list[int]:
    s = s.strip("[]")
    try:
        return [int(x.strip()) for x in s.split(",")]
    except (ValueError, TypeError):
        return []


# ── Directives parsing ───────────────────────────────────────────

def _parse_directives(raw_directives: str) -> dict:
    result: dict = {
        "action_type": "", "start_box": [], "end_box": [],
        "element_text": "", "content": "",
    }
    if not raw_directives or raw_directives in ("{}", ""):
        return result
    try:
        directives = json.loads(raw_directives)
    except (json.JSONDecodeError, TypeError):
        return result

    for cmd in directives:
        if not isinstance(cmd, dict): continue
        h = cmd.get("header", {})
        if h.get("namespace") != "SimulatingOperation": continue
        if h.get("name") != "ExecuteCommand": continue

        for action in (cmd.get("payload", {}).get("actions") or []):
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

    return result


# ── rawPage control name resolution ──────────────────────────────

def _find_node_at_point(ocr_node: dict, x: int, y: int) -> dict | None:
    """Find the deepest OCR tree node containing (x, y)."""
    best: dict | None = None
    for sub in ocr_node.get("subNodes", []):
        if _bounds_contain(sub.get("bounds", []), x, y):
            deeper = _find_node_at_point(sub, x, y)
            if deeper:
                if best is None or len(deeper.get("id", "")) > len(best.get("id", "")):
                    best = deeper
    if best:
        return best
    if _bounds_contain(ocr_node.get("bounds", []), x, y):
        return ocr_node
    return None


def _bounds_contain(bounds: list[int], x: int, y: int) -> bool:
    if len(bounds) < 4:
        return False
    return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]


def _resolve_from_rawpage(coords: list[int], ocr_page: dict) -> str:
    """Resolve control name from rawPage OCR tree for a given coordinate."""
    if not coords or len(coords) < 2:
        return ""
    if not ocr_page or not ocr_page.get("nodes"):
        return ""
    
    x, y = coords[0], coords[1]
    root = ocr_page["nodes"][0]
    touched = _find_node_at_point(root, x, y)
    if not touched:
        return ""

    # Direct text
    if touched.get("text", "").strip():
        return touched["text"].strip()

    # icon with empty text → sibling text
    if touched.get("type") == "icon" or not touched.get("text"):
        parent = _find_parent(root, touched.get("id", ""))
        if parent:
            texts = [
                s["text"] for s in parent.get("subNodes", [])
                if s.get("type") == "text" and s.get("text", "").strip()
            ]
            if texts:
                return texts[0]

    return ""


def _find_parent(ocr_node: dict, target_id: str) -> dict | None:
    for sub in ocr_node.get("subNodes", []):
        if sub.get("id") == target_id:
            return ocr_node
        result = _find_parent(sub, target_id)
        if result:
            return result
    return None


# ── Preprocessor ─────────────────────────────────────────────────

def preprocess(task_dir: str | Path) -> NormalizedTask:
    """
    Parse all data sources for a single task directory.
    
    Expected directory structure:
        <task_dir>/
        ├── utg.json
        ├── clearRes.gzip  (or clearRes.json)
        └── catchDataTurnIdN/
            └── temp_image-screenshot-origin.jpg
    
    Returns a NormalizedTask ready for downstream writers.
    """
    task_dir = Path(task_dir)
    task_uuid = task_dir.name

    # ── 1. Load utg.json ────────────────────────────────────
    utg_path = task_dir / "utg.json"
    if not utg_path.is_file():
        raise FileNotFoundError(f"utg.json not found: {utg_path}")
    with open(utg_path, "r", encoding="utf-8") as f:
        utg = json.load(f)

    # ── 2. Load clearRes (if available) ─────────────────────
    clearres_data = _try_load_clearres(task_dir)

    # ── 3. Extract instruction ──────────────────────────────
    instruction = _extract_instruction(utg)

    # ── 4. Build node index ─────────────────────────────────
    node_by_id: dict = {}
    for node in utg.get("nodes", []):
        nid = node.get("id")
        if nid is not None:
            node_by_id[nid] = node
            node_by_id[str(nid)] = node
            if isinstance(nid, str) and nid.isdigit():
                node_by_id[int(nid)] = node

    # ── 5. Build edge index (by 'to' node) ──────────────────
    edge_by_to: dict[str, list[dict]] = {}
    for edge in utg.get("edges", []):
        to_id = str(edge.get("to", ""))
        edge_by_to.setdefault(to_id, []).append(edge)

    # ── 6. Parse action steps (filter thinking/reflection) ──
    action_purposes = clearres_data.get("action_purposes", [])
    ocr_pages = clearres_data.get("ocr_pages", [])
    purpose_idx = 0

    steps: list[NormalizedStep] = []
    last_screenshot = ""

    for sd in utg.get("stepData", []):
        sid = str(sd.get("stepId", ""))
        if sid in ("home", "end"):
            continue

        node = node_by_id.get(sid)
        if sid.isdigit() and node is None:
            node = node_by_id.get(int(sid))

        # Parse directives
        raw_item = (node or {}).get("raw_item") or {}
        directives_str = raw_item.get("directives", "")
        dir_info = _parse_directives(directives_str)

        # Parse action_type string
        at_str = sd.get("action_type", "")
        parsed_at = _parse_action_type(at_str)

        # Determine action type and coords
        action_type = dir_info.get("action_type") or parsed_at.get("action_type") or "unknown"
        start_box = dir_info.get("start_box") or parsed_at.get("start_box", [])
        end_box = dir_info.get("end_box", [])
        element_text = dir_info.get("element_text", "")
        content = dir_info.get("content", "")
        direction = parsed_at.get("direction", "")

        # Filter thinking/reflection (no directives, no real action)
        if action_type in ("unknown", "noop") and not start_box:
            continue

        # Action purpose: only consume for real UI actions (skip clarify/context steps)
        if action_type in _REAL_ACTIONS:
            purpose = action_purposes[purpose_idx] if purpose_idx < len(action_purposes) else ""
            purpose_idx += 1
        else:
            purpose = ""

        # Screenshot
        node_img = (node or {}).get("image", "")
        ss_path = _image_to_local_path(node_img)
        if not ss_path and last_screenshot:
            ss_path = last_screenshot
        if ss_path:
            last_screenshot = ss_path

        # Edge data
        edges = edge_by_to.get(sid, [])
        edge_from = None
        edge_events: list[dict] = []
        edge_view_images: list[str] = []
        if edges:
            e0 = edges[0]
            edge_from = e0.get("from")
            edge_events = e0.get("events", [])
            edge_view_images = e0.get("view_images", [])

        # rawPage control name resolution
        resolved_target = element_text
        if not resolved_target and start_box and ocr_pages:
            # Assign OCR page by matching purpose index
            ocr_idx = min(purpose_idx - 1, len(ocr_pages) - 1)
            if ocr_idx >= 0:
                resolved_target = _resolve_from_rawpage(start_box, ocr_pages[ocr_idx])

        # Cost time
        cost_time = int(sd.get("cost_time", "0") or "0")

        steps.append(NormalizedStep(
            step_id=sid,
            step_index=len(steps),
            action_type=action_type,
            action_start_box=start_box,
            action_end_box=end_box,
            action_target=resolved_target,
            action_content=content,
            action_direction=direction,
            action_raw_str=at_str,
            cost_time_ms=cost_time,
            step_type=sd.get("type", ""),
            thought=sd.get("thought", ""),
            action_purpose=purpose,
            screenshot_path=ss_path,
            screenshot_source=node_img,
            edge_from=edge_from,
            edge_to=sid,
            edge_events=edge_events,
            edge_view_images=edge_view_images,
            node_id=(node or {}).get("id", ""),
            node_label=(node or {}).get("label", ""),
            node_shape=(node or {}).get("shape", ""),
            ocr_page_index=purpose_idx - 1,
        ))

    return NormalizedTask(
        task_uuid=task_uuid,
        instruction=instruction,
        steps=steps,
        ocr_pages=ocr_pages,
        total_raw_steps=len(utg.get("stepData", [])),
        total_action_steps=len(steps),
        total_duration_ms=sum(s.cost_time_ms for s in steps),
    )


def _extract_instruction(utg: dict) -> str:
    for node in utg.get("nodes", []):
        ts = node.get("title", "")
        if ts:
            try:
                t = json.loads(ts)
                i = t.get("instruction", "").strip()
                if i: return i
            except (json.JSONDecodeError, TypeError):
                pass
    for edge in utg.get("edges", []):
        ts = edge.get("title", "")
        if ts:
            try:
                t = json.loads(ts)
                i = t.get("instruction", "").strip()
                if i: return i
            except (json.JSONDecodeError, TypeError):
                pass
    return ""


def _image_to_local_path(image_url: str) -> str:
    if not image_url:
        return ""
    m = _TURN_RE.search(image_url)
    if m:
        return f"catchDataTurnId{m.group(1)}/temp_image-screenshot-origin.jpg"
    if "home" in image_url:
        return "home/temp_image-screenshot-origin.jpg"
    if "end" in image_url:
        return "end/temp_image-screenshot-origin.jpg"
    return image_url


def _try_load_clearres(task_dir: Path) -> dict[str, Any]:
    # Try common naming conventions in priority order
    candidates = [
        task_dir / "clearRes.gzip",
        task_dir / "clearRes.gz",
        task_dir / "clearRes.json",
        task_dir / "clearRes.zip",
        task_dir / "clearRes",          # no extension (plain JSON)
    ]
    for p in candidates:
        if p.is_file():
            return parse_clearres_light(p)
    # Also try parent directory (for reorg_output layout)
    for suffix in (".gzip", ".gz", ".json", ".zip"):
        p = task_dir.parent / "clearRes" / f"{task_dir.name}{suffix}"
        if p.is_file():
            return parse_clearres_light(p)
    return {"ocr_pages": [], "action_purposes": []}
