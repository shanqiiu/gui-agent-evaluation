"""Trajectory Differential Judger — three-class deviation analysis.

Classifies Agent trajectories:
    no_impact  — Different path, same result.
    remedial   — Early suboptimal, self-corrected.
    cascading  — Small error amplified into failure.

Consumes: payload + Darwin E2E结果 + 重复动作结果 + 规划失效结果
Produces: TrajectoryDeviation with classification, FES, evidence chain.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .models import (
    DeviationPoint,
    DifferentialJudgerConfig,
    TrajectoryDeviation,
)


def judge_trajectory(
    payload: dict[str, Any],
    darwin_result: dict[str, Any] | None = None,
    repeated_action_result: dict[str, Any] | None = None,
    planning_failure_result: dict[str, Any] | None = None,
    config: DifferentialJudgerConfig | None = None,
) -> TrajectoryDeviation:
    """Entry point: analyze trajectory and classify deviation type."""
    judger = DifferentialJudger(config or DifferentialJudgerConfig())
    return judger.judge(
        payload,
        darwin_result or {},
        repeated_action_result or {},
        planning_failure_result or {},
    )


class DifferentialJudger:
    def __init__(self, config: DifferentialJudgerConfig):
        self.config = config

    # ── Public API ─────────────────────────────────────────────

    def judge(
        self,
        payload: dict,
        darwin_result: dict,
        repeated_action_result: dict,
        planning_failure_result: dict,
    ) -> TrajectoryDeviation:
        task_uuid = payload.get("task_uuid", "")
        instruction = payload.get("instruction", "")
        seq_info = payload.get("seq_info", [])

        # 1. Build step timeline
        steps = self._parse_steps(seq_info, darwin_result)

        # 2. Detect deviations
        deviations = self._detect_deviations(steps, darwin_result, repeated_action_result)

        # 3. Analyze self-correction and cascading
        recovery_count = sum(1 for d in deviations if d.recovered)
        cascaded = self._detect_cascading(deviations, darwin_result)

        # 4. Determine final outcome
        intention_ok = self._intention_ok(darwin_result)

        # 5. Compute metrics
        plan_coverage = self._compute_plan_coverage(darwin_result)
        efficiency = self._compute_efficiency(steps, deviations, repeated_action_result)

        # 6. Classify
        dev_class, confidence, evidence = self._classify(
            deviations, recovery_count, cascaded, intention_ok,
            plan_coverage, planning_failure_result, repeated_action_result,
        )

        first_error = self._find_first_error(deviations, darwin_result)

        return TrajectoryDeviation(
            task_uuid=task_uuid,
            instruction=instruction,
            deviation_class=dev_class,
            confidence=confidence,
            deviations=deviations,
            first_error_step=first_error,
            recovery_count=recovery_count,
            cascaded=cascaded,
            final_outcome_ok=intention_ok,
            plan_coverage=plan_coverage,
            redundant_steps=self._count_redundant(steps, darwin_result),
            efficiency_score=efficiency,
            total_steps=len(steps),
            deviation_count=len(deviations),
            repeated_ranges=repeated_action_result.get("ranges", []),
            planning_failures=planning_failure_result.get("events", []),
            evidence=evidence,
        )

    # ── Step parsing ───────────────────────────────────────────

    def _parse_steps(
        self, seq_info: list, darwin_result: dict
    ) -> list[dict[str, Any]]:
        """Parse seq_info into enriched step list."""
        ab_results = darwin_result.get("ab_pages_result", {})
        steps = []
        for item in seq_info:
            idx = item.get("index", 0)
            pa = (item.get("planning_output") or {}).get("parsed_action") or {}
            action_type = pa.get("action_type", "")
            if not action_type or action_type in ("finished", "done"):
                continue

            ab = ab_results.get(str(idx), {}) if isinstance(ab_results, dict) else {}
            steps.append({
                "step": idx,
                "action_type": action_type,
                "start_box": pa.get("start_box", []),
                "text": pa.get("text", ""),
                "target": pa.get("text", ""),
                "ab_label": ab.get("label", ""),
                "ab_thought": ab.get("thought", ""),
                "page_before": ab.get("pagea_description", ""),
                "page_after": ab.get("pageb_description", ""),
            })
        return steps

    # ── Deviation detection ───────────────────────────────────

    def _detect_deviations(
        self,
        steps: list[dict],
        darwin_result: dict,
        repeated_action_result: dict,
    ) -> list[DeviationPoint]:
        deviations: list[DeviationPoint] = []

        # 1. AB label mismatches (action didn't achieve expected outcome)
        deviations.extend(self._detect_ab_mismatches(steps))

        # 2. Repeated actions (from detector output)
        deviations.extend(self._detect_repeated_ranges(steps, repeated_action_result))

        # 3. Backtracking / self-correction patterns
        deviations.extend(self._detect_backtracks(steps))

        # 4. Plan skip gaps
        deviations.extend(self._detect_plan_gaps(steps, darwin_result))

        # Merge overlapping and sort
        deviations = self._merge_deviations(deviations)

        # Link backtrack recoveries to preceding mismatches
        self._link_recoveries(deviations)

        return deviations

    def _detect_ab_mismatches(self, steps: list[dict]) -> list[DeviationPoint]:
        result = []
        for s in steps:
            label = s.get("ab_label", "")
            if label and label.lower() in ("nok", "bad", "abnormal"):
                result.append(DeviationPoint(
                    step_index=s["step"],
                    deviation_type="action_mismatch",
                    description=f"步骤 {s['step']}: AB判定异常 ({s.get('ab_thought', '')[:60]})",
                    severity="medium",
                ))
        return result

    def _detect_repeated_ranges(
        self, steps: list[dict], repeated_action_result: dict
    ) -> list[DeviationPoint]:
        result = []
        for rng in repeated_action_result.get("ranges", []):
            start = rng.get("start_step", 0)
            end = rng.get("end_step", start)
            at = rng.get("action_type", "unknown")
            target = rng.get("target", "")
            result.append(DeviationPoint(
                step_index=start,
                deviation_type="repeat",
                description=f"步骤 {start}-{end}: 重复{at}操作 ({target})",
                impact_steps=list(range(start, end + 1)),
                severity="medium",
            ))
        return result

    def _detect_backtracks(self, steps: list[dict]) -> list[DeviationPoint]:
        """Detect back/return actions as potential self-corrections."""
        result = []
        back_step_indices = [
            i for i, s in enumerate(steps)
            if s["action_type"] in ("back",) or any(
                p in (s.get("text", "") or "").lower()
                for p in self.config.self_correction_patterns
            )
        ]
        for idx in back_step_indices:
            s = steps[idx]
            # Check if any preceding step had AB label "nok" (not yet recovered)
            recovered = any(
                steps[pi].get("ab_label", "").lower() in ("nok", "bad", "abnormal")
                for pi in range(idx)
            )
            result.append(DeviationPoint(
                step_index=s["step"],
                deviation_type="backtrack",
                description=f"步骤 {s['step']}: 返回/回退操作{'（修正了前序偏差）' if recovered else ''}",
                recovered=recovered,
                severity="low",
            ))
        return result

    def _detect_plan_gaps(
        self, steps: list[dict], darwin_result: dict
    ) -> list[DeviationPoint]:
        """Detect steps where no plan progress was made."""
        progress = self._build_progress_map(darwin_result)
        result = []
        no_progress_steps = []
        for i in range(len(steps)):
            step_num = steps[i]["step"]
            if progress.get(step_num, 0) == progress.get(step_num - 1, 0):
                no_progress_steps.append(step_num)
            else:
                if len(no_progress_steps) >= self.config.min_deviation_gap:
                    result.append(DeviationPoint(
                        step_index=no_progress_steps[0],
                        deviation_type="plan_skip",
                        description=f"步骤 {no_progress_steps[0]}-{no_progress_steps[-1]}: 未推进Plan进展",
                        impact_steps=list(no_progress_steps),
                        severity="low",
                    ))
                no_progress_steps = []
        return result

    def _build_progress_map(self, darwin_result: dict) -> dict[int, int]:
        """Build step→progress mapping from intention step results."""
        progress: dict[int, int] = {}
        cover_key = "llm_intention_step"
        step_results = darwin_result.get(cover_key) or darwin_result.get("vlm_intention_step") or {}
        if isinstance(step_results, dict):
            for k, v in step_results.items():
                try:
                    step = int(k)
                    progress[step] = int(v) if v else 0
                except (ValueError, TypeError):
                    continue
        return progress

    # ── Analysis ─────────────────────────────────────────────

    def _detect_cascading(
        self, deviations: list[DeviationPoint], darwin_result: dict
    ) -> bool:
        """Detect if early errors propagated downstream."""
        if not deviations:
            return False
        # Sort by step index
        sorted_devs = sorted(deviations, key=lambda d: d.step_index)
        first = sorted_devs[0]
        # If earliest deviation was not recovered and later steps were affected
        if not first.recovered:
            affected_later = any(
                d.step_index > first.step_index
                for d in sorted_devs
            )
            if affected_later:
                return True
        return False

    def _intention_ok(self, darwin_result: dict) -> bool:
        intent = darwin_result.get("intention", {})
        label = (intent.get("label") or "").lower()
        return label in ("ok", "normal")

    def _compute_plan_coverage(self, darwin_result: dict) -> float:
        """Compute covered / total plan steps."""
        step_statuses = darwin_result.get("step_statuses", {})
        if not step_statuses:
            step_statuses = {}
            cover_key = "llm_intention_step"
            raw = darwin_result.get(cover_key) or darwin_result.get("vlm_intention_step") or {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    step_statuses[str(k)] = int(v) if v else 0
        total = len(step_statuses)
        if total == 0:
            return 1.0
        covered = sum(1 for v in step_statuses.values() if v)
        return covered / max(total, 1)

    def _compute_efficiency(
        self,
        steps: list[dict],
        deviations: list[DeviationPoint],
        repeated_action_result: dict,
    ) -> float:
        """Compute action efficiency score (0-1)."""
        base = 1.0
        # Penalize repeated ranges
        ranges = repeated_action_result.get("ranges", [])
        repeat_steps = sum(r.get("end_step", r.get("start_step", 0)) - r.get("start_step", 0) + 1
                           for r in ranges)
        if len(steps) > 0:
            base -= min(self.config.repeat_penalty * repeat_steps, 0.3)

        # Penalize backtracks
        backtracks = sum(1 for d in deviations if d.deviation_type == "backtrack")
        base -= min(self.config.backtrack_penalty * backtracks, 0.3)

        return max(base, 0.0)

    def _count_redundant(self, steps: list[dict], darwin_result: dict) -> int:
        """Count steps that didn't contribute to plan progress."""
        progress = self._build_progress_map(darwin_result)
        redundant = 0
        last_progress = -1
        for s in steps:
            current = progress.get(s["step"], last_progress)
            if current == last_progress:
                redundant += 1
            else:
                last_progress = current
        return redundant

    def _find_first_error(
        self, deviations: list[DeviationPoint], darwin_result: dict
    ) -> int | None:
        """Find earliest step where things went wrong."""
        if not deviations:
            return None
        # Prefer unrecovered high/medium severity deviation
        sorted_devs = sorted(deviations, key=lambda d: d.step_index)
        for d in sorted_devs:
            if not d.recovered and d.severity in ("high", "medium"):
                return d.step_index
        return sorted_devs[0].step_index

    # ── Classification ────────────────────────────────────────

    def _classify(
        self,
        deviations: list[DeviationPoint],
        recovery_count: int,
        cascaded: bool,
        intention_ok: bool,
        plan_coverage: float,
        planning_failure_result: dict,
        repeated_action_result: dict,
    ) -> tuple[str, float, list[str]]:
        """Classify trajectory into one of three types."""

        has_repeats = bool(repeated_action_result.get("ranges"))
        has_planning_failure = planning_failure_result.get("label") == "abnormal"

        # ── Cascading ──
        if cascaded and not intention_ok:
            evidence = [
                f"轨迹中存在未恢复的初始偏差，并级联影响后续步骤",
                f"整体意图判定: {'通过' if intention_ok else '未通过'}",
                f"Plan 覆盖率: {plan_coverage:.0%}",
                f"偏差数: {len(deviations)}, 恢复数: {recovery_count}",
            ]
            if has_planning_failure:
                pf_subtype = planning_failure_result.get("subtype", "")
                evidence.append(f"规划失效: {pf_subtype}")
            if deviations:
                first = sorted(deviations, key=lambda d: d.step_index)[0]
                evidence.append(f"首错步骤: {first.step_index} ({first.deviation_type})")
            return "cascading", 0.85, evidence

        if plan_coverage < self.config.cascading_threshold:
            evidence = [
                f"Plan 覆盖率过低 ({plan_coverage:.0%}), 低于阈值 {self.config.cascading_threshold}",
                f"偏差数: {len(deviations)}",
            ]
            return "cascading", 0.75, evidence

        # ── No-impact ──
        if (not deviations or all(d.severity == "low" for d in deviations)) and intention_ok:
            if recovery_count <= self.config.max_recovery_for_no_impact:
                evidence = [
                    f"整体意图判定: 通过",
                    f"Plan 覆盖率: {plan_coverage:.0%}",
                ]
                if deviations:
                    evidence.append(f"{len(deviations)} 个低影响偏差，均已解决或无关紧要")
                return "no_impact", 0.90, evidence

        # ── Remedial ──
        if recovery_count > 0 and intention_ok:
            evidence = [
                f"存在 {len(deviations)} 个偏差，其中 {recovery_count} 个已通过自我修正恢复",
                f"整体意图判定: 通过",
                f"Plan 覆盖率: {plan_coverage:.0%}",
            ]
            if has_repeats:
                evidence.append("检测到重复操作，Agent通过回退进行了修正")
            return "remedial", 0.78, evidence

        # ── Fallback: remedial (partial) ──
        if intention_ok and deviations:
            evidence = [
                f"整体意图判定: 通过，但存在 {len(deviations)} 个轨迹偏差",
                f"Plan 覆盖率: {plan_coverage:.0%}",
            ]
            return "remedial", 0.65, evidence

        # ── Default to cascading ──
        evidence = [
            f"整体意图判定: {'通过' if intention_ok else '未通过'}",
            f"Plan 覆盖率: {plan_coverage:.0%}",
            f"偏差数: {len(deviations)}",
        ]
        return "cascading", 0.70, evidence

    # ── Utilities ─────────────────────────────────────────────

    def _merge_deviations(
        self, deviations: list[DeviationPoint]
    ) -> list[DeviationPoint]:
        """Merge overlapping deviations, keeping recovery events separate."""
        if len(deviations) <= 1:
            return deviations
        sorted_devs = sorted(deviations, key=lambda d: d.step_index)
        merged = []
        severity_order = {"high": 3, "medium": 2, "low": 1}
        for dev in sorted_devs:
            if not merged:
                merged.append(dev)
                continue
            prev = merged[-1]
            gap = abs(dev.step_index - prev.step_index)
            # Don't merge if one is a recovery event
            if prev.deviation_type == "backtrack" or dev.deviation_type == "backtrack":
                merged.append(dev)
            elif gap <= self.config.min_deviation_gap:
                if severity_order.get(dev.severity, 0) > severity_order.get(prev.severity, 0):
                    merged[-1] = dev
            else:
                merged.append(dev)
        return merged

    def _text_similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _link_recoveries(self, deviations: list[DeviationPoint]) -> None:
        """Link backtrack recovery events to preceding mismatches."""
        backtracks = [d for d in deviations if d.deviation_type == "backtrack" and d.recovered]
        mismatches = [d for d in deviations if d.deviation_type == "action_mismatch" and not d.recovered]
        for bt in backtracks:
            for mm in mismatches:
                if mm.step_index < bt.step_index:
                    mm.recovered = True
                    mm.recovery_step = bt.step_index
                    break
