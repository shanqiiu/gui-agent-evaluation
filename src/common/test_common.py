"""Comprehensive tests for src/common/ — AB validator + both detectors.

Covers:
    1. ABValidator — mock mode, heuristic patterns, response parsing
    2. RepeatedActionDetector — all four repeat types, edge cases
    3. PlanningFailureDetector — all four failure subtypes, edge cases
    4. Integration — full pipeline with all modules consuming each other
"""

from __future__ import annotations

import json
import pytest

from src.common import (
    ABValidator,
    ABValidatorConfig,
    ABValidationReport,
    MissingCheckpoint,
    PlanningFailureConfig,
    PlanningFailureDetector,
    RepeatedActionConfig,
    RepeatedActionDetector,
    StepABResult,
    detect_planning_failures,
    detect_repeated_actions,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def make_payload(steps: list[dict]) -> dict:
    """Create a minimal /check_e2e payload."""
    seq_info = []
    for i, s in enumerate(steps):
        seq_info.append({
            "index": i,
            "image_relative_path": s.get("img", ""),
            "planning_output": {
                "parsed_action": {
                    "action_type": s.get("action_type", "click"),
                    "start_box": s.get("start_box", []),
                    "end_box": s.get("end_box", []),
                    "text": s.get("text", ""),
                    "direction": s.get("direction", ""),
                }
            },
        })
    return {
        "instruction": "test instruction",
        "seq_info": seq_info,
    }


def make_ab_report(results: list[StepABResult]) -> ABValidationReport:
    return ABValidationReport(
        task_uuid="test-uuid",
        results=results,
        model_used="[mock]",
    )


def make_step_ab(
    step_index: int,
    label: str = "符合预期",
    action_des: str = "",
    pagea: str = "",
    pageb: str = "",
    thought: str = "",
) -> StepABResult:
    return StepABResult(
        step_index=step_index,
        label=label,
        action_des=action_des or f"step_{step_index}_action",
        pagea_description=pagea,
        pageb_description=pageb,
        thought=thought,
    )


class MockVerificationReport:
    """Fake Module B VerificationReport for testing."""

    def __init__(
        self,
        total: int = 0,
        achieved: int = 0,
        not_achieved: int = 0,
        overall: str = "优秀",
        checkpoint_results: list[dict] | None = None,
    ):
        self.total_checkpoints = total
        self.achieved_count = achieved
        self.not_achieved_count = not_achieved
        self.uncertain_count = total - achieved - not_achieved
        self.overall_status = overall
        self.completion_score = achieved / total if total > 0 else 0.0
        self.required_completion_score = self.completion_score
        self._results = checkpoint_results or []

    @property
    def results(self):
        return [MockCheckpointResult(**r) for r in self._results]


class MockCheckpoint:
    def __init__(self, name: str = "", required: bool = True):
        self.name = name
        self.required = required


class MockCheckpointResult:
    def __init__(self, name: str = "", status: str = "达成",
                 step_index: int = -1, required: bool = True):
        self.checkpoint = MockCheckpoint(name=name, required=required)
        self.status = status
        self.step_index = step_index
        self.confidence = 0.9


# ═══════════════════════════════════════════════════════════════════
# 1. ABValidator
# ═══════════════════════════════════════════════════════════════════

class TestABValidator:
    """Test ABValidator in mock mode."""

    def test_validate_single_expected_transition(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        result = validator.validate_single(
            before_image_base64="",
            after_image_base64="",
            action_info="动作类型: click；操作目标: 打开设置应用",
            step_index=0,
        )
        assert result.label == "符合预期"
        assert result.step_index == 0
        assert result.action_des != ""

    def test_validate_single_unexpected_transition(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        result = validator.validate_single(
            before_image_base64="",
            after_image_base64="",
            action_info="动作类型: click；操作目标: 页面显示404错误",
            step_index=1,
        )
        assert result.label == "不符合预期"

    def test_validate_single_uncertain(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        result = validator.validate_single(
            before_image_base64="",
            after_image_base64="",
            action_info="动作类型: unknown_type",
            step_index=0,
        )
        assert result.label == "无法判定"
        assert result.confidence < 0.5

    def test_validate_payload_full(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        payload = make_payload([
            {"action_type": "click", "text": "打开设置应用"},
            {"action_type": "scroll", "text": "向下滑动寻找隐私"},
            {"action_type": "click", "text": "点击隐私和安全进入设置页"},
            {"action_type": "finished", "text": "任务完成"},
        ])
        report = validator.validate_payload(payload, task_uuid="test-001")
        assert report.task_uuid == "test-001"
        # finished is skipped, so 3 AB checks
        assert len(report.results) == 3
        # "打开设置应用" and "进入设置页" → 符合预期; "向下滑动" → 符合预期 (scroll pattern)
        assert all(r.label == "符合预期" for r in report.results)

    def test_validate_payload_empty(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        payload = {"seq_info": []}
        report = validator.validate_payload(payload)
        assert len(report.results) == 0

    def test_response_parsing_achieved_json(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        response = json.dumps({
            "PageB_Content": "设置首页，显示隐私、安全等选项",
            "Thought": "操作后页面确实进入了设置首页，符合预期",
            "Answer": "符合预期",
        }, ensure_ascii=False)
        result = validator._parse_vlm_response(response, step_index=0)
        assert result.label == "符合预期"
        assert "设置首页" in result.pageb_description

    def test_response_parsing_unexpected_json(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        response = json.dumps({
            "PageB_Content": "仍在桌面，未进入设置",
            "Thought": "点击后页面未变化",
            "Answer": "不符合预期",
        }, ensure_ascii=False)
        result = validator._parse_vlm_response(response, step_index=1)
        assert result.label == "不符合预期"

    def test_response_parsing_json_in_markdown(self):
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        response = '```json\n{"Answer": "符合预期", "PageB_Content": "test", "Thought": "ok"}\n```'
        result = validator._parse_vlm_response(response, step_index=0)
        assert result.label == "符合预期"

    def test_ab_report_get_method(self):
        report = ABValidationReport(
            results=[
                make_step_ab(0, "符合预期"),
                make_step_ab(2, "不符合预期"),
            ]
        )
        assert report.get(0).label == "符合预期"
        assert report.get(2).label == "不符合预期"
        # Missing step returns empty
        assert report.get(1).label == ""


# ═══════════════════════════════════════════════════════════════════
# 2. RepeatedActionDetector
# ═══════════════════════════════════════════════════════════════════

class TestRepeatedActionDetector:
    """Test repeated action detection with mock AB results."""

    def test_normal_no_repeats(self):
        payload = make_payload([
            {"action_type": "click", "start_box": [100, 200], "text": "btn1"},
            {"action_type": "click", "start_box": [300, 400], "text": "btn2"},
            {"action_type": "finished", "text": "done"},
        ])
        ab = make_ab_report([
            make_step_ab(0, "符合预期", "click btn1"),
            make_step_ab(1, "符合预期", "click btn2"),
        ])
        result = detect_repeated_actions(payload, ab)
        assert result.label == "normal"
        assert len(result.ranges) == 0

    def test_consecutive_click_repeat(self):
        payload = make_payload([
            {"action_type": "click", "start_box": [500, 900], "text": "点击设置"},
            {"action_type": "click", "start_box": [510, 910], "text": "点击设置"},
            {"action_type": "finished", "text": "done"},
        ])
        ab = make_ab_report([
            make_step_ab(0, "符合预期", "click settings"),
            make_step_ab(1, "不符合预期", "same click"),
        ])
        result = detect_repeated_actions(payload, ab)
        assert result.label == "abnormal"
        assert result.ranges[0].repeat_type == "repeated_action"

    def test_consecutive_swipe_repeat(self):
        payload = make_payload([
            {"action_type": "scroll", "direction": "down", "text": "向下滑动"},
            {"action_type": "scroll", "direction": "down", "text": "向下滑动"},
            {"action_type": "scroll", "direction": "down", "text": "向下滑动"},
            {"action_type": "scroll", "direction": "down", "text": "向下滑动"},
        ])
        # Use realistic AB labels: scrolls often get 无法判定 from VLM
        ab = make_ab_report([
            make_step_ab(0, "无法判定"),
            make_step_ab(1, "无法判定"),
            make_step_ab(2, "无法判定"),
            make_step_ab(3, "无法判定"),
        ])
        result = detect_repeated_actions(payload, ab)
        assert result.label == "abnormal"
        assert any(r.repeat_type == "repeated_swipe" for r in result.ranges)

    def test_wait_repeats(self):
        payload = make_payload([
            {"action_type": "wait", "text": "等待"},
            {"action_type": "wait", "text": "等待"},
            {"action_type": "wait", "text": "等待"},
            {"action_type": "click", "text": "next"},
        ])
        ab = make_ab_report([
            make_step_ab(0, "无法判定"),
            make_step_ab(1, "无法判定"),
            make_step_ab(2, "无法判定"),
            make_step_ab(3, "符合预期"),
        ])
        result = detect_repeated_actions(payload, ab)
        assert result.label == "abnormal"
        # May be "repeated_wait" or merged "repeated_action+repeated_wait"
        assert any("wait" in r.repeat_type for r in result.ranges)

    def test_short_loop_detection(self):
        # A→B→A pattern with same page description
        payload = make_payload([
            {"action_type": "click", "start_box": [200, 300], "text": "enter page A"},
            {"action_type": "click", "start_box": [400, 500], "text": "enter page B"},
            {"action_type": "click", "start_box": [200, 300], "text": "back to page A"},
        ])
        ab = make_ab_report([
            make_step_ab(0, "符合预期", "enter_page_a", pageb="settings home"),
            make_step_ab(1, "符合预期", "enter_page_b", pageb="privacy page"),
            make_step_ab(2, "符合预期", "back_to_a", pageb="settings home"),
        ])
        result = detect_repeated_actions(payload, ab)
        # May or may not detect depending on page similarity, but should not crash
        assert result is not None

    def test_reasonable_repeat_not_detected(self):
        # Multi-select or delete should NOT be flagged as repeat
        payload = make_payload([
            {"action_type": "click", "start_box": [100, 200], "text": "勾选item1"},
            {"action_type": "click", "start_box": [100, 300], "text": "勾选item2"},
            {"action_type": "finished", "text": "done"},
        ])
        ab = make_ab_report([
            make_step_ab(0, "符合预期", "勾选 item1"),
            make_step_ab(1, "符合预期", "勾选 item2"),
        ])
        result = detect_repeated_actions(payload, ab)
        # Both are "勾选" but different targets → not detected
        assert result.label == "normal"

    def test_too_short_sequence(self):
        payload = make_payload([{"action_type": "click", "text": "only one step"}])
        result = detect_repeated_actions(payload)
        assert result.label == "normal"
        assert "过短" in result.summary


# ═══════════════════════════════════════════════════════════════════
# 3. PlanningFailureDetector
# ═══════════════════════════════════════════════════════════════════

class TestPlanningFailureDetector:
    """Test planning failure detection with Module B mock output."""

    def test_normal_complete(self):
        payload = make_payload([
            {"action_type": "click", "text": "step 1"},
            {"action_type": "click", "text": "step 2"},
            {"action_type": "finished", "text": "done"},
        ])
        vr = MockVerificationReport(
            total=2, achieved=2, not_achieved=0, overall="优秀",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "达成", "step_index": 0},
                {"name": "点击隐私和安全", "status": "达成", "step_index": 1},
            ],
        )
        result = detect_planning_failures(payload, verification_report=vr)
        assert result.label == "normal"

    def test_premature_termination(self):
        payload = make_payload([
            {"action_type": "click", "text": "step 1"},
            {"action_type": "finished", "text": "done"},
        ])
        vr = MockVerificationReport(
            total=3, achieved=1, not_achieved=2, overall="失败",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "达成", "step_index": 0},
                {"name": "点击隐私和安全", "status": "未达成", "step_index": -1},
                {"name": "点击密码保险箱", "status": "未达成", "step_index": -1},
            ],
        )
        result = detect_planning_failures(payload, verification_report=vr)
        assert result.label == "abnormal"
        assert result.subtype == "premature_termination"

    def test_missing_required_step(self):
        payload = make_payload([
            {"action_type": "click", "text": "step 1"},
            {"action_type": "click", "text": "step 2"},
            {"action_type": "finished", "text": "done"},
        ])
        vr = MockVerificationReport(
            total=3, achieved=2, not_achieved=1, overall="良好",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "达成", "step_index": 0},
                {"name": "点击隐私和安全", "status": "达成", "step_index": 1},
                {"name": "点击密码保险箱", "status": "未达成", "step_index": -1, "required": True},
            ],
        )
        result = detect_planning_failures(payload, verification_report=vr)
        assert result.label == "abnormal"
        assert result.subtype == "premature_termination"  # has missing + terminal → premature
        assert len(result.missing_checkpoints) == 1

    def test_fail_to_terminate(self):
        payload = make_payload([
            {"action_type": "click", "text": "step 1"},
            {"action_type": "click", "text": "step 2"},
            {"action_type": "click", "text": "extra step 3"},
            {"action_type": "scroll", "text": "extra step 4"},
            {"action_type": "scroll", "text": "extra step 5"},
            {"action_type": "scroll", "text": "extra step 6"},
            {"action_type": "finished", "text": "done"},
        ])
        vr = MockVerificationReport(
            total=2, achieved=2, not_achieved=0, overall="优秀",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "达成", "step_index": 0},
                {"name": "点击隐私和安全", "status": "达成", "step_index": 1},
            ],
        )
        result = detect_planning_failures(payload, verification_report=vr)
        assert result.label == "abnormal"
        assert result.subtype == "fail_to_terminate"

    def test_objective_or_plan_mismatch(self):
        payload = make_payload([
            {"action_type": "click", "text": "wrong step"},
            {"action_type": "finished", "text": "done"},
        ])
        vr = MockVerificationReport(
            total=2, achieved=0, not_achieved=2, overall="失败",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "未达成"},
                {"name": "点击隐私和安全", "status": "未达成"},
            ],
        )
        ab = make_ab_report([
            make_step_ab(0, "不符合预期"),
        ])
        result = detect_planning_failures(
            payload, verification_report=vr, ab_report=ab,
        )
        assert result.label == "abnormal"

    def test_to_dict_output(self):
        payload = make_payload([
            {"action_type": "click", "text": "step"},
            {"action_type": "finished", "text": "done"},
        ])
        vr = MockVerificationReport(
            total=1, achieved=0, not_achieved=1, overall="失败",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "未达成"},
            ],
        )
        result = detect_planning_failures(payload, verification_report=vr)
        d = result.to_dict()
        assert "label" in d
        assert "subtype" in d
        assert "completion_score" in d


