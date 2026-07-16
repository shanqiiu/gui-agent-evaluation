"""Tests for checkpoint-to-step alignment."""

from __future__ import annotations

from src.common import ABValidationReport, StepABResult
from src.verifier import Checkpoint, align_checkpoints_to_steps


def test_ecommerce_search_filter_checkpoints_align_to_semantic_steps():
    payload = {
        "seq_info": [
            _step(4, "open_app", "\u6253\u5f00\u5e94\u7528"),
            _step(5, "type", "\u8f93\u5165\u6d77\u98de\u4e1d\u6d17\u53d1\u6c3480g"),
            _step(6, "type", "\u8f93\u5165\u5b55\u5987 \u53ef\u7528 \u9694\u79bb\u971c"),
            _step(7, "click", "\u70b9\u51fb\u7b5b\u9009"),
            _step(8, "type", "\u8f93\u5165\u6700\u4f4e\u4ef7100"),
            _step(9, "click", "\u70b9\u51fb\u786e\u8ba4"),
            _step(10, "click", "\u70b9\u51fb\u5546\u54c1"),
        ]
    }
    ab_report = ABValidationReport(results=[
        StepABResult(
            step_index=4,
            action_des="\u6253\u5f00\u5e94\u7528",
            pageb_description="\u62fc\u591a\u591a\u5e94\u7528\u9996\u9875\uff0c\u5305\u542b\u641c\u7d22\u680f",
        ),
        StepABResult(
            step_index=6,
            action_des="\u8f93\u5165\u6587\u672c",
            pageb_description="\u641c\u7d22\u7ed3\u679c\u9875\uff0c\u641c\u7d22\u5173\u952e\u8bcd\u4e3a\u5b55\u5987\u53ef\u7528\u9694\u79bb\u971c\uff0c\u5c55\u793a\u76f8\u5173\u5546\u54c1\u5217\u8868",
        ),
        StepABResult(
            step_index=7,
            action_des="\u70b9\u51fb\u7b5b\u9009",
            pageb_description="\u7b5b\u9009\u754c\u9762\uff0c\u5305\u542b\u4ef7\u683c\u533a\u95f4\u548c\u786e\u8ba4\u6309\u94ae",
        ),
        StepABResult(
            step_index=8,
            action_des="\u8f93\u5165\u6587\u672c",
            pageb_description="\u7b5b\u9009\u754c\u9762\uff0c\u4ef7\u683c\u533a\u95f4\u6700\u4f4e\u4ef7\u5df2\u8f93\u5165100",
        ),
        StepABResult(
            step_index=9,
            action_des="\u70b9\u51fb\u786e\u8ba4",
            pageb_description="\u5546\u54c1\u641c\u7d22\u7ed3\u679c\u5217\u8868\u9875\uff0c\u663e\u793a\u4ef7\u683c102\u548c139\u5143\u7684\u9694\u79bb\u971c\u5546\u54c1",
        ),
        StepABResult(
            step_index=10,
            action_des="\u70b9\u51fb\u5546\u54c1",
            pageb_description="\u7b80\u7f07\u6c34\u5149\u7d20\u989c\u9694\u79bb\u971c\u5546\u54c1\u8be6\u60c5\u9875\uff0c\u4ef7\u683c102\u5143",
        ),
    ])
    checkpoints = [
        Checkpoint(
            name="\u6253\u5f00\u62fc\u591a\u591a\u5e94\u7528",
            expected_state="\u5c4f\u5e55\u663e\u793a\u62fc\u591a\u591a\u5e94\u7528\u9996\u9875",
        ),
        Checkpoint(
            name="\u8f93\u5165\u641c\u7d22\u5173\u952e\u8bcd",
            expected_state="\u641c\u7d22\u680f\u5185\u663e\u793a\u6587\u672c\u5b55\u5987\u9694\u79bb\u971c",
        ),
        Checkpoint(
            name="\u6267\u884c\u641c\u7d22",
            expected_state="\u9875\u9762\u8df3\u8f6c\u81f3\u641c\u7d22\u7ed3\u679c\u5217\u8868\u9875\uff0c\u663e\u793a\u76f8\u5173\u5546\u54c1",
        ),
        Checkpoint(
            name="\u7b5b\u9009\u4ef7\u683c\u533a\u95f4",
            expected_state="\u4ef7\u683c\u4e0b\u9650\u8bbe\u7f6e\u4e3a100\u5143",
        ),
        Checkpoint(
            name="\u6d4f\u89c8\u5e76\u786e\u8ba4\u5546\u54c1\u5c5e\u6027",
            expected_state="\u5546\u54c1\u5305\u542b\u9694\u79bb\u971c\uff0c\u4ef7\u683c\u5927\u4e8e100\u5143",
        ),
    ]

    alignments = align_checkpoints_to_steps(checkpoints, payload, ab_report=ab_report)

    assert [item.step_index for item in alignments] == [4, 6, 6, 8, 10]
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
