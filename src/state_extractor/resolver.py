"""
Control name resolver: resolves target element names from clearRes OCR tree.

Handles the case where directives.params.node.text is empty (icon elements)
by searching the OCR tree for sibling text nodes.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import AlignedStep, OCRNode


# ── actionPurpose semantic classification ─────────────────────────

_PURPOSE_PATTERNS = [
    (r"(滑动|滚动|翻页|查看|浏览|寻找|未出现|已出现|可见)", "in_state_exploration"),
    (r"(输入|填写|勾选|选择|切换|修改|搜索)", "in_state_interaction"),
    (r"(进入|打开|点击.*进入|跳转|返回上级|退出应用|启动应用)", "state_transition"),
    (r"(完成|手动|无法|需要.*验证|提示用户|任务完成)", "terminal"),
]


def classify_purpose(action_purpose: str) -> str:
    """Classify actionPurpose text into one of four categories."""
    if not action_purpose:
        return "unknown"
    for pattern, label in _PURPOSE_PATTERNS:
        if re.search(pattern, action_purpose):
            return label
    return "in_state_exploration"


def classify_all_purposes(steps: list[AlignedStep]) -> None:
    """Classify actionPurpose for all steps in-place."""
    for step in steps:
        step.purpose_classification = classify_purpose(step.action_purpose)


# ── Control name resolution ───────────────────────────────────────

def resolve_target_name(step: AlignedStep) -> str:
    """
    Resolve the human-readable target element name for a step.
    
    Strategy (in priority order):
    1. directives.params.node.text (already stored in action_target)
    2. clearRes OCR tree: find node at touch point, return its text
    3. OCR tree: if touched node is icon/text with empty text → find sibling text
    4. Return empty string if no match
    """
    # Strategy 1: already have text from directives
    if step.action_target.strip():
        return step.action_target

    # Strategy 2 & 3: search OCR tree
    if not step.ocr_tree_root or not step.action_start_box:
        return ""

    x, y = step.action_start_box[0], step.action_start_box[1]
    touched = step.ocr_tree_root.find_node_at_point(x, y)
    if not touched:
        return ""

    # Direct text on touched node
    if touched.text.strip():
        return touched.text.strip()

    # Strategy 3: icon/layout with empty text → sibling text
    sibling_texts = touched.get_sibling_texts(step.ocr_tree_root)
    if sibling_texts:
        return sibling_texts[0]

    # Strategy 4: check parent for text
    parent = touched.get_parent(step.ocr_tree_root)
    if parent and parent.text.strip():
        return parent.text.strip()

    # Last resort: search all text nodes in the tree near the touch point
    all_texts = step.ocr_tree_root.collect_all_texts()
    if all_texts:
        # Find closest text to touch point
        closest = min(
            all_texts,
            key=lambda t: _point_distance(x, y, t.get("bounds", [0, 0, 0, 0])),
            default=None,
        )
        if closest:
            return closest.get("text", "")

    return ""


def resolve_all_targets(steps: list[AlignedStep]) -> None:
    """Resolve target names for all steps in-place."""
    for step in steps:
        resolved = resolve_target_name(step)
        if resolved and not step.action_target.strip():
            step.action_target = resolved


def _point_distance(x: int, y: int, bounds: list[int]) -> float:
    """Distance from point to center of bounds."""
    if len(bounds) < 4:
        return float("inf")
    cx = (bounds[0] + bounds[2]) / 2
    cy = (bounds[1] + bounds[3]) / 2
    return ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
