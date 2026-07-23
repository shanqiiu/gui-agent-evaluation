"""Grounding-error detection for GUI Agent evaluation.

A grounding error occurs when an action's physical target (tap coordinate,
input field, scroll direction/distance) is incorrect, causing the action to
either fail or land on the wrong UI element even though the agent's intent
was correct.

This module is rule-based: it consumes evidence already produced by the
baseline pipeline (AB validator, state sequence, visual evidence) and does
not make additional VLM/LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_TAP_ACTIONS = frozenset({"click", "tap", "long_press", "double_click"})
_INPUT_ACTIONS = frozenset({"input", "type", "enter", "replace_text"})
_SCROLL_ACTIONS = frozenset({"scroll", "swipe", "drag", "scroll_up", "scroll_down"})


@dataclass
class GroundingEvent:
    subtype: str
    confidence: float
    first_error_step: int
    end_step: int = -1
    related_subtask_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": "grounding_error",
            "subtype": self.subtype,
            "first_error_step": self.first_error_step,
            "end_step": self.end_step if self.end_step >= 0 else self.first_error_step,
            "related_subtask_id": self.related_subtask_id,
            "evidence_refs": self.evidence_refs,
            "message": self.message,
            "recovery_outcome": "unknown",
            "impact": "unknown",
            "confidence": round(self.confidence, 3),
        }


def detect_grounding_errors(
    payload: dict[str, Any],
    *,
    ab_report: Any = None,
    state_sequence: Any = None,
) -> list[GroundingEvent]:
    """Detect grounding errors from baseline pipeline evidence.

    Returns a list of GroundingEvent objects, one per detected error.
    """
    events: list[GroundingEvent] = []
    ab_by_step = _ab_index(ab_report)
    states = _state_items(state_sequence)

    for state_idx, state in enumerate(states):
        action_types = _safe_list(state.get("action_types"))
        step_range = _step_range(state)
        first_step = step_range[0] if step_range else -1

        if first_step < 0:
            continue

        # Collect action types across this state's steps
        all_types: set[str] = set()
        for at in action_types:
            all_types.add(str(at).strip().lower())

        # ── wrong_tap_target ──
        tap_steps = _action_steps_in_range(payload, step_range, _TAP_ACTIONS)
        if tap_steps:
            if _has_unexpected_ab_for_steps(ab_by_step, tap_steps):
                vis = _visual_change(state)
                if _is_minimal_visual_change(vis):
                    events.append(GroundingEvent(
                        subtype="wrong_tap_target",
                        confidence=0.74,
                        first_error_step=min(tap_steps),
                        end_step=max(tap_steps),
                        evidence_refs=[f"state_sequence.states[{state_idx}]"],
                        message=_build_tap_message(tap_steps, state),
                    ))

        # ── wrong_input_location ──
        input_steps = _action_steps_in_range(payload, step_range, _INPUT_ACTIONS)
        if input_steps:
            if _has_unexpected_ab_for_steps(ab_by_step, input_steps):
                ocr_changed = _ocr_changed(state)
                if not ocr_changed:
                    events.append(GroundingEvent(
                        subtype="wrong_input_location",
                        confidence=0.70,
                        first_error_step=min(input_steps),
                        end_step=max(input_steps),
                        evidence_refs=[f"state_sequence.states[{state_idx}]"],
                        message=_build_input_message(input_steps, state),
                    ))

        # ── wrong_scroll_direction ──
        scroll_steps = _action_steps_in_range(payload, step_range, _SCROLL_ACTIONS)
        if scroll_steps:
            if _has_unexpected_ab_for_steps(ab_by_step, scroll_steps):
                vis = _visual_change(state)
                if _is_minimal_visual_change(vis):
                    events.append(GroundingEvent(
                        subtype="wrong_scroll_direction",
                        confidence=0.68,
                        first_error_step=min(scroll_steps),
                        end_step=max(scroll_steps),
                        evidence_refs=[f"state_sequence.states[{state_idx}]"],
                        message=_build_scroll_message(scroll_steps, state),
                    ))

    return events


# ── helpers ──────────────────────────────────────────────────────────


def _ab_index(ab_report: Any) -> dict[int, dict[str, Any]]:
    """Build step-indexed AB result dict."""
    index: dict[int, dict[str, Any]] = {}
    if ab_report is None:
        return index
    results = None
    if hasattr(ab_report, "results"):
        results = ab_report.results
    elif isinstance(ab_report, dict):
        results_dict = ab_report.get("results") or {}
        if isinstance(results_dict, dict):
            results = list(results_dict.values())
    if not isinstance(results, list):
        return index
    for item in results:
        step = -1
        if isinstance(item, dict):
            step = int(item.get("step_index", -1))
        elif hasattr(item, "step_index"):
            step = int(item.step_index)  # type: ignore[union-attr]
        if step < 0:
            continue
        if isinstance(item, dict):
            index[step] = item
        elif hasattr(item, "to_dict"):
            index[step] = item.to_dict()  # type: ignore[union-attr]
    return index


def _state_items(sequence: Any) -> list[dict[str, Any]]:
    """Normalise state_sequence into a list of state dicts."""
    if sequence is None:
        return []
    if hasattr(sequence, "to_dict"):
        sequence = sequence.to_dict()
    if not isinstance(sequence, dict):
        return []
    return [item for item in sequence.get("states") or [] if isinstance(item, dict)]


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _step_range(state: dict[str, Any]) -> list[int]:
    rng = state.get("step_range")
    if isinstance(rng, list) and len(rng) >= 2:
        return [int(rng[0]), int(rng[1])]
    source = state.get("source_step_indices")
    if isinstance(source, list) and source:
        return [int(source[0]), int(source[-1])]
    return []


def _visual_change(state: dict[str, Any]) -> dict[str, Any]:
    """Extract visual change summary from state segment."""
    summary: Any = state.get("visual_change_summary") or {}
    if isinstance(summary, dict):
        return summary
    if hasattr(summary, "to_dict"):
        return summary.to_dict()  # type: ignore[no-any-return]
    return {}


def _ocr_changed(state: dict[str, Any]) -> bool:
    """Check whether OCR evidence indicates content change."""
    vis = _visual_change(state)
    ocr_sim = vis.get("ocr_text_similarity")
    rawpage = vis.get("rawpage_changed")
    if rawpage is True:
        return True
    if rawpage is False:
        return False
    if ocr_sim is not None and ocr_sim < 0.70:
        return True
    return False


def _is_minimal_visual_change(vis: dict[str, Any]) -> bool:
    """True when pixel-level change is negligible."""
    pixel_diff = vis.get("pixel_diff_ratio")
    ssim = vis.get("ssim")
    phash_dist = vis.get("phash_distance")
    score = 0
    if pixel_diff is not None and pixel_diff < 0.05:
        score += 1
    if ssim is not None and ssim > 0.94:
        score += 1
    if phash_dist is not None and phash_dist < 4:
        score += 1
    if score >= 2:
        return True
    return False


def _action_steps_in_range(
    payload: dict[str, Any],
    step_range: list[int],
    action_set: frozenset[str],
) -> list[int]:
    """Return step indices within range that match action_set types."""
    steps: list[int] = []
    if len(step_range) < 2:
        return steps
    lo, hi = step_range[0], step_range[1]
    seq = payload.get("seq_info") or []
    for pos, item in enumerate(seq):
        step_idx = int(item.get("index", pos)) if isinstance(item, dict) else pos
        if step_idx < lo or step_idx > hi:
            continue
        parsed = (item.get("planning_output") or {}).get("parsed_action") or {}
        at = str(parsed.get("action_type", "") or "").strip().lower()
        if at in action_set:
            steps.append(step_idx)
    return steps


def _has_unexpected_ab_for_steps(
    ab_index: dict[int, dict[str, Any]],
    step_indices: list[int],
) -> bool:
    """Check if any step in the range has an unexpected AB result."""
    for step in step_indices:
        ab = ab_index.get(step) or {}
        label = str(ab.get("label") or "").strip()
        if label in {"不符合预期", "unexpected"}:
            return True
    return False


def _build_tap_message(
    step_indices: list[int],
    state: dict[str, Any],
) -> str:
    steps_str = ",".join(str(s) for s in step_indices)
    desc = str(state.get("page_description") or state.get("label") or "").strip()
    return f"tap action at step {steps_str} produced no expected page change: {desc}" if desc else f"tap action at step {steps_str} produced no expected page change"


def _build_input_message(
    step_indices: list[int],
    state: dict[str, Any],
) -> str:
    steps_str = ",".join(str(s) for s in step_indices)
    purposes = _safe_list(state.get("action_purposes"))
    intent = purposes[0] if purposes else "input text"
    return f"input action at step {steps_str} ({intent}) did not change OCR content"


def _build_scroll_message(
    step_indices: list[int],
    state: dict[str, Any],
) -> str:
    steps_str = ",".join(str(s) for s in step_indices)
    desc = str(state.get("page_description") or state.get("label") or "").strip()
    return f"scroll/swipe at step {steps_str} produced minimal visual change: {desc}" if desc else f"scroll/swipe at step {steps_str} produced minimal visual change"
