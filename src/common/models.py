"""Shared data models for the common detection pipeline.

These models bridge Module A (decomposer), Module B (verifier), payload.json,
and the two rule-based detectors (repeated_action, planning_failure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── AB Page Validation ────────────────────────────────────────────

@dataclass
class StepABResult:
    """AB page validation result for a single action step.

    Replicates Darwin's ab_pages_result structure for a single step,
    so the detectors can consume it without Darwin dependency.
    """

    step_index: int
    label: str = ""                      # "符合预期" | "不符合预期" | "无法判定"
    action_des: str = ""                 # VLM-generated action description
    pagea_description: str = ""          # page content before action
    pageb_description: str = ""          # page content after action
    thought: str = ""                    # VLM reasoning
    confidence: float = 0.0              # 0.0 – 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "action_des": self.action_des,
            "pagea_description": self.pagea_description,
            "pageb_description": self.pageb_description,
            "thought": self.thought,
        }

    @classmethod
    def empty(cls, step_index: int = -1) -> StepABResult:
        return cls(step_index=step_index)


@dataclass
class ABValidationReport:
    """Aggregated AB validation results for all steps in a trajectory."""

    task_uuid: str = ""
    results: list[StepABResult] = field(default_factory=list)
    model_used: str = ""
    total_vlm_calls: int = 0
    fallback_count: int = 0

    def get(self, step_index: int) -> StepABResult:
        """Get AB result for a specific step, or empty result if not found."""
        for r in self.results:
            if r.step_index == step_index:
                return r
        return StepABResult.empty(step_index)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_uuid": self.task_uuid,
            "results": {str(r.step_index): r.to_dict() for r in self.results},
            "model_used": self.model_used,
            "total_vlm_calls": self.total_vlm_calls,
            "fallback_count": self.fallback_count,
        }


# ── Detector Input / Output ───────────────────────────────────────

@dataclass
class RepeatedActionRange:
    """A detected repeated action range."""

    start_step: int
    end_step: int
    action_type: str
    target: str = ""
    repeat_type: str = ""                # "repeated_action" | "repeated_wait" | "repeated_swipe" | "state_action_loop"
    severity: str = "low"                # "low" | "medium" | "high"
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_step": self.start_step,
            "end_step": self.end_step,
            "action_type": self.action_type,
            "target": self.target,
            "repeat_type": self.repeat_type,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
        }


@dataclass
class RepeatedActionResult:
    """Complete repeated action detection result."""

    label: str = "normal"                # "normal" | "abnormal"
    severity: str = "none"               # "none" | "low" | "medium" | "high"
    confidence: float = 0.0
    ranges: list[RepeatedActionRange] = field(default_factory=list)
    summary: str = ""
    action_count: int = 0
    repeated_range_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "type": "repeated_action",
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "ranges": [r.to_dict() for r in self.ranges],
            "summary": self.summary,
            "metrics": {
                "action_count": self.action_count,
                "repeated_range_count": self.repeated_range_count,
            },
        }


@dataclass
class PlanningFailureEvent:
    """A single planning failure event."""

    subtype: str                         # "missing_required_step" | "premature_termination" | "fail_to_terminate" | "objective_or_plan_mismatch"
    confidence: float = 0.0
    first_error_step: int = -1
    related_anomalies: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtype": self.subtype,
            "confidence": round(self.confidence, 3),
            "first_error_step": self.first_error_step,
            "related_anomalies": self.related_anomalies,
            "evidence": self.evidence,
        }


@dataclass
class MissingCheckpoint:
    """A checkpoint that was not achieved."""

    name: str
    required: bool = True
    status: str = "not_started"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "status": self.status,
        }


@dataclass
class PlanningFailureResult:
    """Complete planning failure detection result."""

    label: str = "normal"                # "normal" | "abnormal"
    subtype: str = "none"
    severity: str = "none"
    confidence: float = 0.0
    first_error_step: int = -1
    completion_score: float = 0.0
    total_plan: int = 0
    covered_plan: int = 0
    missing_checkpoints: list[MissingCheckpoint] = field(default_factory=list)
    bug_steps: list[str] = field(default_factory=list)
    related_anomalies: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    events: list[PlanningFailureEvent] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "type": "planning_failure",
            "subtype": self.subtype,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "first_error_step": self.first_error_step,
            "completion_score": round(self.completion_score, 3),
            "total_plan": self.total_plan,
            "covered_plan": self.covered_plan,
            "missing_checkpoints": [c.to_dict() for c in self.missing_checkpoints],
            "bug_steps": self.bug_steps,
            "related_anomalies": self.related_anomalies,
            "evidence": self.evidence,
            "events": [e.to_dict() for e in self.events],
            "summary": self.summary,
        }