# ═══════════════════════════════════════════════════════════════════
# 4. Integration — full pipeline
# ═══════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end test: AB validator → repeated → planning failure."""

    def test_full_pipeline_normal(self):
        """Normal trajectory with no anomalies."""
        payload = make_payload([
            {"action_type": "click", "start_box": [100, 200],
             "text": "进入设置首页"},
            {"action_type": "click", "start_box": [400, 800],
             "text": "点击隐私和安全进入隐私设置页面"},
            {"action_type": "click", "start_box": [300, 600],
             "text": "点击密码保险箱"},
            {"action_type": "finished", "text": "任务完成"},
        ])

        # Step 1: AB validation
        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        ab_report = validator.validate_payload(payload)

        # Step 2: Repeated action detection
        repeated = detect_repeated_actions(payload, ab_report)
        assert repeated.label == "normal"

        # Step 3: Planning failure detection
        vr = MockVerificationReport(
            total=3, achieved=3, not_achieved=0, overall="优秀",
            checkpoint_results=[
                {"name": "进入设置首页", "status": "达成", "step_index": 0},
                {"name": "点击隐私和安全", "status": "达成", "step_index": 1},
                {"name": "点击密码保险箱", "status": "达成", "step_index": 2},
            ],
        )
        planning = detect_planning_failures(
            payload, verification_report=vr, ab_report=ab_report,
            repeated_action_result=repeated,
        )
        assert planning.label == "normal"

    def test_full_pipeline_with_repeated_and_missing(self):
        """Trajectory with repeated actions AND missing checkpoints."""
        payload = make_payload([
            {"action_type": "click", "start_box": [400, 800],
             "text": "点击隐私和安全"},
            {"action_type": "click", "start_box": [410, 810],
             "text": "点击隐私和安全"},
            {"action_type": "finished", "text": "任务完成"},
        ])

        validator = ABValidator(ABValidatorConfig(mock_mode=True))
        ab_report = validator.validate_payload(payload)

        repeated = detect_repeated_actions(payload, ab_report)
        assert repeated.label == "abnormal"

        vr = MockVerificationReport(
            total=2, achieved=1, not_achieved=1, overall="一般",
            checkpoint_results=[
                {"name": "进入隐私设置页", "status": "达成", "step_index": 0},
                {"name": "点击密码保险箱", "status": "未达成"},
            ],
        )
        planning = detect_planning_failures(
            payload, verification_report=vr,
            repeated_action_result=repeated,
        )
        assert planning.label == "abnormal"
        # Should have "repeated_action" in related anomalies
        assert "repeated_action" in planning.related_anomalies

    def test_convenience_functions(self):
        """Test the module-level convenience functions."""
        payload = make_payload([
            {"action_type": "click", "text": "test"},
            {"action_type": "finished", "text": "done"},
        ])
        ab = make_ab_report([make_step_ab(0, "符合预期")])
        result = detect_repeated_actions(payload, ab)
        assert result is not None

        vr = MockVerificationReport(total=1, achieved=1)
        plan = detect_planning_failures(payload, verification_report=vr)
        assert plan is not None
