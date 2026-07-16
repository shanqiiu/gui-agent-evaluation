"""Tests for lightweight evaluator state evidence."""

from __future__ import annotations

from src.common import ABValidationReport, StepABResult, detect_repeated_actions
from src.evaluator.state_evidence import build_state_sequence


def _payload() -> dict:
    return {
        "task_uuid": "case-state",
        "seq_info": [
            {
                "index": 0,
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [100, 200],
                        "text": "点击设置",
                    }
                },
            },
            {
                "index": 1,
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [102, 202],
                        "text": "点击设置",
                    }
                },
            },
            {
                "index": 2,
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "text": "任务完成",
                    }
                },
            },
        ],
    }


def test_state_sequence_detects_page_transition():
    ab = ABValidationReport(results=[
        StepABResult(
            step_index=0,
            label="符合预期",
            action_des="点击设置",
            pagea_description="桌面",
            pageb_description="设置首页",
        ),
        StepABResult(
            step_index=1,
            label="不符合预期",
            action_des="点击设置",
            pagea_description="设置首页",
            pageb_description="设置首页",
        ),
    ])

    state_sequence = build_state_sequence(_payload(), ab)

    assert state_sequence.progress_steps == [0]
    assert len(state_sequence.states) == 2
    assert state_sequence.transitions[0].trigger_step == 0


def test_state_progress_prevents_false_repeat():
    payload = _payload()
    ab = ABValidationReport(results=[
        StepABResult(
            step_index=0,
            label="无法判定",
            action_des="点击设置",
            pagea_description="桌面",
            pageb_description="桌面",
        ),
        StepABResult(
            step_index=1,
            label="无法判定",
            action_des="点击设置",
            pagea_description="桌面",
            pageb_description="设置首页",
        ),
    ])

    without_state = detect_repeated_actions(payload, ab)
    with_state = detect_repeated_actions(
        payload,
        ab,
        state_sequence=build_state_sequence(payload, ab),
    )

    assert without_state.label == "abnormal"
    assert with_state.label == "normal"
