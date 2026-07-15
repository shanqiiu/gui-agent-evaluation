"""Models for trajectory differential deviation analysis.

The three-class framework:
    无影响偏差 (No-impact):   Different path, same result — no penalty.
    补救性偏差 (Remedial):     Early suboptimal but self-corrected — reduced score.
    级联偏差  (Cascading):     Small error amplified into failure — mark FES.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviationPoint:
    """A single deviation from the expected trajectory."""

    step_index: int                          # where the deviation occurred
    deviation_type: str                      # "action_mismatch" | "plan_skip" | "repeat" | "backtrack" | "ineffective"
    description: str                         # human-readable explanation
    recovered: bool = False                  # was the agent able to self-correct?
    recovery_step: int | None = None         # if recovered, at which step?
    impact_steps: list[int] = field(default_factory=list)  # subsequent steps affected
    severity: str = "low"                    # "low" | "medium" | "high"


@dataclass
class TrajectoryDeviation:
    """Complete deviation analysis for a single task trajectory."""

    task_uuid: str
    instruction: str

    # ── Classification ──
    deviation_class: str                     # "no_impact" | "remedial" | "cascading"
    confidence: float                        # 0.0 – 1.0

    # ── Evidence ──
    deviations: list[DeviationPoint] = field(default_factory=list)
    first_error_step: int | None = None      # earliest step where things went wrong
    recovery_count: int = 0                  # number of self-corrections
    cascaded: bool = False                   # did early errors propagate?
    final_outcome_ok: bool = True            # was the overall task successful?

    # ── Metrics ──
    plan_coverage: float = 0.0               # covered / total plan steps
    redundant_steps: int = 0                 # steps not contributing to plan progress
    efficiency_score: float = 0.0            # action efficiency (0-1)
    total_steps: int = 0
    deviation_count: int = 0

    # ── Supporting data ──
    repeated_ranges: list[dict] = field(default_factory=list)
    planning_failures: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        deviations_json = [
            {
                "step_index": d.step_index,
                "deviation_type": d.deviation_type,
                "description": d.description,
                "recovered": d.recovered,
                "recovery_step": d.recovery_step,
                "impact_steps": d.impact_steps,
                "severity": d.severity,
            }
            for d in self.deviations
        ]
        return {
            "task_uuid": self.task_uuid,
            "instruction": self.instruction,
            "deviation_class": self.deviation_class,
            "confidence": round(self.confidence, 3),
            "first_error_step": self.first_error_step,
            "recovery_count": self.recovery_count,
            "cascaded": self.cascaded,
            "final_outcome_ok": self.final_outcome_ok,
            "plan_coverage": round(self.plan_coverage, 3),
            "redundant_steps": self.redundant_steps,
            "efficiency_score": round(self.efficiency_score, 3),
            "total_steps": self.total_steps,
            "deviation_count": self.deviation_count,
            "deviations": deviations_json,
            "evidence": self.evidence,
        }


@dataclass
class DifferentialJudgerConfig:
    """Configuration for the trajectory differential judger."""

    # Deviation sensitivity
    plan_coverage_threshold: float = 0.8     # below this, consider cascading
    backtrack_penalty: float = 0.15          # per backtrack, reduce efficiency
    repeat_penalty: float = 0.1              # per repeated range, reduce efficiency
    min_deviation_gap: int = 2               # steps between deviations to consider separate

    # Self-correction detection
    self_correction_patterns: list[str] = field(default_factory=lambda: ["back", "返回", "return"])

    # Cascading detection
    cascading_threshold: float = 0.5         # plan coverage below this → cascading
    max_recovery_for_no_impact: int = 0      # > 0 recoveries → not pure no_impact
