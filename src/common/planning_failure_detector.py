"""Planning failure detection — independent of Darwin oracle.

Detects four subtypes of planning failure from trajectory data:
    1. missing_required_step    — Required checkpoints not achieved
    2. premature_termination     — Agent stopped before completing required steps
    3. fail_to_terminate         — Agent kept acting after Plan was completed
    4. objective_or_plan_mismatch — Path or objective does not match Plan

Inputs:
    - payload (seq_info): action sequence
    - VerificationReport (Module B): checkpoint achievement status
    - ABValidationReport: AB labels per step
    - RepeatedActionResult: for linking repeated actions

Output: PlanningFailureResult with subtype, severity, evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    MissingCheckpoint,
    PlanningFailureEvent,
    PlanningFailureResult,
)


@dataclass(frozen=True)
class PlanningFailureConfig:
    completion_threshold: float = 0.95
    fail_to_terminate_extra_steps: int = 2
    low_completion_threshold: float = 0.8


def detect_planning_failures(
    payload: dict[str, Any],
    verification_report: Any = None,          # Module B VerificationReport
    ab_report: Any = None,                     # ABValidationReport
    repeated_action_result: Any = None,        # RepeatedActionResult
    config: PlanningFailureConfig | None = None,
) -> PlanningFailureResult:
    """Detect planning failures from payload + verification + AB + repeated results.

    Args:
        payload: /check_e2e payload dict.
        verification_report: Module B VerificationReport.
        ab_report: ABValidationReport.
        repeated_action_result: RepeatedActionResult from repeated_action_detector.
        config: Optional PlanningFailureConfig.

    Returns:
        PlanningFailureResult.
    """
    detector = PlanningFailureDetector(config or PlanningFailureConfig())
    return detector.detect(
        payload=payload,
        verification_report=verification_report,
        ab_report=ab_report,
        repeated_action_result=repeated_action_result,
    )


class PlanningFailureDetector:
    """Model-free planning failure detector."""

    def __init__(self, config: PlanningFailureConfig):
        self.config = config

    def detect(
        self,
        payload: dict[str, Any],
        verification_report: Any = None,
        ab_report: Any = None,
        repeated_action_result: Any = None,
    ) -> PlanningFailureResult:
        actions = self._build_actions(payload)
        step_statuses = self._collect_step_statuses(verification_report)
        total_plan = self._total_plan_count(verification_report)
        covered_plan = self._covered_plan_count(verification_report)
        completion_score = self._completion_score(covered_plan, total_plan)
        missing_cps = self._missing_checkpoints(verification_report)
        bug_only = self._is_bug_only(verification_report, missing_cps)
        events: list[PlanningFailureEvent] = []

        # 1. Missing required steps
        if missing_cps:
            events.append(PlanningFailureEvent(
                subtype="missing_required_step",
                confidence=0.82,
                first_error_step=self._terminal_step(actions),
                evidence=[
                    f"缺失必要 Plan 步骤：{self._join_names(missing_cps)}",
                    f"Plan 覆盖率为 {completion_score:.2f}",
                ],
            ))

        # 2. Premature termination
        if self._is_premature_termination(
            actions, completion_score, missing_cps,
            verification_report, bug_only
        ):
            intention_evidence = self._intention_evidence(verification_report)
            events.append(PlanningFailureEvent(
                subtype="premature_termination",
                confidence=0.88,
                first_error_step=self._terminal_step(actions),
                evidence=[
                    "最后动作是 finished/done",
                    f"Plan 覆盖率为 {completion_score:.2f}",
                    intention_evidence,
                ],
            ))

        # 3. Fail to terminate
        ft_event = self._detect_fail_to_terminate(
            actions=actions,
            verification_report=verification_report,
            completion_score=completion_score,
            repeated_action_result=repeated_action_result,
        )
        if ft_event:
            events.append(ft_event)

        # 4. Objective or plan mismatch
        if self._is_objective_or_plan_mismatch(
            verification_report, missing_cps, bug_only
        ):
            events.append(PlanningFailureEvent(
                subtype="objective_or_plan_mismatch",
                confidence=0.68,
                first_error_step=self._first_bad_ab_step(ab_report),
                evidence=[
                    self._intention_evidence(verification_report),
                ],
            ))

        events = [e for e in events if e.evidence]
        if not events:
            return self._normal_result(
                completion_score=completion_score,
                total_plan=total_plan,
                covered_plan=covered_plan,
                verification_report=verification_report,
            )

        primary = self._primary_event(events)
        severity = self._severity(primary, completion_score, events)
        confidence = max(e.confidence for e in events)
        related = self._related_anomalies(events, repeated_action_result)

        return PlanningFailureResult(
            label="abnormal",
            subtype=primary.subtype,
            severity=severity,
            confidence=round(confidence, 3),
            first_error_step=primary.first_error_step,
            completion_score=round(completion_score, 3),
            total_plan=total_plan,
            covered_plan=covered_plan,
            missing_checkpoints=missing_cps,
            related_anomalies=related,
            evidence=self._dedupe([
                ev for e in events for ev in e.evidence
            ]),
            events=events,
            summary=self._abnormal_summary(primary, missing_cps, completion_score),
        )

    # ── Action building ─────────────────────────────────────────

    def _build_actions(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for pos, item in enumerate(payload.get("seq_info") or []):
            parsed = (item.get("planning_output") or {}).get("parsed_action") or {}
            action_type = self._normalize_text(parsed.get("action_type"))
            actions.append({
                "step": int(item.get("index", pos)),
                "action_type": action_type,
                "text": self._normalize_text(parsed.get("text")),
            })
        return actions

    # ── VerificationReport consumption (replaces Darwin aligned_result) ──

    def _collect_step_statuses(
        self, verification_report: Any
    ) -> dict[str, dict[str, Any]]:
        """Collect per-checkpoint statuses from VerificationReport or legacy dict."""
        statuses: dict[str, dict[str, Any]] = {}

        # Module B VerificationReport
        if verification_report is not None and hasattr(verification_report, "results"):
            for i, r in enumerate(verification_report.results):
                cpid = f"step_{i}"
                statuses[cpid] = {
                    "id": cpid,
                    "name": r.checkpoint.name if hasattr(r.checkpoint, "name") else str(i),
                    "label": "ok" if r.status == "达成" else (
                        "nok" if r.status == "未达成" else "unknown"
                    ),
                    "page_ids": [r.step_index] if r.step_index >= 0 else [],
                    "wrong_reasons": [],
                }
            return statuses

        # Legacy Darwin dict
        if isinstance(verification_report, dict):
            for key in ("llm_intention_step", "vlm_intention_step"):
                steps = verification_report.get(key)
                if not isinstance(steps, dict):
                    continue
                for step_id, info in steps.items():
                    if not isinstance(info, dict):
                        continue
                    current = statuses.setdefault(step_id, {
                        "id": step_id,
                        "name": info.get("step") or step_id,
                        "labels": [],
                        "page_ids": [],
                        "wrong_reasons": [],
                    })
                    current["name"] = info.get("step") or current["name"]
                    current["labels"].append(info.get("label"))
                    pid = info.get("page_id")
                    if isinstance(pid, list):
                        pid = pid[0] if pid else -1
                    if isinstance(pid, int):
                        current["page_ids"].append(pid)
                    if info.get("wrong_reason"):
                        current["wrong_reasons"].append(info["wrong_reason"])

            for status in statuses.values():
                labels = [l for l in status["labels"] if l]
                if "ok" in labels:
                    status["label"] = "ok"
                elif labels and all(l == "nok" for l in labels):
                    status["label"] = "nok"
                elif "pok" in labels:
                    status["label"] = "pok"
                else:
                    status["label"] = "unknown"

        return statuses

    def _total_plan_count(self, verification_report: Any) -> int:
        if verification_report is None:
            return 0
        if hasattr(verification_report, "total_checkpoints"):
            return verification_report.total_checkpoints
        if isinstance(verification_report, dict):
            return verification_report.get("Plan步骤数", 0)
        return 0

    def _covered_plan_count(self, verification_report: Any) -> int:
        if verification_report is None:
            return 0
        if hasattr(verification_report, "achieved_count"):
            return verification_report.achieved_count
        if isinstance(verification_report, dict):
            return verification_report.get("执行覆盖Plan步骤数", 0)
        return 0

    def _completion_score(self, covered: int, total: int) -> float:
        if total <= 0:
            return 1.0
        return covered / total

    def _missing_checkpoints(
        self, verification_report: Any
    ) -> list[MissingCheckpoint]:
        checkpoints: list[MissingCheckpoint] = []

        if verification_report is not None and hasattr(verification_report, "results"):
            for r in verification_report.results:
                if hasattr(r, "status") and r.status == "未达成":
                    name = r.checkpoint.name if hasattr(r.checkpoint, "name") else "unknown"
                    required = r.checkpoint.required if hasattr(r.checkpoint, "required") else True
                    if required:
                        checkpoints.append(MissingCheckpoint(
                            name=name,
                            required=True,
                            status="not_started",
                        ))
            return checkpoints

        # Legacy
        if isinstance(verification_report, dict):
            for item in verification_report.get("未覆盖Plan") or []:
                if isinstance(item, dict):
                    name = item.get("Plan步骤名") or item.get("step") or str(item)
                else:
                    name = str(item)
                checkpoints.append(MissingCheckpoint(name=name))
        return checkpoints

    def _is_bug_only(
        self, verification_report: Any, missing_cps: list[MissingCheckpoint]
    ) -> bool:
        """Check if failures are purely functional bugs, not planning failures."""
        if missing_cps:
            return False
        if verification_report is not None and hasattr(verification_report, "results"):
            bug_count = sum(
                1 for r in verification_report.results
                if hasattr(r, "status") and r.status == "未达成"
                and hasattr(r.checkpoint, "required") and not r.checkpoint.required
            )
            if bug_count > 0 and not missing_cps:
                return True
        return False

    # ── Detection sub-methods ───────────────────────────────────

    def _is_premature_termination(
        self,
        actions: list[dict[str, Any]],
        completion_score: float,
        missing_cps: list[MissingCheckpoint],
        verification_report: Any,
        bug_only: bool,
    ) -> bool:
        if bug_only or not actions:
            return False
        terminal = actions[-1]["action_type"] in {"done", "finished"}
        if not terminal:
            return False
        if missing_cps:
            return True
        if completion_score < self.config.completion_threshold:
            return True
        # Check overall status from verification report
        if verification_report is not None and hasattr(verification_report, "overall_status"):
            if verification_report.overall_status in {"失败", "一般"}:
                return True
        return False

    def _detect_fail_to_terminate(
        self,
        actions: list[dict[str, Any]],
        verification_report: Any,
        completion_score: float,
        repeated_action_result: Any,
    ) -> PlanningFailureEvent | None:
        if completion_score < self.config.completion_threshold:
            return None
        completion_step = self._last_progress_step(verification_report)
        if completion_step < 0:
            return None
        extra = [
            a for a in actions
            if a["step"] > completion_step
            and a["action_type"] not in {"done", "finished", "clarify"}
        ]
        if len(extra) <= self.config.fail_to_terminate_extra_steps:
            return None
        related: list[str] = []
        if isinstance(repeated_action_result, dict):
            if repeated_action_result.get("label") == "abnormal":
                related.append("repeated_action")
        elif hasattr(repeated_action_result, "label"):
            if repeated_action_result.label == "abnormal":
                related.append("repeated_action")
        return PlanningFailureEvent(
            subtype="fail_to_terminate",
            confidence=0.76,
            first_error_step=extra[0]["step"],
            related_anomalies=related,
            evidence=[
                f"任务在步骤{completion_step}附近已覆盖全部Plan",
                f"完成后仍继续执行{len(extra)}个非终止动作",
                "关联重复动作异常" if related else "",
            ],
        )

    def _is_objective_or_plan_mismatch(
        self,
        verification_report: Any,
        missing_cps: list[MissingCheckpoint],
        bug_only: bool,
    ) -> bool:
        if bug_only or missing_cps:
            return False
        if verification_report is not None and hasattr(verification_report, "overall_status"):
            return verification_report.overall_status == "失败"
        return False

    def _last_progress_step(self, verification_report: Any) -> int:
        if verification_report is not None and hasattr(verification_report, "results"):
            max_step = -1
            for r in verification_report.results:
                if hasattr(r, "status") and r.status == "达成":
                    if hasattr(r, "step_index") and r.step_index > max_step:
                        max_step = r.step_index
            return max_step

        # Legacy
        if isinstance(verification_report, dict):
            page_ids: list[int] = []
            for key in ("llm_intention_step", "vlm_intention_step"):
                steps = verification_report.get(key)
                if not isinstance(steps, dict):
                    continue
                for info in steps.values():
                    if info.get("label") != "ok":
                        continue
                    pid = info.get("page_id")
                    if isinstance(pid, list):
                        pid = pid[0] if pid else -1
                    if isinstance(pid, int) and pid >= 0:
                        page_ids.append(pid)
            return max(page_ids) if page_ids else -1
        return -1

    def _terminal_step(self, actions: list[dict[str, Any]]) -> int:
        for a in actions:
            if a["action_type"] in {"done", "finished"}:
                return a["step"]
        return actions[-1]["step"] if actions else -1

    def _first_bad_ab_step(self, ab_report: Any) -> int:
        """Find first step with AB label '不符合预期'."""
        if ab_report is None:
            return -1
        # ABValidationReport
        if hasattr(ab_report, "results"):
            for r in sorted(ab_report.results, key=lambda x: x.step_index):
                if hasattr(r, "label") and r.label == "不符合预期":
                    return r.step_index
            return -1
        # Legacy Darwin dict
        if isinstance(ab_report, dict):
            ab_results = ab_report.get("ab_pages_result") or {}
            for key, item in sorted(ab_results.items(), key=lambda p: int(p[0])):
                if isinstance(item, dict) and item.get("label") not in {"符合预期", "无法判定"}:
                    return int(key)
        return -1

    # ── Event prioritization ────────────────────────────────────

    def _primary_event(self, events: list[PlanningFailureEvent]) -> PlanningFailureEvent:
        priority = {
            "premature_termination": 0,
            "missing_required_step": 1,
            "fail_to_terminate": 2,
            "objective_or_plan_mismatch": 3,
        }
        return sorted(events, key=lambda e: priority.get(e.subtype, 99))[0]

    def _severity(
        self,
        primary: PlanningFailureEvent,
        completion_score: float,
        events: list[PlanningFailureEvent],
    ) -> str:
        if primary.subtype == "premature_termination" or completion_score < self.config.low_completion_threshold:
            return "high"
        if primary.subtype == "fail_to_terminate" and len(events) > 1:
            return "high"
        return "medium"

    def _related_anomalies(
        self,
        events: list[PlanningFailureEvent],
        repeated_action_result: Any,
    ) -> list[str]:
        related = [item for e in events for item in e.related_anomalies]
        if isinstance(repeated_action_result, dict):
            if repeated_action_result.get("label") == "abnormal" and "repeated_action" not in related:
                related.append("repeated_action")
        elif hasattr(repeated_action_result, "label"):
            if repeated_action_result.label == "abnormal" and "repeated_action" not in related:
                related.append("repeated_action")
        return self._dedupe(related)

    # ── Evidence ─────────────────────────────────────────────────

    def _intention_evidence(self, verification_report: Any) -> str:
        if verification_report is None:
            return ""
        if hasattr(verification_report, "overall_status"):
            return f"综合评估结果为{verification_report.overall_status}"
        if isinstance(verification_report, dict):
            label = verification_report.get("整体意图测试结果")
            return f"整体意图测试结果为{label}" if label else ""
        return ""

    def _abnormal_summary(
        self,
        primary: PlanningFailureEvent,
        missing_cps: list[MissingCheckpoint],
        completion_score: float,
    ) -> str:
        subtype_names = {
            "premature_termination": "提前终止",
            "missing_required_step": "遗漏必要步骤",
            "fail_to_terminate": "未能终止",
            "objective_or_plan_mismatch": "目标或路径规划不一致",
        }
        name = subtype_names.get(primary.subtype, primary.subtype)
        if missing_cps:
            return f"检测到规划失效：{name}；缺失步骤：{self._join_names(missing_cps)}。"
        return f"检测到规划失效：{name}；Plan 覆盖率为 {completion_score:.2f}。"

    def _normal_result(
        self,
        completion_score: float,
        total_plan: int,
        covered_plan: int,
        verification_report: Any,
    ) -> PlanningFailureResult:
        return PlanningFailureResult(
            label="normal",
            subtype="none",
            severity="none",
            confidence=0.0,
            first_error_step=-1,
            completion_score=round(completion_score, 3),
            total_plan=total_plan,
            covered_plan=covered_plan,
            summary=f"未发现规划失效异常；Plan 覆盖率为 {completion_score:.2f}。",
        )

    # ── Utility ──────────────────────────────────────────────────

    def _join_names(self, checkpoints: list[MissingCheckpoint]) -> str:
        return "、".join(c.name for c in checkpoints if c.name)

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    def _dedupe(self, values: list[str]) -> list[str]:
        result = []
        for v in values:
            if v and v not in result:
                result.append(v)
        return result
