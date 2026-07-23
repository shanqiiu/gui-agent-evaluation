"""Tests for the independent repeated baseline orchestration."""

from __future__ import annotations

import base64
import json

from src.common import ABValidationReport, StepABResult, hydrate_payload_images
from src.evaluator.repeated_baseline import (
    RepeatedBaselineConfig,
    run_repeated_baseline,
    run_repeated_baseline_batch,
)
from src.verifier import Checkpoint, align_checkpoints_to_steps


def test_hydrate_payload_images_resolves_relative_paths(tmp_path):
    image = tmp_path / "catchDataTurnId0.jpg"
    image.write_bytes(b"fake image bytes")
    payload_path = tmp_path / "payload.json"
    payload = {
        "_image_base_dir": ".",
        "seq_info": [
            {"index": 10, "image_relative_path": "catchDataTurnId0.jpg"},
            {"index": 11, "image_relative_path": ""},
        ],
    }
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    hydrated, stats = hydrate_payload_images(payload, payload_path=payload_path)

    assert hydrated["seq_info"][0]["image_relative_path"] == base64.b64encode(
        b"fake image bytes"
    ).decode("ascii")
    assert hydrated["seq_info"][0]["_image_original_ref"] == "catchDataTurnId0.jpg"
    assert stats.resolved == 1
    assert stats.missing == 1


def test_alignment_uses_source_step_indexes_and_monotonic_order():
    payload = {
        "seq_info": [
            {
                "index": 20,
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "text": "点击设置",
                    }
                },
            },
            {
                "index": 30,
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "text": "点击隐私和安全",
                    }
                },
            },
        ]
    }
    checkpoints = [
        Checkpoint(name="打开设置", expected_state="设置首页"),
        Checkpoint(name="进入隐私和安全", expected_state="隐私和安全页面"),
    ]
    ab_report = ABValidationReport(results=[
        StepABResult(step_index=20, pageb_description="设置首页"),
        StepABResult(step_index=30, pageb_description="隐私和安全页面"),
    ])

    alignments = align_checkpoints_to_steps(checkpoints, payload, ab_report=ab_report)

    assert [a.step_index for a in alignments] == [20, 30]
    assert all(a.checkpoint_index == i for i, a in enumerate(alignments))


def test_repeated_baseline_mock_end_to_end(tmp_path):
    payload = {
        "instruction": "打开设置",
        "_checkpoints": [
            {"name": "进入设置首页", "expected_state": "设置首页"},
        ],
        "seq_info": [
            {
                "index": 5,
                "image_relative_path": "",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [100, 200],
                        "text": "点击设置",
                    }
                },
            },
            {
                "index": 6,
                "image_relative_path": "",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [105, 205],
                        "text": "点击设置",
                    }
                },
            },
            {
                "index": 7,
                "image_relative_path": "",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "text": "任务完成",
                    }
                },
            },
        ],
    }
    payload_path = tmp_path / "case-001" / "payload.json"
    payload_path.parent.mkdir()
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = run_repeated_baseline(
        payload_path,
        config=RepeatedBaselineConfig(mock_mode=True),
    )

    assert result["task_uuid"] == "case-001"
    assert result["repeated_prediction"]["task_uuid"] == "case-001"
    assert result["planning_failure_prediction"]["task_uuid"] == "case-001"
    assert "intent_matches" in result
    assert "intent_matcher_diagnostics" in result
    assert result["intent_matcher_diagnostics"]["purpose_llm"]["status"] == "skipped_no_purpose_features"
    event_categories = {event["category"] for event in result["anomaly_events"]}
    assert "repeated_action" in event_categories
    assert "planning_failure" in event_categories
    assert (payload_path.parent / "repeated_baseline" / "intent_matcher_diagnostics.json").is_file()
    assert (payload_path.parent / "repeated_baseline" / "intent_matches.json").is_file()
    assert (payload_path.parent / "repeated_baseline" / "planning_failure_result.json").is_file()
    assert (payload_path.parent / "repeated_baseline" / "anomaly_events.json").is_file()
    assert (payload_path.parent / "repeated_baseline" / "baseline_result.json").is_file()


def test_repeated_baseline_emits_anomaly_event_for_clarify(tmp_path):
    payload = {
        "instruction": "打开设置",
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": "",
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "text": "点击设置",
                    }
                },
            },
        ],
        "_interruption_events": [
            {
                "type": "clarify",
                "message": "当前页面需要你手动操作",
                "source_step_id": "0",
                "source_action": "clarify(当前页面需要你手动操作);",
                "raw_step_index": 0,
            }
        ],
    }
    payload_path = tmp_path / "case-clarify" / "payload.json"
    payload_path.parent.mkdir()
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = run_repeated_baseline(
        payload_path,
        config=RepeatedBaselineConfig(mock_mode=True, verify_checkpoints=False),
    )

    assert len(result["anomaly_events"]) == 1
    event = result["anomaly_events"][0]
    assert event["category"] == "abnormal_interruption_response"
    assert event["subtype"] == "manual_clarification_required"
    assert event["first_error_step"] == 0
    assert event["recovery_outcome"] == "unknown"
    assert (payload_path.parent / "repeated_baseline" / "anomaly_events.json").is_file()

def test_repeated_baseline_batch(tmp_path):
    for case_id in ("case-001", "case-002"):
        payload = {
            "instruction": "打开设置",
            "seq_info": [
                {
                    "index": 0,
                    "image_relative_path": "",
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "click",
                            "text": "点击设置",
                        }
                    },
                },
                {
                    "index": 1,
                    "image_relative_path": "",
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "finished",
                            "text": "任务完成",
                        }
                    },
                },
            ],
        }
        case_dir = tmp_path / "preprocess_out" / case_id
        case_dir.mkdir(parents=True)
        (case_dir / "payload.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    result = run_repeated_baseline_batch(
        tmp_path / "preprocess_out",
        tmp_path / "baseline_out",
        config=RepeatedBaselineConfig(mock_mode=True),
    )

    assert result["total"] == 2
    assert result["ok"] == 2
    assert result["error"] == 0
    assert result["results"][0]["planning_failure_label"] in {"normal", "abnormal", "uncertain"}
    assert "anomaly_event_count" in result["results"][0]
    assert (tmp_path / "baseline_out" / "batch_result.json").is_file()
    assert (tmp_path / "baseline_out" / "case-001" / "baseline_result.json").is_file()
