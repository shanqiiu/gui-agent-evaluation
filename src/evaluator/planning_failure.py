"""Planning-failure aggregation for the new evaluator baseline.

This module consumes the outputs already produced by repeated_baseline:
intent matches, checkpoint verification, state sequence, and repeated-action
prediction. It does not depend on legacy oracle/Darwin structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.verifier import Checkpoint


@dataclass(frozen=True)
class PlanningFailureConfig:
    completion_threshold: float = 0.95
    fail_to_terminate_extra_steps: int = 2


@dataclass
class PlanningFailureEvent:
    subtype: str
    confidence: float
    first_error_step: int = -1
    checkpoint_index: int = -1
    checkpoint_name: str = ""
    evidence: list[str] = field(default_factory=list)
    related_anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtype": self.subtype,
            "confidence": round(self.confidence, 3),
            "first_error_step": self.first_error_step,
            "checkpoint_index": self.checkpoint_index,
            "checkpoint_name": self.checkpoint_name,
            "evidence": self.evidence,
            "related_anomalies": self.related_anomalies,
        }


@dataclass
class PlanningFailureResult:
    label: str = "normal"
    subtype: str = "none"
    confidence: float = 0.0
    first_error_step: int = -1
    completion_score: float = 0.0
    required_completion_score: float = 0.0
    total_checkpoints: int = 0
    required_total: int = 0
    achieved_count: int = 0
    required_achieved: int = 0
    missing_checkpoints: list[dict[str, Any]] = field(default_factory=list)
    uncertain_checkpoints: list[dict[str, Any]] = field(default_factory=list)
    related_anomalies: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    events: list[PlanningFailureEvent] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "type": "planning_failure",
            "subtype": self.subtype,
            "confidence": round(self.confidence, 3),
            "first_error_step": self.first_error_step,
            "completion_score": round(self.completion_score, 3),
            "required_completion_score": round(self.required_completion_score, 3),
            "summary": {
                "total_checkpoints": self.total_checkpoints,
                "required_total": self.required_total,
                "achieved_count": self.achieved_count,
                "required_achieved": self.required_achieved,
            },
            "missing_checkpoints": self.missing_checkpoints,
            "uncertain_checkpoints": self.uncertain_checkpoints,
            "related_anomalies": self.related_anomalies,
            "evidence": self.evidence,
            "events": [event.to_dict() for event in self.events],
            "message": self.summary,
        }


def detect_planning_failure(
    *,
    checkpoints: list[Checkpoint],
    payload: dict[str, Any] | None = None,
    intent_matches: list[Any] | None = None,
    verification_report: Any = None,
    state_sequence: Any = None,
    repeated_prediction: Any = None,
    config: PlanningFailureConfig | None = None,
) -> PlanningFailureResult:
    """Aggregate task-level planning failure from new-baseline artifacts."""
    detector = PlanningFailureAggregator(config or PlanningFailureConfig())
    return detector.detect(
        checkpoints=checkpoints,
        payload=payload or {},
        intent_matches=intent_matches or [],
        verification_report=verification_report,
        state_sequence=state_sequence,
        repeated_prediction=repeated_prediction,
    )


class PlanningFailureAggregator:
    def __init__(self, config: PlanningFailureConfig):
        self.config = config

    def detect(
        self,
        *,
        checkpoints: list[Checkpoint],
        payload: dict[str, Any],
        intent_matches: list[Any],
        verification_report: Any,
        state_sequence: Any,
        repeated_prediction: Any,
    ) -> PlanningFailureResult:
        del state_sequence
        if not checkpoints:
            return PlanningFailureResult(
                label="uncertain",
                summary="缺少 _checkpoints，无法进行规划失效聚合。",
            )

        verification_by_cp = self._verification_by_checkpoint(verification_report)
        intent_by_cp = {
            self._int(_value(match, "checkpoint_index", idx), idx): match
            for idx, match in enumerate(intent_matches)
        }
        stats = self._stats(checkpoints, verification_by_cp)
        terminal_step = self._terminal_step(payload)
        events: list[PlanningFailureEvent] = []
        missing: list[dict[str, Any]] = []
        uncertain: list[dict[str, Any]] = []

        for cp_idx, checkpoint in enumerate(checkpoints):
            if not checkpoint.required:
                continue
            intent = intent_by_cp.get(cp_idx)
            verification = verification_by_cp.get(cp_idx)
            intent_matched = bool(_value(intent, "matched", False))
            status = str(_value(verification, "status", "") or "")
            confidence = self._float(_value(verification, "confidence", 0.0), 0.0)
            step_index = self._int(_value(verification, "step_index", -1), -1)

            if not intent_matched:
                item = self._checkpoint_item(cp_idx, checkpoint, "unmatched_intent", step_index)
                missing.append(item)
                events.append(PlanningFailureEvent(
                    subtype="missing_required_checkpoint",
                    confidence=0.84,
                    first_error_step=terminal_step,
                    checkpoint_index=cp_idx,
                    checkpoint_name=checkpoint.name,
                    evidence=[
                        f"必要 checkpoint 未被实际 agent_purpose 召回：{checkpoint.name}",
                        "意图层未匹配，跳过执行层达成判定。",
                    ],
                ))
                continue

            if status == "未达成":
                item = self._checkpoint_item(cp_idx, checkpoint, "not_achieved", step_index)
                missing.append(item)
                events.append(PlanningFailureEvent(
                    subtype="execution_blocked",
                    confidence=max(0.72, min(confidence, 0.9)),
                    first_error_step=step_index if step_index >= 0 else terminal_step,
                    checkpoint_index=cp_idx,
                    checkpoint_name=checkpoint.name,
                    evidence=[
                        f"必要 checkpoint 有意图匹配但截图/VLM 未证明达成：{checkpoint.name}",
                        f"verifier_status={status}, confidence={confidence:.2f}",
                    ],
                ))
                continue

            if status in {"不确定", ""}:
                uncertain.append(self._checkpoint_item(
                    cp_idx,
                    checkpoint,
                    "uncertain" if status else "not_verified",
                    step_index,
                ))

        if terminal_step >= 0 and stats["required_completion_score"] < self.config.completion_threshold:
            events.append(PlanningFailureEvent(
                subtype="premature_termination",
                confidence=0.82,
                first_error_step=terminal_step,
                evidence=[
                    "轨迹出现 finished/done 终止动作。",
                    f"required checkpoint 完成率为 {stats['required_completion_score']:.2f}。",
                ],
            ))

        fail_to_terminate = self._fail_to_terminate_event(
            payload,
            verification_by_cp,
            stats["required_completion_score"],
            repeated_prediction,
        )
        if fail_to_terminate is not None:
            events.append(fail_to_terminate)

        if not events:
            if uncertain:
                return PlanningFailureResult(
                    label="uncertain",
                    completion_score=stats["completion_score"],
                    required_completion_score=stats["required_completion_score"],
                    total_checkpoints=stats["total"],
                    required_total=stats["required_total"],
                    achieved_count=stats["achieved"],
                    required_achieved=stats["required_achieved"],
                    uncertain_checkpoints=uncertain,
                    evidence=["存在未验证或不确定 checkpoint，不能给出高置信规划失败结论。"],
                    summary="规划失效证据不足。",
                )
            return PlanningFailureResult(
                label="normal",
                completion_score=stats["completion_score"],
                required_completion_score=stats["required_completion_score"],
                total_checkpoints=stats["total"],
                required_total=stats["required_total"],
                achieved_count=stats["achieved"],
                required_achieved=stats["required_achieved"],
                summary="未发现规划失效异常。",
            )

        primary = self._primary_event(events)
        related = self._related_anomalies(events, repeated_prediction)
        evidence = self._dedupe([text for event in events for text in event.evidence])
        return PlanningFailureResult(
            label="abnormal",
            subtype=primary.subtype,
            confidence=max(event.confidence for event in events),
            first_error_step=primary.first_error_step,
            completion_score=stats["completion_score"],
            required_completion_score=stats["required_completion_score"],
            total_checkpoints=stats["total"],
            required_total=stats["required_total"],
            achieved_count=stats["achieved"],
            required_achieved=stats["required_achieved"],
            missing_checkpoints=missing,
            uncertain_checkpoints=uncertain,
            related_anomalies=related,
            evidence=evidence,
            events=events,
            summary=self._summary(primary, missing, stats["required_completion_score"]),
        )

    def _verification_by_checkpoint(self, report: Any) -> dict[int, Any]:
        results = _value(report, "results", []) or []
        by_cp: dict[int, Any] = {}
        for idx, result in enumerate(results):
            checkpoint_index = self._int(_value(result, "checkpoint_index", idx), idx)
            image_context = _value(result, "image_context", {}) or {}
            if isinstance(image_context, dict):
                checkpoint_index = self._int(
                    image_context.get("checkpoint_index", checkpoint_index),
                    checkpoint_index,
                )
            by_cp[checkpoint_index] = result
        return by_cp

    def _stats(self, checkpoints: list[Checkpoint], verification_by_cp: dict[int, Any]) -> dict[str, Any]:
        total = len(checkpoints)
        required_total = sum(1 for checkpoint in checkpoints if checkpoint.required)
        achieved = 0
        required_achieved = 0
        for cp_idx, checkpoint in enumerate(checkpoints):
            status = str(_value(verification_by_cp.get(cp_idx), "status", "") or "")
            if status == "达成":
                achieved += 1
                if checkpoint.required:
                    required_achieved += 1
        return {
            "total": total,
            "required_total": required_total,
            "achieved": achieved,
            "required_achieved": required_achieved,
            "completion_score": achieved / total if total else 0.0,
            "required_completion_score": (
                required_achieved / required_total if required_total else 1.0
            ),
        }

    def _fail_to_terminate_event(
        self,
        payload: dict[str, Any],
        verification_by_cp: dict[int, Any],
        required_completion_score: float,
        repeated_prediction: Any,
    ) -> PlanningFailureEvent | None:
        if required_completion_score < self.config.completion_threshold:
            return None
        completion_step = max(
            (
                self._int(_value(result, "step_index", -1), -1)
                for result in verification_by_cp.values()
                if str(_value(result, "status", "") or "") == "达成"
            ),
            default=-1,
        )
        if completion_step < 0:
            return None
        extra_steps = [
            step for step in self._action_steps(payload)
            if step["step"] > completion_step and step["action_type"] not in {"finished", "done", "clarify"}
        ]
        if len(extra_steps) <= self.config.fail_to_terminate_extra_steps:
            return None
        related = ["repeated_action"] if _label(repeated_prediction) == "abnormal" else []
        return PlanningFailureEvent(
            subtype="fail_to_terminate",
            confidence=0.76,
            first_error_step=extra_steps[0]["step"],
            evidence=[
                f"必要 checkpoint 已在步骤 {completion_step} 前完成。",
                f"完成后仍继续执行 {len(extra_steps)} 个非终止动作。",
            ],
            related_anomalies=related,
        )

    def _terminal_step(self, payload: dict[str, Any]) -> int:
        terminal = -1
        for step in self._action_steps(payload):
            if step["action_type"] in {"finished", "done"}:
                terminal = step["step"]
        return terminal

    def _action_steps(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for pos, item in enumerate(payload.get("seq_info") or []):
            parsed = (item.get("planning_output") or {}).get("parsed_action") or {}
            action_type = str(parsed.get("action_type", "") or "").strip().lower()
            result.append({
                "step": self._int(item.get("index", pos), pos),
                "action_type": action_type,
            })
        return result

    def _checkpoint_item(
        self,
        checkpoint_index: int,
        checkpoint: Checkpoint,
        status: str,
        step_index: int,
    ) -> dict[str, Any]:
        return {
            "checkpoint_index": checkpoint_index,
            "checkpoint_id": checkpoint.checkpoint_id,
            "name": checkpoint.name,
            "required": checkpoint.required,
            "status": status,
            "step_index": step_index,
        }

    def _primary_event(self, events: list[PlanningFailureEvent]) -> PlanningFailureEvent:
        priority = {
            "missing_required_checkpoint": 0,
            "execution_blocked": 1,
            "premature_termination": 2,
            "fail_to_terminate": 3,
            "objective_or_plan_mismatch": 4,
        }
        return sorted(events, key=lambda item: priority.get(item.subtype, 99))[0]

    def _related_anomalies(self, events: list[PlanningFailureEvent], repeated_prediction: Any) -> list[str]:
        related = [item for event in events for item in event.related_anomalies]
        if _label(repeated_prediction) == "abnormal":
            related.append("repeated_action")
        return self._dedupe(related)

    def _summary(
        self,
        primary: PlanningFailureEvent,
        missing: list[dict[str, Any]],
        required_completion_score: float,
    ) -> str:
        names = "、".join(item["name"] for item in missing if item.get("name"))
        if names:
            return (
                f"检测到规划失效：{primary.subtype}；缺失/未达成 checkpoint：{names}；"
                f"required 完成率 {required_completion_score:.2f}。"
            )
        return f"检测到规划失效：{primary.subtype}。"

    def _dedupe(self, values: list[str]) -> list[str]:
        result = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    def _int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def _value(item: Any, key: str, default: Any = None) -> Any:
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _label(item: Any) -> str:
    return str(_value(item, "label", "") or "")
