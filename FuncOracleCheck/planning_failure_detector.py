"""Planning failure detection for GUI Agent execution traces.

The detector reuses Darwin E2E outputs and does not issue extra model calls.
It focuses on missing required steps, premature termination, failure to
terminate, and high-level plan mismatch while avoiding functional-bug-only
cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanningFailureConfig:
    completion_threshold: float = 0.95
    fail_to_terminate_extra_steps: int = 2
    low_completion_threshold: float = 0.8


def detect_planning_failures(
    sample_dict: dict[str, Any],
    raw_oracle_result: dict[str, Any] | None = None,
    aligned_result: dict[str, Any] | None = None,
    repeated_action_result: dict[str, Any] | None = None,
    config: PlanningFailureConfig | None = None,
) -> dict[str, Any]:
    detector = PlanningFailureDetector(config or PlanningFailureConfig())
    return detector.detect(
        sample_dict=sample_dict,
        raw_oracle_result=raw_oracle_result or {},
        aligned_result=aligned_result or {},
        repeated_action_result=repeated_action_result or {},
    )


class PlanningFailureDetector:
    def __init__(self, config: PlanningFailureConfig):
        self.config = config

    def detect(
        self,
        sample_dict: dict[str, Any],
        raw_oracle_result: dict[str, Any],
        aligned_result: dict[str, Any],
        repeated_action_result: dict[str, Any],
    ) -> dict[str, Any]:
        actions = self._build_actions(sample_dict)
        step_statuses = self._collect_step_statuses(raw_oracle_result)
        total_plan = self._total_plan_count(step_statuses, aligned_result)
        covered_plan = self._covered_plan_count(step_statuses, aligned_result)
        completion_score = self._completion_score(covered_plan, total_plan)
        missing_checkpoints = self._missing_checkpoints(step_statuses, aligned_result)
        bug_steps = self._bug_steps(raw_oracle_result, aligned_result)
        bug_only = bool(bug_steps) and not missing_checkpoints
        events: list[dict[str, Any]] = []

        if missing_checkpoints:
            events.append(
                self._event(
                    subtype="missing_required_step",
                    confidence=0.82,
                    first_error_step=self._terminal_step(actions),
                    evidence=[
                        f"缺失必要 Plan 步骤：{self._join_checkpoint_names(missing_checkpoints)}",
                        f"Plan 覆盖率为 {completion_score:.2f}",
                    ],
                )
            )

        if self._is_premature_termination(actions, completion_score, missing_checkpoints, raw_oracle_result, bug_only):
            events.append(
                self._event(
                    subtype="premature_termination",
                    confidence=0.88,
                    first_error_step=self._terminal_step(actions),
                    evidence=[
                        "最后动作是 finished/done",
                        f"Plan 覆盖率为 {completion_score:.2f}",
                        self._overall_intention_evidence(raw_oracle_result, aligned_result),
                    ],
                )
            )

        fail_to_terminate_event = self._detect_fail_to_terminate(
            actions=actions,
            step_statuses=step_statuses,
            completion_score=completion_score,
            repeated_action_result=repeated_action_result,
        )
        if fail_to_terminate_event:
            events.append(fail_to_terminate_event)

        if self._is_objective_or_plan_mismatch(raw_oracle_result, aligned_result, missing_checkpoints, bug_only):
            events.append(
                self._event(
                    subtype="objective_or_plan_mismatch",
                    confidence=0.68,
                    first_error_step=self._first_bad_ab_step(raw_oracle_result),
                    evidence=[
                        self._overall_intention_evidence(raw_oracle_result, aligned_result),
                        self._path_consistency_evidence(aligned_result),
                    ],
                )
            )

        events = [event for event in events if event["evidence"]]
        if not events:
            return self._normal_result(
                summary=self._normal_summary(completion_score, bug_steps),
                completion_score=completion_score,
                total_plan=total_plan,
                covered_plan=covered_plan,
                bug_steps=bug_steps,
            )

        primary = self._primary_event(events)
        severity = self._severity(primary, completion_score, events)
        confidence = max(event["confidence"] for event in events)
        return {
            "label": "abnormal",
            "type": "planning_failure",
            "subtype": primary["subtype"],
            "severity": severity,
            "confidence": round(confidence, 3),
            "first_error_step": primary["first_error_step"],
            "completion_score": round(completion_score, 3),
            "total_plan": total_plan,
            "covered_plan": covered_plan,
            "missing_checkpoints": missing_checkpoints,
            "bug_steps": bug_steps,
            "related_anomalies": self._related_anomalies(events, repeated_action_result),
            "evidence": self._dedupe([evidence for event in events for evidence in event["evidence"]]),
            "events": events,
            "summary": self._abnormal_summary(primary, missing_checkpoints, completion_score),
        }

    def _build_actions(self, sample_dict: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for pos, item in enumerate(sample_dict.get("seq_info") or []):
            parsed_action = ((item.get("planning_output") or {}).get("parsed_action") or {})
            action_type = self._normalize_text(parsed_action.get("action_type"))
            actions.append(
                {
                    "step": int(item.get("index", pos)),
                    "action_type": action_type,
                    "text": self._normalize_text(parsed_action.get("text")),
                }
            )
        return actions

    def _collect_step_statuses(self, raw_oracle_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        for key in ("llm_intention_step", "vlm_intention_step"):
            steps = raw_oracle_result.get(key)
            if not isinstance(steps, dict):
                continue
            for step_id, info in steps.items():
                if not isinstance(info, dict):
                    continue
                current = statuses.setdefault(
                    step_id,
                    {
                        "id": step_id,
                        "name": info.get("step") or step_id,
                        "labels": [],
                        "page_ids": [],
                        "wrong_reasons": [],
                    },
                )
                current["name"] = info.get("step") or current["name"]
                current["labels"].append(info.get("label"))
                page_id = info.get("page_id")
                if isinstance(page_id, list):
                    page_id = page_id[0] if page_id else -1
                if isinstance(page_id, int):
                    current["page_ids"].append(page_id)
                if info.get("wrong_reason"):
                    current["wrong_reasons"].append(info["wrong_reason"])

        for status in statuses.values():
            labels = [label for label in status["labels"] if label]
            if "ok" in labels:
                status["label"] = "ok"
            elif labels and all(label == "nok" for label in labels):
                status["label"] = "nok"
            elif "pok" in labels:
                status["label"] = "pok"
            else:
                status["label"] = "unknown"
        return statuses

    def _total_plan_count(self, step_statuses: dict[str, dict[str, Any]], aligned_result: dict[str, Any]) -> int:
        aligned_count = aligned_result.get("Plan步骤数")
        if isinstance(aligned_count, int):
            return aligned_count
        return len(step_statuses)

    def _covered_plan_count(self, step_statuses: dict[str, dict[str, Any]], aligned_result: dict[str, Any]) -> int:
        aligned_count = aligned_result.get("执行覆盖Plan步骤数")
        if isinstance(aligned_count, int):
            return aligned_count
        return sum(1 for status in step_statuses.values() if status.get("label") == "ok")

    def _completion_score(self, covered_plan: int, total_plan: int) -> float:
        if total_plan <= 0:
            return 1.0
        return covered_plan / total_plan

    def _missing_checkpoints(
        self,
        step_statuses: dict[str, dict[str, Any]],
        aligned_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        checkpoints: list[dict[str, Any]] = []
        for item in aligned_result.get("未覆盖Plan") or []:
            if isinstance(item, dict):
                name = item.get("Plan步骤名") or item.get("step") or str(item)
            else:
                name = str(item)
            checkpoints.append({"id": "", "name": name, "required": True, "status": "not_started"})

        for step_id, status in step_statuses.items():
            if status.get("label") != "nok":
                continue
            checkpoints.append(
                {
                    "id": step_id,
                    "name": status.get("name") or step_id,
                    "required": True,
                    "status": "not_started",
                    "wrong_reason": self._join(status.get("wrong_reasons") or []),
                }
            )
        return self._dedupe_checkpoints(checkpoints)

    def _bug_steps(self, raw_oracle_result: dict[str, Any], aligned_result: dict[str, Any]) -> list[str]:
        bug_steps: list[str] = []
        for item in aligned_result.get("存在问题的功能") or []:
            bug_steps.append(str(item))
        for key in ("llm_intention_step_identity", "vlm_intention_step_identity"):
            identity = raw_oracle_result.get(key)
            if isinstance(identity, dict):
                bug_steps.extend(str(step) for step in identity.get("bug_steps") or [])
        return self._dedupe(bug_steps)

    def _is_premature_termination(
        self,
        actions: list[dict[str, Any]],
        completion_score: float,
        missing_checkpoints: list[dict[str, Any]],
        raw_oracle_result: dict[str, Any],
        bug_only: bool,
    ) -> bool:
        if bug_only or not actions:
            return False
        terminal = actions[-1]["action_type"] in {"done", "finished"}
        if not terminal:
            return False
        overall_label = ((raw_oracle_result.get("intention") or {}).get("label") or "").lower()
        return bool(missing_checkpoints) or completion_score < self.config.completion_threshold or overall_label == "nok"

    def _detect_fail_to_terminate(
        self,
        actions: list[dict[str, Any]],
        step_statuses: dict[str, dict[str, Any]],
        completion_score: float,
        repeated_action_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if completion_score < self.config.completion_threshold:
            return None
        completion_step = self._last_progress_step(step_statuses)
        if completion_step < 0:
            return None
        extra_actions = [
            action for action in actions
            if action["step"] > completion_step and action["action_type"] not in {"done", "finished", "clarify"}
        ]
        if len(extra_actions) <= self.config.fail_to_terminate_extra_steps:
            return None
        related = []
        if repeated_action_result.get("label") == "abnormal":
            related.append("repeated_action")
        return self._event(
            subtype="fail_to_terminate",
            confidence=0.76,
            first_error_step=extra_actions[0]["step"],
            evidence=[
                f"任务在步骤{completion_step}附近已覆盖全部 Plan",
                f"完成后仍继续执行{len(extra_actions)}个非终止动作",
                "关联重复动作异常" if related else "",
            ],
            related_anomalies=related,
        )

    def _is_objective_or_plan_mismatch(
        self,
        raw_oracle_result: dict[str, Any],
        aligned_result: dict[str, Any],
        missing_checkpoints: list[dict[str, Any]],
        bug_only: bool,
    ) -> bool:
        if bug_only or missing_checkpoints:
            return False
        intention = raw_oracle_result.get("intention") or {}
        overall_label = intention.get("label") or aligned_result.get("整体意图测试结果")
        path_label = aligned_result.get("路径一致性测试结果")
        return overall_label == "nok" or path_label == "nok"

    def _last_progress_step(self, step_statuses: dict[str, dict[str, Any]]) -> int:
        page_ids: list[int] = []
        for status in step_statuses.values():
            if status.get("label") != "ok":
                continue
            page_ids.extend(page_id for page_id in status.get("page_ids", []) if isinstance(page_id, int) and page_id >= 0)
        return max(page_ids) if page_ids else -1

    def _terminal_step(self, actions: list[dict[str, Any]]) -> int:
        for action in actions:
            if action["action_type"] in {"done", "finished"}:
                return action["step"]
        return actions[-1]["step"] if actions else -1

    def _first_bad_ab_step(self, raw_oracle_result: dict[str, Any]) -> int:
        ab_results = raw_oracle_result.get("ab_pages_result") or {}
        if isinstance(ab_results, dict):
            for key, item in sorted(ab_results.items(), key=lambda pair: int(pair[0])):
                if isinstance(item, dict) and item.get("label") not in {"符合预期", "无法判定"}:
                    return int(key)
        return -1

    def _event(
        self,
        subtype: str,
        confidence: float,
        first_error_step: int,
        evidence: list[str],
        related_anomalies: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "subtype": subtype,
            "confidence": confidence,
            "first_error_step": first_error_step,
            "related_anomalies": related_anomalies or [],
            "evidence": [item for item in evidence if item],
        }

    def _primary_event(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        priority = {
            "premature_termination": 0,
            "missing_required_step": 1,
            "fail_to_terminate": 2,
            "objective_or_plan_mismatch": 3,
        }
        return sorted(events, key=lambda event: priority.get(event["subtype"], 99))[0]

    def _severity(self, primary: dict[str, Any], completion_score: float, events: list[dict[str, Any]]) -> str:
        if primary["subtype"] == "premature_termination" or completion_score < self.config.low_completion_threshold:
            return "high"
        if primary["subtype"] == "fail_to_terminate" and len(events) > 1:
            return "high"
        return "medium"

    def _related_anomalies(self, events: list[dict[str, Any]], repeated_action_result: dict[str, Any]) -> list[str]:
        related = [item for event in events for item in event.get("related_anomalies", [])]
        if repeated_action_result.get("label") == "abnormal" and "repeated_action" not in related:
            related.append("repeated_action")
        return self._dedupe(related)

    def _overall_intention_evidence(self, raw_oracle_result: dict[str, Any], aligned_result: dict[str, Any]) -> str:
        intention = raw_oracle_result.get("intention") or {}
        label = intention.get("label") or aligned_result.get("整体意图测试结果")
        reason = intention.get("wrong_reason") or aligned_result.get("整体意图测试结果判断依据")
        if not label:
            return ""
        return f"整体意图测试结果为{label}" + (f"：{reason}" if reason else "")

    def _path_consistency_evidence(self, aligned_result: dict[str, Any]) -> str:
        label = aligned_result.get("路径一致性测试结果")
        return f"路径一致性测试结果为{label}" if label else ""

    def _abnormal_summary(
        self,
        primary: dict[str, Any],
        missing_checkpoints: list[dict[str, Any]],
        completion_score: float,
    ) -> str:
        subtype_name = {
            "premature_termination": "提前终止",
            "missing_required_step": "遗漏必要步骤",
            "fail_to_terminate": "未能终止",
            "objective_or_plan_mismatch": "目标或路径规划不一致",
        }.get(primary["subtype"], primary["subtype"])
        if missing_checkpoints:
            return f"检测到规划失效：{subtype_name}；缺失步骤：{self._join_checkpoint_names(missing_checkpoints)}。"
        return f"检测到规划失效：{subtype_name}；Plan 覆盖率为 {completion_score:.2f}。"

    def _normal_summary(self, completion_score: float, bug_steps: list[str]) -> str:
        if bug_steps:
            return f"未判为规划失效；当前达尔文结果更像功能问题，涉及：{self._join(bug_steps)}。"
        return f"未发现规划失效异常；Plan 覆盖率为 {completion_score:.2f}。"

    def _normal_result(
        self,
        summary: str,
        completion_score: float,
        total_plan: int,
        covered_plan: int,
        bug_steps: list[str],
    ) -> dict[str, Any]:
        return {
            "label": "normal",
            "type": "planning_failure",
            "subtype": "none",
            "severity": "none",
            "confidence": 0.0,
            "first_error_step": -1,
            "completion_score": round(completion_score, 3),
            "total_plan": total_plan,
            "covered_plan": covered_plan,
            "missing_checkpoints": [],
            "bug_steps": bug_steps,
            "related_anomalies": [],
            "evidence": [],
            "events": [],
            "summary": summary,
        }

    def _join_checkpoint_names(self, checkpoints: list[dict[str, Any]]) -> str:
        return self._join([checkpoint.get("name", "") for checkpoint in checkpoints])

    def _join(self, values: list[str]) -> str:
        return "、".join(self._dedupe([value for value in values if value]))

    def _dedupe(self, values: list[str]) -> list[str]:
        result = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    def _dedupe_checkpoints(self, checkpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        seen = set()
        for checkpoint in checkpoints:
            key = checkpoint.get("id") or checkpoint.get("name")
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(checkpoint)
        return result

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()
