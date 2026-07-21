"""Unified anomaly event projection for evaluator outputs.

This module is intentionally lightweight: it maps normalized evidence already
present in payload/baseline artifacts into the project-level anomaly taxonomy.
It does not replace specialized detectors such as repeated-action or planning
failure; it provides a common event surface for downstream reports.
"""

from __future__ import annotations

import re
from typing import Any


def build_anomaly_events(
    payload: dict[str, Any],
    *,
    planning_failure_prediction: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build unified anomaly events from baseline evidence."""
    events: list[dict[str, Any]] = []
    events.extend(
        _interruption_events(
            payload.get("_interruption_events") or [],
            planning_failure_prediction=planning_failure_prediction or {},
        )
    )
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
