"""Tests for grounding-error detection."""

from __future__ import annotations

from src.evaluator.grounding import GroundingEvent, detect_grounding_errors


# ── helpers ──────────────────────────────────────────────────────────


def _tap_payload(action_type: str = "click", step_range: tuple[int, int] = (0, 1)) -> dict:
    return {
        "seq_info": [
            {
                "index": step_range[0],
                "planning_output": {
                    "parsed_action": {"action_type": action_type},
                },
            },
        ],
    }


def _ab_report_unexpected(steps: list[int]) -> dict:
    return {
        "results": {
            str(s): {
                "step_index": s,
                "label": "不符合预期",
                "action_des": "tap action",
            }
            for s in steps
        }
    }


def _state_sequence_visual(
    purpose: str = "tap button",
    pixel_diff: float = 0.01,
    ssim: float = 0.98,
    phash_dist: int = 1,
) -> dict:
    return {
        "states": [
            {
                "label": "state-0",
                "step_range": [0, 1],
                "action_types": ["click"],
                "action_purposes": [purpose],
                "page_description": "home page",
                "visual_change_summary": {
                    "pixel_diff_ratio": pixel_diff,
                    "ssim": ssim,
                    "phash_distance": phash_dist,
                },
            }
        ]
    }


# ── tests ────────────────────────────────────────────────────────────


def test_wrong_tap_target_detected() -> None:
    events = detect_grounding_errors(
        _tap_payload("click"),
        ab_report=_ab_report_unexpected([0]),
        state_sequence=_state_sequence_visual("tap settings button", pixel_diff=0.01, ssim=0.98, phash_dist=1),
    )

    assert len(events) == 1
    evt = events[0]
    assert evt.subtype == "wrong_tap_target"
    assert evt.first_error_step == 0
    assert evt.confidence == 0.74
    assert "tap action" in evt.message.lower() or "no expected page change" in evt.message


def test_wrong_tap_not_detected_when_visual_changes() -> None:
    events = detect_grounding_errors(
        _tap_payload("click"),
        ab_report=_ab_report_unexpected([0]),
        state_sequence=_state_sequence_visual("tap button", pixel_diff=0.20, ssim=0.80, phash_dist=15),
    )

    # Visual change exists, so it's NOT a grounding error (action landed, something happened)
    assert len(events) == 0


def test_wrong_tap_not_detected_without_unexpected_ab() -> None:
    ab = {
        "results": {
            "0": {
                "step_index": 0,
                "label": "符合预期",
                "action_des": "tap action",
            }
        }
    }
    events = detect_grounding_errors(
        _tap_payload("click"),
        ab_report=ab,
        state_sequence=_state_sequence_visual("tap button", pixel_diff=0.01, ssim=0.98, phash_dist=1),
    )

    assert len(events) == 0


def test_wrong_input_location_detected() -> None:
    payload = {
        "seq_info": [
            {
                "index": 5,
                "planning_output": {
                    "parsed_action": {"action_type": "input"},
                },
            },
        ],
    }
    ab = {
        "results": {
            "5": {
                "step_index": 5,
                "label": "不符合预期",
            }
        }
    }
    state_seq = {
        "states": [
            {
                "label": "input-state",
                "step_range": [5, 6],
                "action_types": ["input"],
                "action_purposes": ["输入搜索关键词"],
                "page_description": "search page",
                "visual_change_summary": {
                    "ocr_text_similarity": 0.95,
                    "rawpage_changed": False,
                },
            }
        ]
    }

    events = detect_grounding_errors(
        payload,
        ab_report=ab,
        state_sequence=state_seq,
    )

    assert len(events) == 1
    evt = events[0]
    assert evt.subtype == "wrong_input_location"
    assert evt.first_error_step == 5
    assert evt.confidence == 0.70


def test_wrong_input_not_detected_when_ocr_changes() -> None:
    payload = {
        "seq_info": [
            {
                "index": 3,
                "planning_output": {
                    "parsed_action": {"action_type": "input"},
                },
            },
        ],
    }
    ab = {
        "results": {
            "3": {
                "step_index": 3,
                "label": "不符合预期",
            }
        }
    }
    state_seq = {
        "states": [
            {
                "label": "input-state",
                "step_range": [3, 4],
                "action_types": ["input"],
                "action_purposes": ["enter search"],
                "page_description": "search page",
                "visual_change_summary": {
                    "ocr_text_similarity": 0.45,
                    "rawpage_changed": True,
                },
            }
        ]
    }

    events = detect_grounding_errors(
        payload,
        ab_report=ab,
        state_sequence=state_seq,
    )

    # OCR did change, so input likely went to the right place
    assert len(events) == 0


def test_wrong_scroll_direction_detected() -> None:
    payload = {
        "seq_info": [
            {
                "index": 10,
                "planning_output": {
                    "parsed_action": {"action_type": "swipe"},
                },
            },
        ],
    }
    ab = {
        "results": {
            "10": {
                "step_index": 10,
                "label": "不符合预期",
            }
        }
    }
    state_seq = {
        "states": [
            {
                "label": "scroll-state",
                "step_range": [10, 11],
                "action_types": ["swipe"],
                "action_purposes": ["swipe up to see more content"],
                "page_description": "list page",
                "visual_change_summary": {
                    "pixel_diff_ratio": 0.02,
                    "ssim": 0.97,
                    "phash_distance": 2,
                },
            }
        ]
    }

    events = detect_grounding_errors(
        payload,
        ab_report=ab,
        state_sequence=state_seq,
    )

    assert len(events) == 1
    evt = events[0]
    assert evt.subtype == "wrong_scroll_direction"
    assert evt.first_error_step == 10
    assert evt.confidence == 0.68


def test_scroll_not_detected_with_visual_change() -> None:
    payload = {
        "seq_info": [
            {
                "index": 2,
                "planning_output": {
                    "parsed_action": {"action_type": "swipe"},
                },
            },
        ],
    }
    ab = {
        "results": {
            "2": {
                "step_index": 2,
                "label": "不符合预期",
            }
        }
    }
    state_seq = {
        "states": [
            {
                "label": "scroll-state",
                "step_range": [2, 3],
                "action_types": ["swipe"],
                "action_purposes": ["swipe down"],
                "page_description": "list page",
                "visual_change_summary": {
                    "pixel_diff_ratio": 0.25,
                    "ssim": 0.75,
                    "phash_distance": 20,
                },
            }
        ]
    }

    events = detect_grounding_errors(
        payload,
        ab_report=ab,
        state_sequence=state_seq,
    )

    # Major visual change = scroll likely succeeded
    assert len(events) == 0


def test_no_grounding_without_ab_report() -> None:
    events = detect_grounding_errors(
        _tap_payload("click"),
        ab_report=None,
        state_sequence=_state_sequence_visual("tap button"),
    )

    assert len(events) == 0


def test_no_grounding_without_state_sequence() -> None:
    events = detect_grounding_errors(
        _tap_payload("click"),
        ab_report=_ab_report_unexpected([0]),
        state_sequence=None,
    )

    assert len(events) == 0


def test_grounding_event_to_dict() -> None:
    evt = GroundingEvent(
        subtype="wrong_tap_target",
        confidence=0.74,
        first_error_step=3,
        end_step=4,
        evidence_refs=["state_sequence.states[1]"],
        message="tap missed target",
    )
    d = evt.to_dict()
    assert d["category"] == "grounding_error"
    assert d["subtype"] == "wrong_tap_target"
    assert d["first_error_step"] == 3
    assert d["end_step"] == 4
    assert d["confidence"] == 0.74
    assert d["recovery_outcome"] == "unknown"
