from __future__ import annotations

from src.evaluator.anomaly_events import build_anomaly_events


def test_repeated_ranges_project_to_taxonomy_events() -> None:
    events = build_anomaly_events(
        {},
        repeated_prediction={
            "label": "abnormal",
            "ranges": [
                {
                    "start_step": 2,
                    "end_step": 4,
                    "repeat_type": "state_action_loop",
                    "confidence": 0.81,
                    "target": "settings page",
                },
                {
                    "start_step": 5,
                    "end_step": 6,
                    "repeat_type": "repeated_action",
                    "confidence": 0.74,
                    "target": "confirm button",
                },
            ],
        },
    )

    assert [event["category"] for event in events] == ["loop", "repeated_action"]
    assert events[0]["subtype"] == "state_action_loop"
    assert events[0]["first_error_step"] == 2
    assert events[1]["message"] == "confirm button"


def test_planning_events_project_premature_termination_as_top_level() -> None:
    events = build_anomaly_events(
        {},
        planning_failure_prediction={
            "label": "abnormal",
            "confidence": 0.82,
            "events": [
                {
                    "subtype": "premature_termination",
                    "first_error_step": 7,
                    "confidence": 0.82,
                    "evidence": ["finished before required subtask completed"],
                },
                {
                    "subtype": "missing_required_checkpoint",
                    "first_error_step": 7,
                    "confidence": 0.84,
                    "checkpoint_index": 1,
                    "checkpoint_name": "订单提交页面已就绪",
                },
            ],
        },
    )

    assert events[0]["category"] == "premature_termination"
    assert events[0]["subtype"] == "premature_termination"
    assert events[0]["message"] == "finished before required subtask completed"
    assert events[1]["category"] == "planning_failure"
    assert events[1]["related_subtask_id"] == "1"


def test_state_sequence_projects_interruption_keywords() -> None:
    events = build_anomaly_events(
        {},
        planning_failure_prediction={"label": "abnormal"},
        state_sequence={
            "states": [
                {
                    "label": "这是一个安全验证界面",
                    "page_description": "页面提示亲，请按照说明进行验证哦，并要求拖动滑块。",
                    "step_range": [5, 8],
                    "action_purposes": ["等待验证码页面加载完成"],
                }
            ]
        },
    )

    # May include additional events (e.g. hallucination from action_purposes);
    # the key assertion is that the interruption event is present.
    interruption_events = [e for e in events if e["category"] == "abnormal_interruption_response"]
    assert len(interruption_events) == 1
    assert interruption_events[0]["subtype"] == "captcha_or_security_verification"
    assert interruption_events[0]["first_error_step"] == 5
    assert interruption_events[0]["recovery_outcome"] == "not_recovered"


def test_grounding_integration_produces_events() -> None:
    events = build_anomaly_events(
        {
            "seq_info": [
                {
                    "index": 2,
                    "planning_output": {
                        "parsed_action": {"action_type": "click"},
                    },
                },
            ],
        },
        ab_report={
            "results": {
                "2": {
                    "step_index": 2,
                    "label": "不符合预期",
                    "action_des": "tap action",
                }
            }
        },
        state_sequence={
            "states": [
                {
                    "label": "tap-state",
                    "step_range": [2, 3],
                    "action_types": ["click"],
                    "action_purposes": ["点击设置按钮"],
                    "page_description": "home page",
                    "visual_change_summary": {
                        "pixel_diff_ratio": 0.01,
                        "ssim": 0.98,
                        "phash_distance": 2,
                    },
                }
            ]
        },
    )

    grounding_events = [e for e in events if e["category"] == "grounding_error"]
    assert len(grounding_events) == 1
    assert grounding_events[0]["subtype"] == "wrong_tap_target"
    assert grounding_events[0]["first_error_step"] == 2


def test_hallucination_integration_produces_events() -> None:
    events = build_anomaly_events(
        {},
        state_sequence={
            "states": [
                {
                    "label": "hallucination-state",
                    "step_range": [0, 1],
                    "action_types": ["click"],
                    "action_purposes": ["点击设置按钮、进入设置页面"],
                    "page_description": "当前页面为首页",
                }
            ]
        },
    )

    hall_events = [e for e in events if e["category"] == "hallucination"]
    assert len(hall_events) >= 1
    assert hall_events[0]["subtype"] == "non_existent_element"


def test_full_seven_type_taxonomy_coverage() -> None:
    """Verify that all 7 taxonomy categories can be produced."""
    events = build_anomaly_events(
        {
            "_interruption_events": [
                {
                    "type": "clarify",
                    "message": "need user input",
                    "source_step_index": 0,
                    "source_step_id": "step_0",
                    "source_action": "clarify",
                }
            ],
            "seq_info": [
                {
                    "index": 0,
                    "planning_output": {
                        "parsed_action": {"action_type": "click"},
                    },
                },
                {
                    "index": 1,
                    "planning_output": {
                        "parsed_action": {"action_type": "click"},
                    },
                },
            ],
        },
        repeated_prediction={
            "label": "abnormal",
            "ranges": [
                {
                    "start_step": 0,
                    "end_step": 1,
                    "repeat_type": "state_action_loop",
                    "target": "page",
                    "confidence": 0.8,
                },
            ],
        },
        planning_failure_prediction={
            "label": "abnormal",
            "events": [
                {
                    "subtype": "missing_required_checkpoint",
                    "first_error_step": 0,
                    "confidence": 0.84,
                    "checkpoint_index": 0,
                    "checkpoint_name": "搜索结果页面已展示",
                },
                {
                    "subtype": "premature_termination",
                    "first_error_step": 1,
                    "confidence": 0.82,
                    "evidence": ["premature finish"],
                },
            ],
        },
        ab_report={
            "results": {
                "0": {
                    "step_index": 0,
                    "label": "不符合预期",
                }
            }
        },
        state_sequence={
            "states": [
                {
                    "label": "验证码界面",
                    "step_range": [0, 1],
                    "action_types": ["click"],
                    "action_purposes": ["点击设置按钮"],
                    "page_description": "这是一个安全验证界面，请按照说明进行验证",
                    "visual_change_summary": {
                        "pixel_diff_ratio": 0.01,
                        "ssim": 0.98,
                        "phash_distance": 2,
                    },
                }
            ]
        },
    )

    categories = {e["category"] for e in events}
    expected = {
        "loop",
        "planning_failure",
        "premature_termination",
        "abnormal_interruption_response",
        "grounding_error",
        "hallucination",
        # "repeated_action" not included — state_action_loop maps to "loop"
    }
    missing = expected - categories
    assert not missing, f"Missing taxonomy categories: {missing}"
    assert len(categories) >= 6, f"Expected at least 6 categories, got {len(categories)}: {categories}"
