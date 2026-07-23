"""Unified anomaly event projection for evaluator outputs.

This module is intentionally lightweight: it maps normalized evidence already
present in payload/baseline artifacts into the project-level anomaly taxonomy.
It does not replace specialized detectors such as repeated-action or planning
failure; it provides a common event surface for downstream reports.
"""

from __future__ import annotations

import re
from typing import Any

from src.evaluator.grounding import detect_grounding_errors
from src.evaluator.hallucination import detect_hallucinations


def build_anomaly_events(
    payload: dict[str, Any],
    *,
    repeated_prediction: dict[str, Any] | None = None,
    planning_failure_prediction: dict[str, Any] | None = None,
    state_sequence: Any = None,
    ab_report: Any = None,
) -> list[dict[str, Any]]:
    """Build unified anomaly events from baseline evidence."""
    events: list[dict[str, Any]] = []
    planning = planning_failure_prediction or {}
    events.extend(_repeated_events(repeated_prediction or {}))
    events.extend(_planning_events(planning))
    events.extend(_state_interruption_events(state_sequence, planning_failure_prediction=planning))
    events.extend(
        _interruption_events(
            payload.get("_interruption_events") or [],
            planning_failure_prediction=planning,
        )
    )
    # ── grounding errors ──
    grounding_evts = detect_grounding_errors(
        payload,
        ab_report=ab_report,
        state_sequence=state_sequence,
    )
    events.extend(event.to_dict() for event in grounding_evts)
    # ── hallucinations ──
    hallucination_evts = detect_hallucinations(
        payload,
        state_sequence=state_sequence,
    )
    events.extend(event.to_dict() for event in hallucination_evts)
    return _dedupe_events(events)


_STATE_INTERRUPTION_PATTERNS: tuple[tuple[str, tuple[str, ...], float], ...] = (
    (
        "captcha_or_security_verification",
        ("验证码", "滑块", "安全验证", "验证框", "按照说明进行验证", "拖动滑块"),
        0.86,
    ),
    (
        "login_required",
        ("登录", "登陆", "未登录", "账号登录", "手机号登录"),
        0.82,
    ),
    (
        "permission_prompt",
        ("权限", "授权", "允许访问", "拒绝", "权限申请"),
        0.78,
    ),
    (
        "crash_or_app_error",
        ("崩溃", "闪退", "crash", "应用无响应", "系统遇到问题", "错误提示"),
        0.82,
    ),
    (
        "network_or_loading_blocked",
        ("加载失败", "网络错误", "网络异常", "请求超时", "无法加载", "服务器无响应", "重新加载"),
        0.8,
    ),
    (
        "loading_state",
        ("加载中", "正在加载", "请稍等", "拼命加载中"),
        0.68,
    ),
)


def _repeated_events(repeated_prediction: dict[str, Any]) -> list[dict[str, Any]]:
    if str(repeated_prediction.get("label") or "").strip().lower() != "abnormal":
        return []
    events: list[dict[str, Any]] = []
    for idx, raw in enumerate(repeated_prediction.get("ranges") or []):
        if not isinstance(raw, dict):
            continue
        repeat_type = str(raw.get("repeat_type") or "").strip()
        category = (
            "loop"
            if "state_action_loop" in repeat_type
            else "repeated_action"
        )
        events.append({
            "category": category,
            "subtype": repeat_type or category,
            "first_error_step": _int(raw.get("start_step"), -1),
            "end_step": _int(raw.get("end_step"), -1),
            "related_subtask_id": "",
            "evidence_refs": [f"repeated_prediction.ranges[{idx}]"],
            "message": str(raw.get("target") or raw.get("action_type") or "").strip(),
            "recovery_outcome": "unknown",
            "impact": "unknown",
            "confidence": _float(raw.get("confidence"), repeated_prediction.get("confidence"), 0.0),
        })
    return events


def _planning_events(planning_failure_prediction: dict[str, Any]) -> list[dict[str, Any]]:
    if str(planning_failure_prediction.get("label") or "").strip().lower() != "abnormal":
        return []
    events: list[dict[str, Any]] = []
    for idx, raw in enumerate(planning_failure_prediction.get("events") or []):
        if not isinstance(raw, dict):
            continue
        subtype = str(raw.get("subtype") or "").strip()
        category = "premature_termination" if subtype == "premature_termination" else "planning_failure"
        events.append({
            "category": category,
            "subtype": subtype or category,
            "first_error_step": _int(
                raw.get("first_error_step"),
                planning_failure_prediction.get("first_error_step"),
                -1,
            ),
            "related_subtask_id": str(raw.get("checkpoint_index") or "").strip(),
            "checkpoint_name": str(raw.get("checkpoint_name") or "").strip(),
            "evidence_refs": [f"planning_failure_prediction.events[{idx}]"],
            "message": _event_message(raw),
            "recovery_outcome": "not_recovered",
            "impact": "task_blocking",
            "confidence": _float(raw.get("confidence"), planning_failure_prediction.get("confidence"), 0.0),
        })
    return events


