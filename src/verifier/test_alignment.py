"""Tests for checkpoint-to-step alignment."""

from __future__ import annotations

from src.common import ABValidationReport, StepABResult
from src.verifier import Checkpoint, align_checkpoints_to_steps, match_checkpoint_intents


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



def test_alignment_can_use_aggregated_state_purpose_when_step_text_is_weak():
    payload = {
        "seq_info": [
            _step(1, "click", "tap element"),
            _step(2, "click", "tap element"),
        ]
    }
    state_sequence = {
        "states": [
            {
                "state_id": "s_0",
                "label": "home page",
                "step_range": [1, 1],
                "source_step_indices": [1],
                "page_description": "home page with entry button",
                "action_purposes": ["enter account preferences"],
                "action_types": ["click"],
                "evidence_quality": "partial",
                "visual_change_summary": {},
            },
            {
                "state_id": "s_1",
                "label": "account preferences page",
                "step_range": [2, 2],
                "source_step_indices": [2],
                "page_description": "account preferences page displays notification switch",
                "action_purposes": ["open notification preferences"],
                "action_types": ["click"],
                "evidence_quality": "partial",
                "visual_change_summary": {},
            },
        ]
    }
    checkpoints = [
        Checkpoint(
            name="open notification preferences",
            expected_state="account preferences page displays notification switch",
        )
    ]

    without_state = align_checkpoints_to_steps(
        checkpoints,
        payload,
        min_score=0.24,
    )
    with_state = align_checkpoints_to_steps(
        checkpoints,
        payload,
        state_sequence=state_sequence,
        min_score=0.24,
    )

    assert without_state[0].step_index == -1
    assert with_state[0].step_index == 2
    assert any("state_candidate=s_1" in item for item in with_state[0].evidence)



def test_intent_recall_unmatched_blocks_execution_alignment():
    payload = {
        "seq_info": [
            _step(1, "click", "tap generic element"),
        ]
    }
    checkpoints = [
        Checkpoint(
            name="enable advanced backup setting",
            expected_state="advanced backup setting is enabled",
        )
    ]

    matches = match_checkpoint_intents(checkpoints, payload, min_score=0.5)
    alignments = align_checkpoints_to_steps(
        checkpoints,
        payload,
        intent_matches=matches,
        min_score=0.5,
    )

    assert matches[0].matched is False
    assert matches[0].confidence == "unmatched_intent"
    assert alignments[0].step_index == -1
    assert alignments[0].confidence == "unmatched_intent"
