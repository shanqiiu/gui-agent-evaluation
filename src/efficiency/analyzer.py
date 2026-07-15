"""UI Agent Trajectory Efficiency Analyzer.

Four sub-metrics:
    1. ineffective_rate    — AB判定异常或未改变状态的操作比例
    2. exploratory_overhead — 超出Plan最少步骤的探索性开销
    3. navigation_redundancy — 不必要的页面往返
    4. scroll_efficiency    — 滑动操作的命中效率

Rule-based, no external model calls required.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import (
    EfficiencyConfig,
    EfficiencyReport,
    ExplorationCluster,
    IneffectiveAction,
    NavigationLoop,
)


def analyze_efficiency(
    payload: dict[str, Any],
    darwin_result: dict[str, Any] | None = None,
    repeated_action_result: dict[str, Any] | None = None,
    config: EfficiencyConfig | None = None,
) -> EfficiencyReport:
    """Entry point: analyze trajectory efficiency."""
    analyzer = EfficiencyAnalyzer(config or EfficiencyConfig())
    return analyzer.analyze(payload, darwin_result or {}, repeated_action_result or {})


class EfficiencyAnalyzer:
    def __init__(self, config: EfficiencyConfig):
        self.config = config

    # ── Public API ─────────────────────────────────────────────

    def analyze(
        self,
        payload: dict,
        darwin_result: dict,
        repeated_action_result: dict,
    ) -> EfficiencyReport:
        task_uuid = payload.get("task_uuid", "")
        instruction = payload.get("instruction", "")
        seq_info = payload.get("seq_info", [])

        # Parse steps
        steps = self._parse_steps(seq_info, darwin_result)

        # Count plan steps
        step_plan = payload.get("step_level_instruction", "")
        plan_steps = len([s for s in step_plan.split("->") if s.strip()]) if step_plan else 0

        if not steps:
            return EfficiencyReport(
                task_uuid=task_uuid, instruction=instruction,
                evidence=["动作序列为空"],
            )

        # ── 1. Ineffective actions ──
        ineffective = self._detect_ineffective(steps, repeated_action_result)
        ineffective_count = len(ineffective)
        ineffective_rate = ineffective_count / len(steps) if steps else 0

        # ── 2. Exploration clusters ──
        clusters = self._detect_exploration_clusters(steps)
        overhead = self._compute_overhead(clusters, steps, plan_steps)

        # ── 3. Navigation redundancy ──
        loops = self._detect_navigation_loops(steps)
        redundancy = self._compute_redundancy(loops, steps)

        # ── 4. Scroll efficiency ──
        scroll_eff = self._compute_scroll_efficiency(steps)

        # ── Composite score ──
        w = self.config
        overall = 1.0 - (
            w.weight_ineffective * ineffective_rate +
            w.weight_overhead * overhead +
            w.weight_redundancy * redundancy +
            w.weight_scroll * (1.0 - scroll_eff)
        )
        overall = max(0.0, min(1.0, overall))

        if overall >= 0.85:
            label = "efficient"
        elif overall >= 0.60:
            label = "moderate"
        else:
            label = "inefficient"

        # ── Evidence ──
        evidence = self._build_evidence(
            ineffective_rate, overhead, redundancy, scroll_eff,
            clusters, loops, ineffective,
        )

        return EfficiencyReport(
            task_uuid=task_uuid,
            instruction=instruction,
            ineffective_rate=ineffective_rate,
            exploratory_overhead=overhead,
            navigation_redundancy=redundancy,
            scroll_efficiency=scroll_eff,
            overall_efficiency=overall,
            efficiency_label=label,
            ineffective_actions=ineffective,
            exploration_clusters=clusters,
            navigation_loops=loops,
            total_steps=len(steps),
            effective_steps=len(steps) - ineffective_count,
            ineffective_steps=ineffective_count,
            plan_steps=plan_steps,
            scroll_steps=sum(1 for s in steps if s["action_type"] in ("scroll", "swipe", "drag")),
            back_steps=sum(1 for s in steps if s["action_type"] == "back"),
            evidence=evidence,
        )

    # ── Step parsing ───────────────────────────────────────────

    def _parse_steps(
        self, seq_info: list, darwin_result: dict
    ) -> list[dict[str, Any]]:
        ab_results = darwin_result.get("ab_pages_result", {})
        steps = []
        for item in seq_info:
            idx = item.get("index", 0)
            pa = (item.get("planning_output") or {}).get("parsed_action") or {}
            action_type = pa.get("action_type", "")
            if not action_type or action_type in ("finished", "done", "do-nothing"):
                continue
            ab = ab_results.get(str(idx), {}) if isinstance(ab_results, dict) else {}
            steps.append({
                "step": idx,
                "action_type": action_type,
                "start_box": pa.get("start_box", []),
                "end_box": pa.get("end_box", []),
                "text": pa.get("text", ""),
                "direction": pa.get("direction", ""),
                "ab_label": ab.get("label", ""),
                "page_before": ab.get("pagea_description", ""),
                "page_after": ab.get("pageb_description", ""),
            })
        return steps

    # ── 1. Ineffective actions ─────────────────────────────────

    def _detect_ineffective(
        self, steps: list[dict], repeated_action_result: dict
    ) -> list[IneffectiveAction]:
        result = []
        repeated_steps: set[int] = set()
        for rng in repeated_action_result.get("ranges", []):
            for s in range(rng.get("start_step", 0), rng.get("end_step", -1) + 1):
                repeated_steps.add(s)

        for s in steps:
            step = s["step"]
            reasons = []
            if step in repeated_steps:
                reasons.append("repeat")
            if s.get("ab_label", "").lower() in ("nok", "bad", "abnormal"):
                reasons.append("ab_nok")
            if reasons:
                result.append(IneffectiveAction(
                    step_index=step,
                    action_type=s["action_type"],
                    reason="+".join(reasons),
                    target=s.get("text", ""),
                ))
        return result

    # ── 2. Exploration clusters ────────────────────────────────

    def _detect_exploration_clusters(
        self, steps: list[dict]
    ) -> list[ExplorationCluster]:
        """Detect clusters of consecutive scroll/swipe actions."""
        clusters = []
        i = 0
        while i < len(steps):
            s = steps[i]
            if s["action_type"] not in ("scroll", "swipe", "drag"):
                i += 1
                continue
            # Found a scroll → extend cluster
            start = i
            while i < len(steps) and steps[i]["action_type"] in ("scroll", "swipe", "drag"):
                i += 1
            count = i - start
            if count >= self.config.consecutive_scroll_threshold:
                # Check if target was found within window after cluster
                found = self._target_found_after(steps, i, self.config.scroll_target_window)
                overhead = count - 1 if found else count  # at least 1 scroll needed
                clusters.append(ExplorationCluster(
                    start_step=steps[start]["step"],
                    end_step=steps[i - 1]["step"],
                    action_type="scroll",
                    step_count=count,
                    found_target=found,
                    overhead=overhead,
                ))
            else:
                i += 1
        return clusters

    def _target_found_after(
        self, steps: list[dict], cluster_end: int, window: int
    ) -> bool:
        """Check if a successful action follows within window steps after cluster."""
        for j in range(cluster_end, min(cluster_end + window, len(steps))):
            s = steps[j]
            if s["action_type"] == "click" and s.get("ab_label", "").lower() in ("ok", ""):
                return True
        return False

    def _compute_overhead(
        self, clusters: list[ExplorationCluster],
        steps: list[dict], plan_steps: int,
    ) -> float:
        """Compute exploratory overhead as ratio of extra steps."""
        extra = sum(c.overhead for c in clusters)
        if len(steps) == 0:
            return 0.0
        return extra / len(steps)

    # ── 3. Navigation redundancy ───────────────────────────────

    def _detect_navigation_loops(
        self, steps: list[dict]
    ) -> list[NavigationLoop]:
        """Detect back-to-page navigation loops."""
        loops = []
        back_pages: list[tuple[int, str]] = []
        for s in steps:
            if s["action_type"] == "back":
                page = s.get("page_before", "") or s.get("page_after", "")
                back_pages.append((s["step"], page))

        for i in range(len(back_pages) - 1):
            step_a, page_a = back_pages[i]
            for j in range(i + 1, len(back_pages)):
                step_b, page_b = back_pages[j]
                if page_a and page_b and self._pages_similar(page_a, page_b):
                    loops.append(NavigationLoop(
                        start_step=step_a,
                        end_step=step_b,
                        pages=[page_a, page_b],
                        loop_count=1,
                    ))
        return loops

    def _pages_similar(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        a_lower = a.lower().strip()
        b_lower = b.lower().strip()
        if a_lower == b_lower:
            return True
        # Check for shared keywords
        a_words = set(a_lower.split())
        b_words = set(b_lower.split())
        if not a_words or not b_words:
            return False
        overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
        return overlap > 0.7

    def _compute_redundancy(
        self, loops: list[NavigationLoop], steps: list[dict]
    ) -> float:
        if not steps:
            return 0.0
        loop_steps = sum(
            (nl.end_step - nl.start_step + 1) * nl.loop_count for nl in loops
        )
        return min(loop_steps / len(steps), 1.0)

    # ── 4. Scroll efficiency ───────────────────────────────────

    def _compute_scroll_efficiency(self, steps: list[dict]) -> float:
        """Compute how efficiently scrolls find targets."""
        scrolls = [s for s in steps if s["action_type"] in ("scroll", "swipe", "drag")]
        if not scrolls:
            return 1.0
        # Count scrolls followed by successful click within window
        productive = 0
        for s in scrolls:
            idx = steps.index(s)
            for j in range(idx + 1, min(idx + 1 + self.config.scroll_target_window, len(steps))):
                if steps[j]["action_type"] == "click" and steps[j].get("ab_label", "").lower() not in ("nok",):
                    productive += 1
                    break
        return productive / len(scrolls) if scrolls else 1.0

    # ── Evidence ────────────────────────────────────────────────

    def _build_evidence(
        self,
        ineffective_rate: float,
        overhead: float,
        redundancy: float,
        scroll_eff: float,
        clusters: list[ExplorationCluster],
        loops: list[NavigationLoop],
        ineffective: list[IneffectiveAction],
    ) -> list[str]:
        evidence = []
        if ineffective_rate > 0.2:
            evidence.append(
                f"无效操作率 {ineffective_rate:.0%}，{len(ineffective)} 个无效步骤"
            )
        if clusters:
            for c in clusters[:3]:
                evidence.append(
                    f"步骤 {c.start_step}-{c.end_step}: {c.step_count}次连续滑动"
                    f"{'（找到目标）' if c.found_target else '（未找到目标）'}"
                )
        if loops:
            evidence.append(f"检测到 {len(loops)} 个页面导航循环")
        if scroll_eff < 0.5:
            evidence.append(f"滑动效率偏低 ({scroll_eff:.0%})")
        if overhead > self.config.exploratory_overhead_threshold:
            evidence.append(f"探索性开销 {overhead:.0%}，高于阈值")
        if not evidence:
            evidence.append("执行效率正常")
        return evidence