def _state_interruption_events(
    state_sequence: Any,
    *,
    planning_failure_prediction: dict[str, Any],
) -> list[dict[str, Any]]:
    states = _state_items(state_sequence)
    events: list[dict[str, Any]] = []
    for idx, state in enumerate(states):
        text = _state_text(state)
        if not text:
            continue
        for subtype, keywords, confidence in _STATE_INTERRUPTION_PATTERNS:
            matched = next((keyword for keyword in keywords if keyword.lower() in text.lower()), "")
            if not matched:
                continue
            events.append({
                "category": "abnormal_interruption_response",
                "subtype": subtype,
                "first_error_step": _state_first_step(state),
                "related_subtask_id": "",
                "evidence_refs": [f"state_sequence.states[{idx}]"],
                "message": _state_message(state),
                "matched_signal": matched,
                "recovery_outcome": _recovery_outcome(planning_failure_prediction),
                "impact": _impact(planning_failure_prediction),
                "confidence": confidence,
            })
            break
    return events


def _interruption_events(
    interruption_events: list[Any],
    *,
    planning_failure_prediction: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, raw in enumerate(interruption_events):
        if not isinstance(raw, dict):
            continue
        event_type = str(raw.get("type") or "").strip().lower()
        if event_type != "clarify":
            continue

        first_error_step = _source_step(raw)
        events.append({
            "category": "abnormal_interruption_response",
            "subtype": "manual_clarification_required",
            "first_error_step": first_error_step,
            "related_subtask_id": "",
            "evidence_refs": [f"_interruption_events[{idx}]"],
            "message": str(raw.get("message") or "").strip(),
            "source_step_id": str(raw.get("source_step_id") or "").strip(),
            "source_action": str(raw.get("source_action") or "").strip(),
            "recovery_outcome": _recovery_outcome(planning_failure_prediction),
            "impact": _impact(planning_failure_prediction),
            "confidence": 0.88,
        })
    return events


def _source_step(raw: dict[str, Any]) -> int:
    for key in ("source_step_index", "raw_step_index"):
        value = raw.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    source_step_id = str(raw.get("source_step_id") or "")
    match = re.search(r"\d+", source_step_id)
    return int(match.group(0)) if match else -1


def _state_items(state_sequence: Any) -> list[dict[str, Any]]:
    if state_sequence is None:
        return []
    if hasattr(state_sequence, "to_dict"):
        state_sequence = state_sequence.to_dict()
    if not isinstance(state_sequence, dict):
        return []
    return [item for item in state_sequence.get("states") or [] if isinstance(item, dict)]


def _state_text(state: dict[str, Any]) -> str:
    parts = [
        str(state.get("label") or ""),
        str(state.get("page_description") or ""),
    ]
    for value in state.get("action_purposes") or []:
        parts.append(str(value))
    for value in state.get("evidence") or []:
        parts.append(str(value))
    return " ".join(part.strip() for part in parts if part and part.strip())


def _state_message(state: dict[str, Any]) -> str:
    return (
        str(state.get("page_description") or "").strip()
        or str(state.get("label") or "").strip()
        or "interruption state detected"
    )


def _state_first_step(state: dict[str, Any]) -> int:
    step_range = state.get("step_range") or []
    if isinstance(step_range, list) and step_range:
        return _int(step_range[0], -1)
    source_steps = state.get("source_step_indices") or []
    if isinstance(source_steps, list) and source_steps:
        return _int(source_steps[0], -1)
    return -1


def _event_message(raw: dict[str, Any]) -> str:
    evidence = raw.get("evidence") or []
    if isinstance(evidence, list) and evidence:
        return str(evidence[0]).strip()
    return str(raw.get("checkpoint_name") or raw.get("subtype") or "").strip()


def _int(*values: Any) -> int:
    default = -1
    for value in values:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        if isinstance(value, float):
            return int(value)
        default = value if isinstance(value, int) else default
    return default


def _float(*values: Any) -> float:
    for value in values:
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            continue
    return 0.0


def _recovery_outcome(planning_failure_prediction: dict[str, Any]) -> str:
    label = str(planning_failure_prediction.get("label") or "").strip().lower()
    if label == "abnormal":
        return "not_recovered"
    if label == "normal":
        return "recovered_or_non_blocking"
    return "unknown"


def _impact(planning_failure_prediction: dict[str, Any]) -> str:
    label = str(planning_failure_prediction.get("label") or "").strip().lower()
    if label == "abnormal":
        return "task_blocking"
    if label == "normal":
        return "no_confirmed_task_failure"
    return "unknown"


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for event in events:
        key = (
            str(event.get("category") or ""),
            str(event.get("subtype") or ""),
            _int(event.get("first_error_step"), -1),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped
