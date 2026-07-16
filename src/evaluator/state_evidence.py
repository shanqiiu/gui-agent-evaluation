"""Lightweight state evidence aggregation for evaluator baselines."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from src.evaluator.visual_evidence import StepVisualEvidence, build_visual_evidence


@dataclass
class StateSegment:
    state_id: str
    label: str
    step_range: tuple[int, int]
    source_step_indices: list[int] = field(default_factory=list)
    page_description: str = ""
    action_types: list[str] = field(default_factory=list)
    evidence_quality: str = "missing"
    visual_change_summary: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "label": self.label,
            "step_range": list(self.step_range),
            "source_step_indices": self.source_step_indices,
            "page_description": self.page_description,
            "action_types": self.action_types,
            "evidence_quality": self.evidence_quality,
            "visual_change_summary": self.visual_change_summary,
            "evidence": self.evidence,
        }


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    trigger_step: int
    evidence: list[str] = field(default_factory=list)
    visual_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "trigger_step": self.trigger_step,
            "evidence": self.evidence,
            "visual_evidence": self.visual_evidence,
        }


@dataclass
class StateSequence:
    task_uuid: str = ""
    states: list[StateSegment] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    progress_steps: list[int] = field(default_factory=list)
    evidence_quality: str = "missing"
    visual_evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_uuid": self.task_uuid,
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions],
            "progress_steps": self.progress_steps,
            "evidence_quality": self.evidence_quality,
            "visual_evidence": self.visual_evidence,
        }


def build_state_sequence(
    payload: dict[str, Any],
    ab_report: Any = None,
    verification_report: Any = None,
    *,
    page_similarity_threshold: float = 0.82,
) -> StateSequence:
    """Build a lightweight actual-state sequence from payload and AB evidence."""
    visual_by_step = build_visual_evidence(payload)
    steps = _build_step_records(payload, ab_report, visual_by_step)
    if not steps:
        return StateSequence(task_uuid=payload.get("task_uuid", ""))

    checkpoint_progress = _checkpoint_progress_steps(verification_report)
    states: list[StateSegment] = []
    transitions: list[StateTransition] = []

    current_steps: list[dict[str, Any]] = []
    current_label = _initial_label(steps[0])
    current_start = steps[0]["source_step_index"]

    for step in steps:
        current_steps.append(step)
        boundary, evidence, next_label = _is_boundary(
            step,
            current_label,
            checkpoint_progress,
            page_similarity_threshold,
        )
        if not boundary:
            continue

        state = _make_state(
            len(states),
            current_label,
            current_start,
            step["source_step_index"],
            current_steps,
        )
        states.append(state)
        next_state_id = f"s_{len(states)}"
        transitions.append(StateTransition(
            from_state=state.state_id,
            to_state=next_state_id,
            trigger_step=step["source_step_index"],
            evidence=evidence,
            visual_evidence=_visual_to_dict(step.get("visual_evidence")),
        ))
        current_steps = []
        current_label = next_label or step.get("page_after") or current_label
        current_start = step["source_step_index"] + 1

    if current_steps:
        states.append(_make_state(
            len(states),
            current_label,
            current_start,
            current_steps[-1]["source_step_index"],
            current_steps,
        ))

    progress_steps = sorted(set(
        [t.trigger_step for t in transitions] + checkpoint_progress
    ))
    return StateSequence(
        task_uuid=payload.get("task_uuid", ""),
        states=states,
        transitions=transitions,
        progress_steps=progress_steps,
        evidence_quality=_sequence_quality(states),
        visual_evidence=[item.to_dict() for item in visual_by_step.values()],
    )


def _build_step_records(
    payload: dict[str, Any],
    ab_report: Any,
    visual_by_step: dict[int, StepVisualEvidence] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for pos, item in enumerate(payload.get("seq_info") or []):
        parsed = (item.get("planning_output") or {}).get("parsed_action") or {}
        action_type = str(parsed.get("action_type", "")).strip().lower()
        if not action_type or action_type in {"finished", "done"}:
            continue
        source_step_index = int(item.get("index", pos))
        ab = _ab_result(ab_report, source_step_index)
        visual = (visual_by_step or {}).get(source_step_index)
        records.append({
            "source_step_index": source_step_index,
            "action_type": action_type,
            "action_text": " ".join(
                str(parsed.get(k, "")).strip()
                for k in ("text", "content", "direction")
                if str(parsed.get(k, "")).strip()
            ),
            "page_before": str(ab.get("pagea_description") or "").strip(),
            "page_after": str(ab.get("pageb_description") or "").strip(),
            "ab_label": str(ab.get("label") or "").strip(),
            "visual_evidence": visual,
        })
    return records


def _is_boundary(
    step: dict[str, Any],
    current_label: str,
    checkpoint_progress: list[int],
    page_similarity_threshold: float,
) -> tuple[bool, list[str], str]:
    action_type = step["action_type"]
    page_after = step.get("page_after") or ""
    visual = step.get("visual_evidence")
    evidence: list[str] = []

    if step["source_step_index"] in checkpoint_progress:
        evidence.append("checkpoint achieved at this step")
        return True, evidence, page_after or current_label

    if _is_visual_boundary(visual):
        evidence.append(
            f"visual/rawPage boundary confidence={visual.boundary_confidence:.2f}"
        )
        evidence.extend(visual.evidence[:3])
        return True, evidence, page_after or current_label

    if action_type in {"open_app", "back"}:
        evidence.append(f"navigation action: {action_type}")
        return True, evidence, page_after or current_label

    if action_type in {"scroll", "swipe", "drag", "wait", "do-nothing", "do_nothing()"}:
        return False, [], current_label

    if page_after:
        sim = _similarity(current_label, page_after)
        if not current_label or sim < page_similarity_threshold:
            evidence.append(f"page description changed: similarity={sim:.2f}")
            return True, evidence, page_after

    action_text = step.get("action_text", "")
    if any(token in action_text for token in ("进入", "打开", "返回", "切换")):
        evidence.append("action text suggests state transition")
        return True, evidence, page_after or current_label

    return False, [], current_label


def _make_state(
    state_pos: int,
    label: str,
    start_step: int,
    end_step: int,
    steps: list[dict[str, Any]],
) -> StateSegment:
    page_descriptions = [
        s.get("page_after") or s.get("page_before") or ""
        for s in steps
        if s.get("page_after") or s.get("page_before")
    ]
    page_description = page_descriptions[-1] if page_descriptions else ""
    action_types = []
    visual_changes = []
    for step in steps:
        if step["action_type"] not in action_types:
            action_types.append(step["action_type"])
        visual = step.get("visual_evidence")
        if visual is not None:
            visual_changes.append(visual)
    visual_summary = _visual_summary(visual_changes)
    quality = _state_quality(page_description, visual_summary)
    return StateSegment(
        state_id=f"s_{state_pos}",
        label=label or page_description or "unknown",
        step_range=(start_step, end_step),
        source_step_indices=[s["source_step_index"] for s in steps],
        page_description=page_description,
        action_types=action_types,
        evidence_quality=quality,
        visual_change_summary=visual_summary,
        evidence=[f"aggregated {len(steps)} action steps"],
    )


def _initial_label(step: dict[str, Any]) -> str:
    return step.get("page_before") or step.get("page_after") or "unknown"


def _checkpoint_progress_steps(verification_report: Any) -> list[int]:
    progress_steps: list[int] = []
    if verification_report is None or not hasattr(verification_report, "results"):
        return progress_steps
    for result in verification_report.results:
        if getattr(result, "status", "") == "达成":
            step_index = getattr(result, "step_index", -1)
            if isinstance(step_index, int) and step_index >= 0:
                progress_steps.append(step_index)
    return progress_steps


def _ab_result(ab_report: Any, step_index: int) -> dict[str, Any]:
    if ab_report is None:
        return {}
    if isinstance(ab_report, dict):
        results = ab_report.get("results") or ab_report.get("ab_pages_result") or {}
        result = results.get(str(step_index)) or results.get(step_index) or {}
        return result if isinstance(result, dict) else {}
    if hasattr(ab_report, "get"):
        result = ab_report.get(step_index)
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return result if isinstance(result, dict) else {}
    return {}


def _sequence_quality(states: list[StateSegment]) -> str:
    if not states:
        return "missing"
    qualities = {s.evidence_quality for s in states}
    if "strong" in qualities:
        return "strong"
    if "visual" in qualities:
        return "visual"
    if "partial" in qualities:
        return "partial"
    return "missing"


def _is_visual_boundary(visual: StepVisualEvidence | None) -> bool:
    if visual is None:
        return False
    if visual.boundary_confidence >= 0.35:
        return True
    if visual.rawpage_changed is True and (
        visual.ocr_text_similarity is None or visual.ocr_text_similarity <= 0.75
    ):
        return True
    return False


def _visual_summary(visual_changes: list[StepVisualEvidence]) -> dict[str, Any]:
    usable = [v for v in visual_changes if v.evidence_quality != "missing"]
    if not usable:
        return {
            "count": len(visual_changes),
            "usable_count": 0,
            "max_boundary_confidence": 0.0,
            "max_pixel_diff_ratio": None,
            "min_ssim": None,
            "rawpage_change_count": 0,
            "changed_regions": [],
        }

    regions: list[str] = []
    for visual in usable:
        for region in visual.changed_regions:
            if region.region not in regions:
                regions.append(region.region)
    pixel_values = [
        v.pixel_diff_ratio for v in usable if v.pixel_diff_ratio is not None
    ]
    ssim_values = [v.ssim for v in usable if v.ssim is not None]
    return {
        "count": len(visual_changes),
        "usable_count": len(usable),
        "max_boundary_confidence": round(max(v.boundary_confidence for v in usable), 3),
        "max_pixel_diff_ratio": round(max(pixel_values), 4) if pixel_values else None,
        "min_ssim": round(min(ssim_values), 4) if ssim_values else None,
        "rawpage_change_count": sum(1 for v in usable if v.rawpage_changed is True),
        "changed_regions": regions,
    }


def _state_quality(page_description: str, visual_summary: dict[str, Any]) -> str:
    if visual_summary.get("usable_count", 0) > 0 and page_description:
        return "strong"
    if visual_summary.get("usable_count", 0) > 0:
        return "visual"
    if page_description:
        return "partial"
    return "missing"


def _visual_to_dict(visual: StepVisualEvidence | None) -> dict[str, Any]:
    return visual.to_dict() if visual is not None else {}


def _similarity(left: str, right: str) -> float:
    left = "".join(str(left).lower().split())
    right = "".join(str(right).lower().split())
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()
