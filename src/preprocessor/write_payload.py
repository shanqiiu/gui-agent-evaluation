"""
write_payload.py: NormalizedTask → /check_e2e payload.json.

Replaces convert_to_check_e2e.py's payload construction logic.
Uses rawPage-resolved control names and actionPurpose for enriched output.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

from .models import NormalizedTask


def write_payload(
    task: NormalizedTask,
    output_path: str | Path,
    *,
    save_paths: bool = True,
    image_base_dir: str = "",
) -> dict:
    """
    Generate payload.json from NormalizedTask.
    
    Args:
        task: Preprocessed task data
        output_path: Where to write the JSON file
        save_paths: True=relative paths in payload (requires hydrate before send),
                    False=base64 encoded images
        image_base_dir: Base directory for resolving relative image paths
    
    Returns the payload dict.
    """
    output_path = Path(output_path)

    seq_info: list[dict] = []

    for step in task.steps:
        idx = step.step_index

        # Screenshot reference
        img_ref = step.screenshot_path
        if img_ref and not save_paths:
            img_ref = _encode_image(img_ref, Path(image_base_dir) if image_base_dir else None)

        # Action text for parsed_action.text
        text = _make_action_text(step)

        seq_info.append({
            "index": idx,
            "image_relative_path": img_ref,
            "_image_source": step.screenshot_source,
            "_ocr_page_index": step.ocr_page_index,
            "planning_output": {
                "parsed_action": {
                    "action_type": step.action_type,
                    "start_box": step.action_start_box,
                    "end_box": step.action_end_box,
                    "text": text,
                    "direction": step.action_direction,
                    "content": step.action_content or "",
                }
            },
        })

    # Append finished step
    last_idx = len(seq_info)
    seq_info.append({
        "index": last_idx,
        "image_relative_path": "",
        "_image_source": "",
        "planning_output": {
            "parsed_action": {
                "action_type": "finished",
                "start_box": [],
                "end_box": [],
                "text": "任务完成",
                "direction": "",
                "content": "",
            }
        },
    })

    # step_level_instruction: LLM+RAG decomposed sub-goals (if available)
    step_plan = _build_step_level_instruction(task)
    # agent_purposes: Agent's self-reported step-by-step intentions
    agent_purposes = _build_agent_purposes(task)

    payload = {
        "instruction": task.instruction,
        "step_level_instruction": step_plan,
        "agent_purposes": agent_purposes,
        "seq_info": seq_info,
        "_image_base_dir": str(image_base_dir) if image_base_dir else "",
        "_image_mode": "path" if save_paths else "base64",
    }

    # Optional: attach enriched metadata (ignored by /check_e2e, useful for downstream)
    if task.action_purposes:
        payload["_action_purposes"] = task.action_purposes
    if task.ocr_pages:
        payload["_ocr_pages"] = task.ocr_pages
    decomposer_status = getattr(task, "decomposer_status", None)
    if decomposer_status:
        payload["_decomposer"] = decomposer_status
    if task.checkpoints:
        payload["_checkpoints"] = task.checkpoints

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def _make_action_text(step) -> str:
    """Generate human-readable action text, preferring resolved control name."""
    target = step.action_target
    at = step.action_type
    direction = step.action_direction or ""

    if at == "click":
        if target:
            return f"点击{target}"
        if step.action_start_box:
            return "点击页面元素"
        return "点击"
    if at in ("scroll", "swipe", "drag"):
        dir_map = {"down": "向下滑动", "up": "向上滑动", "left": "向左滑动", "right": "向右滑动"}
        if direction:
            return dir_map.get(direction, f"向{direction}滑动")
        return "滑动"
    if at == "type":
        return "输入文本"
    if at == "open_app":
        return "打开应用"
    if at == "clarify":
        return "需手动操作"
    if at == "do-nothing":
        return "等待/检查"
    if at == "finished":
        return "任务完成"
    if at == "back":
        return "返回"
    return at


def _build_step_level_instruction(task: NormalizedTask) -> str:
    """Build step_level_instruction from LLM+RAG decomposed checkpoints."""
    if task.checkpoints:
        names = [c["name"] for c in task.checkpoints if c.get("name")]
        return "->".join(names)
    return ""


def _build_agent_purposes(task: NormalizedTask) -> str:
    """Build agent_purposes from Agent's self-reported actionPurpose log."""
    purposes = [s.action_purpose for s in task.steps if s.action_purpose]
    return "->".join(purposes)


def _encode_image(rel_path: str, base_dir: Optional[Path]) -> str:
    """Read image file and return base64 string."""
    if not rel_path:
        return ""
    full_path = (base_dir / rel_path) if base_dir else Path(rel_path)
    if not full_path.is_file():
        return ""
    with open(full_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
