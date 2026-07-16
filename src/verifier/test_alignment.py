"""Tests for checkpoint-to-step alignment."""

from __future__ import annotations

from src.common import ABValidationReport, StepABResult
from src.verifier import Checkpoint, align_checkpoints_to_steps


def test_generic_form_flow_checkpoints_align_to_semantic_steps():
    payload = {
        "seq_info": [
            _step(1, "open_app", "open settings"),
            _step(2, "click", "tap account section"),
            _step(3, "type", "input user name alice"),
            _step(4, "click", "tap save button"),
            _step(5, "click", "tap profile details"),
        ]
    }
    ab_report = ABValidationReport(results=[
        StepABResult(
            step_index=1,
            action_des="open settings",
            pageb_description="settings home page with account section",
        ),
        StepABResult(
            step_index=2,
            action_des="tap account section",
            pageb_description="account form page with user name input field",
        ),
        StepABResult(
            step_index=3,
            action_des="input user name alice",
            pageb_description="account form page where user name input shows alice",
        ),
        StepABResult(
            step_index=4,
            action_des="tap save button",
            pageb_description="account form saved successfully and profile summary is visible",
        ),
        StepABResult(
            step_index=5,
            action_des="tap profile details",
            pageb_description="profile details page displays user name alice and account status",
        ),
    ])
    checkpoints = [
        Checkpoint(
            name="open settings app",
            expected_state="settings home page is displayed",
        ),
        Checkpoint(
            name="enter account page",
            expected_state="account form page with user name input field",
        ),
        Checkpoint(
            name="input user name",
            expected_state="user name input field displays alice",
        ),
        Checkpoint(
            name="save account form",
            expected_state="profile summary is visible after saving",
        ),
        Checkpoint(
            name="confirm profile details",
            expected_state="profile details page displays user name alice",
        ),
    ]

    alignments = align_checkpoints_to_steps(checkpoints, payload, ab_report=ab_report)

    assert [item.step_index for item in alignments] == [1, 2, 3, 4, 5]
    assert all(item.confidence != "unmatched" for item in alignments)


def test_adjacent_checkpoints_can_share_one_step_when_state_satisfies_both():
    payload = {
        "seq_info": [
            _step(10, "type", "input verification code 123456"),
            _step(11, "click", "tap continue"),
        ]
    }
    ab_report = ABValidationReport(results=[
        StepABResult(
            step_index=10,
            action_des="input verification code 123456",
            pageb_description="verification code field displays 123456 and continue button is enabled",
        ),
        StepABResult(
            step_index=11,
            action_des="tap continue",
            pageb_description="next setup page is displayed",
        ),
    ])
    checkpoints = [
        Checkpoint(
            name="input verification code",
            expected_state="verification code field displays 123456",
        ),
        Checkpoint(
            name="continue button enabled",
            expected_state="continue button is enabled",
        ),
    ]

    alignments = align_checkpoints_to_steps(checkpoints, payload, ab_report=ab_report)

    assert [item.step_index for item in alignments] == [10, 10]
    assert all(item.confidence != "unmatched" for item in alignments)


def _step(index: int, action_type: str, text: str) -> dict:
    return {
        "index": index,
        "planning_output": {
            "parsed_action": {
                "action_type": action_type,
                "text": text,
            }
        },
    }
