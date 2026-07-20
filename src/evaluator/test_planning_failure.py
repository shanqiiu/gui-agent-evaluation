from __future__ import annotations

from src.evaluator.planning_failure import detect_planning_failure
from src.verifier import Checkpoint, CheckpointResult, VerificationReport
from src.verifier.alignment import CheckpointIntentMatch


def _report(results):
    return VerificationReport(
        task_uuid="case-001",
        instruction="test",
        results=results,
        total_checkpoints=len(results),
        achieved_count=sum(1 for r in results if r.status == "达成"),
        required_total=sum(1 for r in results if r.checkpoint.required),
        required_achieved=sum(
            1 for r in results if r.checkpoint.required and r.status == "达成"
        ),
    )


def _payload(actions):
    return {
        "seq_info": [
            {
                "index": idx,
                "planning_output": {
                    "parsed_action": {"action_type": action_type},
                },
            }
            for idx, action_type in actions
        ]
    }


def test_unmatched_required_checkpoint_is_planning_failure():
    checkpoints = [Checkpoint(name="进入搜索结果页")]
    result = detect_planning_failure(
        checkpoints=checkpoints,
        payload=_payload([(0, "click"), (1, "finished")]),
        intent_matches=[
            CheckpointIntentMatch(
                checkpoint_index=0,
                matched=False,
                score=0.0,
                confidence="unmatched_intent",
            )
        ],
        verification_report=_report([]),
    )

    assert result.label == "abnormal"
    assert result.subtype == "missing_required_checkpoint"
    assert result.missing_checkpoints[0]["status"] == "unmatched_intent"


def test_matched_but_not_achieved_is_execution_blocked():
    checkpoint = Checkpoint(name="进入搜索结果页")
    result = detect_planning_failure(
        checkpoints=[checkpoint],
        payload=_payload([(0, "click"), (1, "finished")]),
        intent_matches=[
            CheckpointIntentMatch(
                checkpoint_index=0,
                matched=True,
                score=0.9,
                confidence="high",
            )
        ],
        verification_report=_report([
            CheckpointResult(
                checkpoint=checkpoint,
                status="未达成",
                confidence=0.86,
                step_index=0,
            )
        ]),
    )

    assert result.label == "abnormal"
    assert result.subtype == "execution_blocked"
    assert result.missing_checkpoints[0]["status"] == "not_achieved"


def test_earliest_blocking_event_wins_over_later_missing_checkpoint():
    checkpoints = [
        Checkpoint(name="目标商品详情页已打开"),
        Checkpoint(name="订单提交页面已就绪"),
    ]
    result = detect_planning_failure(
        checkpoints=checkpoints,
        payload=_payload([(5, "click"), (16, "finished")]),
        intent_matches=[
            CheckpointIntentMatch(
                checkpoint_index=0,
                matched=True,
                score=0.8,
                confidence="high",
            ),
            CheckpointIntentMatch(
                checkpoint_index=1,
                matched=False,
                score=0.0,
                confidence="unmatched_intent",
            ),
        ],
        verification_report=_report([
            CheckpointResult(
                checkpoint=checkpoints[0],
                status="未达成",
                confidence=1.0,
                step_index=5,
            )
        ]),
    )

    assert result.label == "abnormal"
    assert result.subtype == "execution_blocked"
    assert result.first_error_step == 5
    assert [event.subtype for event in result.events] == [
        "execution_blocked",
        "missing_required_checkpoint",
        "premature_termination",
    ]


def test_finished_before_required_completion_is_premature_termination():
    checkpoint = Checkpoint(name="进入搜索结果页")
    result = detect_planning_failure(
        checkpoints=[checkpoint],
        payload=_payload([(0, "finished")]),
        intent_matches=[
            CheckpointIntentMatch(
                checkpoint_index=0,
                matched=True,
                score=0.9,
                confidence="high",
            )
        ],
        verification_report=_report([
            CheckpointResult(
                checkpoint=checkpoint,
                status="不确定",
                confidence=0.2,
                step_index=-1,
            )
        ]),
    )

    assert result.label == "abnormal"
    assert result.subtype == "premature_termination"


def test_fail_to_terminate_after_required_completion():
    checkpoint = Checkpoint(name="进入搜索结果页")
    result = detect_planning_failure(
        checkpoints=[checkpoint],
        payload=_payload([(0, "click"), (1, "click"), (2, "click"), (3, "click")]),
        intent_matches=[
            CheckpointIntentMatch(
                checkpoint_index=0,
                matched=True,
                score=0.9,
                confidence="high",
            )
        ],
        verification_report=_report([
            CheckpointResult(
                checkpoint=checkpoint,
                status="达成",
                confidence=0.9,
                step_index=0,
            )
        ]),
        repeated_prediction={"label": "abnormal"},
    )

    assert result.label == "abnormal"
    assert result.subtype == "fail_to_terminate"
    assert "repeated_action" in result.related_anomalies
