"""Tests for checkpoint verification image context metadata."""

from __future__ import annotations

from src.verifier import Checkpoint, CheckpointVerifier, VerifierConfig


def test_unmatched_checkpoint_reports_empty_image_context():
    verifier = CheckpointVerifier(VerifierConfig(mock_mode=False))
    payload = {
        "task_uuid": "ctx-case",
        "instruction": "测试",
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": "before_base64",
                "_image_original_ref": "before.png",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "text": "无关动作",
                    }
                },
            },
            {
                "index": 1,
                "image_relative_path": "after_base64",
                "_image_original_ref": "after.png",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "text": "任务完成",
                    }
                },
            },
        ],
    }

    report = verifier.verify_from_payload([
        Checkpoint(name="完全不相关的检查点", expected_state="完全不相关的页面")
    ], payload)

    item = report.to_dict()["results"][0]
    assert item["step_index"] == -1
    assert item["image_context"]["step_index"] == -1
    assert item["image_context"]["before_step_index"] == -1
    assert item["image_context"]["after_step_index"] == -1
    assert item["image_context"]["image_available"] is False
    assert item["image_context"]["alignment"]["confidence"] == "unmatched"


def test_matched_checkpoint_reports_before_after_image_indices():
    verifier = CheckpointVerifier(VerifierConfig(mock_mode=True))
    payload = {
        "task_uuid": "ctx-case",
        "instruction": "打开应用",
        "seq_info": [
            {
                "index": 4,
                "image_relative_path": "before_base64",
                "_image_original_ref": "before.png",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "open_app",
                        "text": "打开应用",
                    }
                },
            },
            {
                "index": 5,
                "image_relative_path": "after_base64",
                "_image_original_ref": "after.png",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "text": "任务完成",
                    }
                },
            },
        ],
    }

    report = verifier.verify_from_payload([
        Checkpoint(name="打开应用", expected_state="打开应用")
    ], payload)

    context = report.to_dict()["results"][0]["image_context"]
    assert context["step_index"] == 4
    assert context["before_step_index"] == 4
    assert context["after_step_index"] == 5
    assert context["before_image_available"] is True
    assert context["after_image_available"] is True
    assert context["before_image_ref"] == "before.png"
    assert context["after_image_ref"] == "after.png"
