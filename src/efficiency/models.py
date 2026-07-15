"""Models for UI Agent trajectory efficiency analysis.

Four sub-metrics:
    ineffective_rate — 无效操作比例 (AB nok or no state change)
    exploratory_overhead — 探索性开销 (extra steps beyond plan minimum)
    navigation_redundancy — 导航冗余 (unnecessary back-and-forth)
    scroll_efficiency — 滑动效率 (scrolls needed vs found target)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IneffectiveAction:
    """A single action that did not produce expected state change."""
    step_index: int
    action_type: str
    reason: str          # "ab_nok" | "no_state_change" | "same_page_loop"
    target: str = ""


@dataclass
class ExplorationCluster:
    """A cluster of consecutive exploratory actions (scrolls, redundant clicks)."""
    start_step: int
    end_step: int
    action_type: str     # "scroll" | "click" | "mixed"
    step_count: int
    found_target: bool   # did exploration end with a successful action?
    overhead: int        # steps beyond expected


@dataclass
class NavigationLoop:
    """A back-to-page navigation loop: A→B→A or A→B→C→A pattern."""
    start_step: int
    end_step: int
    pages: list[str]     # pages visited
    loop_count: int      # how many times


@dataclass
class EfficiencyReport:
    """Complete efficiency analysis for a single task trajectory."""

    task_uuid: str
    instruction: str

    # ── Sub-metrics ──
    ineffective_rate: float = 0.0          # 0.0–1.0
    exploratory_overhead: float = 0.0      # extra steps / total steps
    navigation_redundancy: float = 0.0     # loop steps / total steps
    scroll_efficiency: float = 1.0         # targets found / scroll attempts

    # ── Composite ──
    overall_efficiency: float = 1.0        # weighted composite 0.0–1.0
    efficiency_label: str = "efficient"    # "efficient" | "moderate" | "inefficient"

    # ── Details ──
    ineffective_actions: list[IneffectiveAction] = field(default_factory=list)
    exploration_clusters: list[ExplorationCluster] = field(default_factory=list)
    navigation_loops: list[NavigationLoop] = field(default_factory=list)

    # ── Counts ──
    total_steps: int = 0
    effective_steps: int = 0
    ineffective_steps: int = 0
    plan_steps: int = 0
    scroll_steps: int = 0
    back_steps: int = 0

    # ── Evidence ──
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_uuid": self.task_uuid,
            "instruction": self.instruction,
            "ineffective_rate": round(self.ineffective_rate, 3),
            "exploratory_overhead": round(self.exploratory_overhead, 3),
            "navigation_redundancy": round(self.navigation_redundancy, 3),
            "scroll_efficiency": round(self.scroll_efficiency, 3),
            "overall_efficiency": round(self.overall_efficiency, 3),
            "efficiency_label": self.efficiency_label,
            "ineffective_actions": [
                {"step": ia.step_index, "action_type": ia.action_type,
                 "reason": ia.reason, "target": ia.target}
                for ia in self.ineffective_actions
            ],
            "exploration_clusters": [
                {"start": ec.start_step, "end": ec.end_step,
                 "action_type": ec.action_type, "step_count": ec.step_count,
                 "found_target": ec.found_target, "overhead": ec.overhead}
                for ec in self.exploration_clusters
            ],
            "navigation_loops": [
                {"start": nl.start_step, "end": nl.end_step,
                 "pages": nl.pages, "loop_count": nl.loop_count}
                for nl in self.navigation_loops
            ],
            "total_steps": self.total_steps,
            "effective_steps": self.effective_steps,
            "ineffective_steps": self.ineffective_steps,
            "plan_steps": self.plan_steps,
            "scroll_steps": self.scroll_steps,
            "back_steps": self.back_steps,
            "evidence": self.evidence,
        }


@dataclass
class EfficiencyConfig:
    """Configuration for the efficiency analyzer."""

    # Thresholds
    consecutive_scroll_threshold: int = 4      # > this → exploration cluster
    consecutive_back_threshold: int = 2        # > this → navigation issue
    exploratory_overhead_threshold: float = 0.3  # above → moderate
    inefficient_threshold: float = 0.5         # above → inefficient
    scroll_target_window: int = 2              # look within N steps for target found after scrolls
    loop_page_window: int = 8                  # window for detecting page-level loops

    # Weights for composite score
    weight_ineffective: float = 0.35
    weight_overhead: float = 0.25
    weight_redundancy: float = 0.25
    weight_scroll: float = 0.15
