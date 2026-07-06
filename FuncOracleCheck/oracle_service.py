"""Shared service functions for Darwin functional oracle checks."""

from __future__ import annotations

from typing import Any

from GUI_TestFramework_v1 import scripts
from GUI_TestFramework_v1.scripts.config import Config
from repeated_action_detector import detect_repeated_actions


def run_sequence(config: Config) -> dict[str, Any]:
    """Run an E2E oracle check from an initialized framework config."""
    test = scripts.sequence.HarmonyAppTest(config)
    sequence_length = len(test.json_data["seq_info"])

    if sequence_length == 0:
        test.no_image_processing()
    elif sequence_length == 1:
        test.single_image_processing(sequence_id=0)
    else:
        test.ab_pages_validate()
        test.child_sequence_router()
        test.test_result()

    aligned_result = test.result_format_align()
    repeated_action_result = detect_repeated_actions(
        sample_dict=test.json_data,
        raw_oracle_result=test.result,
        aligned_result=aligned_result,
    )
    aligned_result["重复动作判定结果"] = repeated_action_result["label"]
    aligned_result["重复动作判定依据"] = repeated_action_result["summary"]
    aligned_result["repeated_action_result"] = repeated_action_result
    return aligned_result


def run_sequence_payload(sample_dict: dict[str, Any]) -> dict[str, Any]:
    """Run an E2E oracle check from API payload metadata."""
    config = Config()
    config.project.PREDICATE_MODE = "production"
    config.data.METADATA = sample_dict
    return run_sequence(config)


def run_single_step(sample_dict: dict[str, Any]) -> dict[str, Any]:
    """Run a two-image single-step oracle check."""
    return scripts.single_step.HarmonyAPPSingleStepTest(sample_dict).run()


def build_single_step_payload(action_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert the public API action list into framework metadata."""
    if len(action_items) != 2:
        raise ValueError("single-step check requires exactly two screenshots")

    first_action = action_items[0]
    second_action = action_items[1]
    return {
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": first_action.get("img", ""),
                "planning_output": {
                    "parsed_action": {
                        "action_type": first_action.get("operType", ""),
                        "start_box": first_action.get("startBox", ""),
                        "end_box": first_action.get("endBox", ""),
                        "text": first_action.get("text", ""),
                        "direction": first_action.get("direction", ""),
                    }
                },
            },
            {
                "index": 1,
                "image_relative_path": second_action.get("img", ""),
            },
        ]
    }
