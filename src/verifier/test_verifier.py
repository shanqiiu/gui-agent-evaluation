"""Tests for Module B — Checkpoint Verifier.

Covers:
    1. Model serialization (to_dict / from_dict)
    2. Single checkpoint verification — mock mode
    3. Heuristic fallback patterns (achieved / not achieved / uncertain)
    4. Empty images → uncertain
    5. VLM response parsing (various formats)
    6. Confidence threshold application
    7. Batch verification + report building
    8. Payload integration (verify_from_payload)
    9. Edge cases (empty checkpoints, malformed JSON, zero steps)
"""

from __future__ import annotations

import json
import pytest

from src.verifier.models import (
    Checkpoint,
    CheckpointResult,
    VerificationReport,
    VerifierConfig,
)
from src.verifier.verifier import CheckpointVerifier


# ═══════════════════════════════════════════════════════════════════
# Test data helpers
# ═══════════════════════════════════════════════════════════════════

def make_checkpoint(
    name: str = "点击隐私和安全",
    expected_state: str = "进入隐私设置页面",
    required: bool = True,
    preconditions: str = "已进入设置首页",
) -> Checkpoint:
    return Checkpoint(
        name=name,
        required=required,
        preconditions=preconditions,
        expected_state=expected_state,
        checkpoint_id="cp_001",
    )


def make_mock_config(**kwargs) -> VerifierConfig:
    """Create a VerifierConfig with mock_mode enabled."""
    return VerifierConfig(mock_mode=True, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# 1. Model serialization
# ═══════════════════════════════════════════════════════════════════

class TestCheckpointModel:
    """Test Checkpoint dataclass serialization."""

    def test_to_dict_fully_populated(self):
        cp = Checkpoint(
            name="点击搜索",
            required=True,
            preconditions="已进入首页",
            expected_state="显示搜索结果列表",
            checkpoint_id="cp_002",
        )
        d = cp.to_dict()
        assert d["name"] == "点击搜索"
        assert d["required"] is True
        assert d["preconditions"] == "已进入首页"
        assert d["expected_state"] == "显示搜索结果列表"
        assert d["checkpoint_id"] == "cp_002"

    def test_to_dict_defaults(self):
        cp = Checkpoint(name="test", required=False)
        d = cp.to_dict()
        assert d["name"] == "test"
        assert d["required"] is False
        assert d["preconditions"] == ""
        assert d["expected_state"] == ""

    def test_from_dict_full(self):
        d = {
            "name": "输入关键词",
            "required": False,
            "preconditions": "搜索框已可见",
            "expected_state": "搜索框显示输入内容",
            "checkpoint_id": "cp_003",
        }
        cp = Checkpoint.from_dict(d)
        assert cp.name == "输入关键词"
        assert cp.required is False
        assert cp.preconditions == "搜索框已可见"

    def test_from_dict_partial(self):
        d = {"name": "提交订单"}
        cp = Checkpoint.from_dict(d)
        assert cp.name == "提交订单"
        assert cp.required is True  # default
        assert cp.preconditions == ""

    def test_roundtrip(self):
        cp = make_checkpoint()
        d = cp.to_dict()
        cp2 = Checkpoint.from_dict(d)
        assert cp2.name == cp.name
        assert cp2.required == cp.required
        assert cp2.expected_state == cp.expected_state


class TestCheckpointResultModel:
    """Test CheckpointResult serialization."""

    def test_to_dict_achieved(self):
        cp = make_checkpoint()
        result = CheckpointResult(
            checkpoint=cp,
            status="达成",
            confidence=0.92,
            evidence="页面已正确跳转到隐私设置页",
            step_index=3,
            action_description="点击: 点击隐私和安全",
            fallback=False,
        )
        d = result.to_dict()
        assert d["status"] == "达成"
        assert d["confidence"] == 0.92
        assert d["step_index"] == 3
        assert d["fallback"] is False

    def test_to_dict_uncertain_fallback(self):
        cp = make_checkpoint()
        result = CheckpointResult(
            checkpoint=cp,
            status="不确定",
            confidence=0.15,
            evidence="VLM调用失败",
            fallback=True,
        )
        d = result.to_dict()
        assert d["status"] == "不确定"
        assert d["fallback"] is True


class TestVerificationReportModel:
    """Test VerificationReport aggregation."""

    def test_build_report_empty(self):
        report = VerificationReport(
            task_uuid="test-uuid",
            instruction="测试指令",
        )
        d = report.to_dict()
        assert d["task_uuid"] == "test-uuid"
        assert d["summary"]["total_checkpoints"] == 0
        assert d["overall_status"] == "未判定"

    def test_build_report_full(self):
        cp = make_checkpoint()
        results = [
            CheckpointResult(checkpoint=cp, status="达成", confidence=0.9),
            CheckpointResult(
                checkpoint=Checkpoint(name="步骤2", required=False),
                status="未达成",
                confidence=0.7,
            ),
        ]
        report = VerificationReport(
            task_uuid="test-uuid",
            instruction="测试指令",
            results=results,
            total_checkpoints=2,
            achieved_count=1,
            not_achieved_count=1,
            required_total=1,
            required_achieved=1,
            completion_score=0.5,
            required_completion_score=1.0,
            overall_status="良好",
            model_used="qwen3-vl-8b",
            total_vlm_calls=2,
        )
        d = report.to_dict()
        assert len(d["results"]) == 2
        assert d["summary"]["total_checkpoints"] == 2
        assert d["summary"]["achieved"] == 1


# ═══════════════════════════════════════════════════════════════════
# 2. Single checkpoint verification — mock mode
# ═══════════════════════════════════════════════════════════════════

class TestSingleCheckpointVerification:
    """Test verify_checkpoint in mock/heuristic mode."""

    def test_heuristic_achieved_enter_page(self):
        verifier = CheckpointVerifier(make_mock_config())
        result = verifier.verify_checkpoint(
            checkpoint=make_checkpoint(expected_state="进入隐私设置页面"),
            action_description="click: 点击隐私和安全以进入隐私设置页面",
        )
        assert result.status == "达成"
        assert result.fallback is True
        assert result.confidence > 0.5

    def test_heuristic_achieved_submit_success(self):
        verifier = CheckpointVerifier(make_mock_config())
        result = verifier.verify_checkpoint(
            checkpoint=make_checkpoint(
                name="提交订单",
                expected_state="下单成功页面",
            ),
            action_description="click: 提交订单，下单成功",
        )
        assert result.status == "达成"
        assert "提交|保存" in result.evidence  # matched pattern

    def test_heuristic_not_achieved_error_page(self):
        verifier = CheckpointVerifier(make_mock_config())
        result = verifier.verify_checkpoint(
            checkpoint=make_checkpoint(expected_state="进入设置页"),
            action_description="当前页面显示404错误页",
        )
        assert result.status == "未达成"
        assert result.fallback is True

    def test_heuristic_not_achieved_login_page(self):
        verifier = CheckpointVerifier(make_mock_config())
        result = verifier.verify_checkpoint(
            checkpoint=make_checkpoint(expected_state="进入支付页"),
            action_description="页面跳转到登录验证页",
        )
        assert result.status == "未达成"

    def test_heuristic_uncertain_default(self):
        verifier = CheckpointVerifier(make_mock_config())
        result = verifier.verify_checkpoint(
            checkpoint=make_checkpoint(expected_state="进入设置页"),
            action_description="等待页面加载",
        )
        assert result.status == "不确定"
        assert "无法确定" in result.evidence

    def test_empty_images_returns_uncertain(self):
        verifier = CheckpointVerifier(make_mock_config())
        result = verifier.verify_checkpoint(
            checkpoint=make_checkpoint(),
            before_image_base64="",
            after_image_base64="",
            action_description="",
        )
        assert result.status == "不确定"
        assert result.fallback is True
        assert "无法确定" in result.evidence


# ═══════════════════════════════════════════════════════════════════
# 3. VLM response parsing
# ═══════════════════════════════════════════════════════════════════

class TestResponseParsing:
    """Test _parse_vlm_response with various JSON formats."""

    def test_parse_achieved_response(self):
        verifier = CheckpointVerifier(make_mock_config())
        cp = make_checkpoint()
        response = json.dumps({
            "checkpoint_achieved": True,
            "confidence": 0.92,
            "page_description": "隐私设置页面，显示密码保险箱选项",
            "thought": "操作后页面确实为隐私设置页，检查点达成",
            "mismatch_reason": "",
        }, ensure_ascii=False)
        result = verifier._parse_vlm_response(response, cp, 3, "click: 隐私和安全")
        assert result.status == "达成"
        assert result.confidence == 0.92
        assert "隐私设置页面" in result.evidence

    def test_parse_not_achieved_response(self):
        verifier = CheckpointVerifier(make_mock_config())
        cp = make_checkpoint()
        response = json.dumps({
            "checkpoint_achieved": False,
            "confidence": 0.85,
            "page_description": "仍在设置首页，未进入隐私页",
            "thought": "点击后页面未变化，可能点击了错误位置",
            "mismatch_reason": "页面未跳转，仍停留在设置首页",
        }, ensure_ascii=False)
        result = verifier._parse_vlm_response(response, cp, 3, "click: 隐私和安全")
        assert result.status == "未达成"
        assert "未进入隐私页" in result.evidence or "页面未跳转" in result.evidence

    def test_parse_response_with_json_in_markdown(self):
        """Test extracting JSON from a markdown code block."""
        verifier = CheckpointVerifier(make_mock_config())
        cp = make_checkpoint()
        response = """```json
{"checkpoint_achieved": true, "confidence": 0.88, "page_description": "test", "thought": "ok", "mismatch_reason": ""}
```
Some trailing text."""
        result = verifier._parse_vlm_response(response, cp, 1, "")
        assert result.status == "达成"
        assert result.confidence == 0.88

    def test_parse_malformed_json_fallback(self):
        """Test when response is not valid JSON at all."""
        verifier = CheckpointVerifier(make_mock_config())
        cp = make_checkpoint()
        response = "这是一段纯文本，不是JSON格式"
        result = verifier._parse_vlm_response(response, cp, 1, "")
        # Should default to uncertain
        assert result.status == "不确定"

    def test_parse_response_missing_achieved_field(self):
        """Test when JSON is valid but missing 'checkpoint_achieved'."""
        verifier = CheckpointVerifier(make_mock_config())
        cp = make_checkpoint()
        response = json.dumps({
            "confidence": 0.7,
            "thought": "不确定结果",
        })
        result = verifier._parse_vlm_response(response, cp, 1, "")
        assert result.status == "不确定"


# ═══════════════════════════════════════════════════════════════════
# 4. Confidence threshold
# ═══════════════════════════════════════════════════════════════════

class TestConfidenceThreshold:
    """Test confidence threshold application."""

    def test_high_confidence_above_threshold_stays(self):
        verifier = CheckpointVerifier(make_mock_config())
        cp = make_checkpoint()
        result = CheckpointResult(checkpoint=cp, status="达成", confidence=0.95)
        result = verifier._apply_confidence_threshold(result)
        assert result.status == "达成"

    def test_below_high_threshold_becomes_uncertain(self):
        config = make_mock_config()
        config.high_confidence_threshold = 0.8
        verifier = CheckpointVerifier(config)
        cp = make_checkpoint()
        result = CheckpointResult(checkpoint=cp, status="达成", confidence=0.7)
        result = verifier._apply_confidence_threshold(result)
        assert result.status == "不确定"

    def test_below_low_threshold_always_uncertain(self):
        config = make_mock_config()
        config.low_confidence_threshold = 0.5
        verifier = CheckpointVerifier(config)
        cp = make_checkpoint()
        result = CheckpointResult(checkpoint=cp, status="达成", confidence=0.3)
        result = verifier._apply_confidence_threshold(result)
        assert result.status == "不确定"


# ═══════════════════════════════════════════════════════════════════
# 5. Batch verification + report
# ═══════════════════════════════════════════════════════════════════

class TestBatchVerification:
    """Test verify_checkpoints and report building."""

    def test_batch_all_achieved(self):
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="进入设置首页", expected_state="设置首页"),
            Checkpoint(name="点击隐私和安全", expected_state="进入隐私设置页面"),
        ]
        step_data = [
            {
                "action_description": "进入设置首页",
                "step_index": 0,
            },
            {
                "action_description": "点击隐私和安全进入隐私设置页面",
                "step_index": 3,
            },
        ]
        report = verifier.verify_checkpoints(
            checkpoints=checkpoints,
            step_data=step_data,
            task_uuid="test-uuid",
            instruction="打开密码自动填充功能",
        )
        assert report.total_checkpoints == 2
        assert report.achieved_count == 2
        assert report.completion_score == 1.0
        assert report.overall_status == "优秀"
        assert len(report.evidence) == 2

    def test_batch_mixed_results(self):
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="进入设置首页", expected_state="设置首页"),
            Checkpoint(name="点击错误按钮", expected_state="404页面"),
            Checkpoint(name="等待加载", expected_state="加载完成"),
        ]
        step_data = [
            {"action_description": "进入设置首页"},
            {"action_description": "页面显示404错误"},
            {"action_description": "等待页面加载"},
        ]
        report = verifier.verify_checkpoints(
            checkpoints=checkpoints,
            step_data=step_data,
            task_uuid="test-uuid",
            instruction="测试",
        )
        assert report.total_checkpoints == 3
        assert report.achieved_count == 1
        assert report.not_achieved_count == 1
        assert report.uncertain_count == 1
        assert report.overall_status == "失败"  # 1/3 required achieved

    def test_batch_empty_checkpoints(self):
        verifier = CheckpointVerifier(make_mock_config())
        report = verifier.verify_checkpoints(
            checkpoints=[],
            step_data=[],
            task_uuid="test-uuid",
            instruction="测试",
        )
        assert report.total_checkpoints == 0
        assert report.completion_score == 0.0
        assert report.overall_status == "未判定"

    def test_step_data_shortfall(self):
        """If fewer step_data than checkpoints, remaining use empty defaults."""
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="cp1", expected_state="进入页面"),
            Checkpoint(name="cp2", expected_state="进入页面"),
        ]
        step_data = [{"action_description": "test"}]
        report = verifier.verify_checkpoints(
            checkpoints=checkpoints,
            step_data=step_data,
            task_uuid="test-uuid",
            instruction="",
        )
        # Both should be uncertain (second has no action_description to match)
        assert report.total_checkpoints == 2


# ═══════════════════════════════════════════════════════════════════
# 6. Payload integration
# ═══════════════════════════════════════════════════════════════════

class TestPayloadIntegration:
    """Test verify_from_payload with realistic payload data."""

    def test_verify_from_payload_even_distribution(self):
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="进入设置首页", expected_state="设置首页"),
            Checkpoint(name="点击隐私和安全", expected_state="隐私设置页"),
        ]
        payload = {
            "task_uuid": "test-uuid",
            "instruction": "打开密码自动填充功能",
            "seq_info": [
                {
                    "index": 0,
                    "image_relative_path": "img0_base64",
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "click",
                            "text": "点击设置图标",
                        }
                    },
                },
                {
                    "index": 1,
                    "image_relative_path": "img1_base64",
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "scroll",
                            "text": "向下滑动寻找隐私",
                        }
                    },
                },
                {
                    "index": 2,
                    "image_relative_path": "img2_base64",
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "click",
                            "text": "点击隐私和安全",
                        }
                    },
                },
                {
                    "index": 3,
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
        report = verifier.verify_from_payload(checkpoints, payload)
        assert report.total_checkpoints == 2
        assert report.task_uuid == "test-uuid"

    def test_verify_from_payload_with_explicit_map(self):
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="进入设置首页", expected_state="设置首页"),
        ]
        payload = {
            "instruction": "test",
            "seq_info": [
                {"index": 0, "image_relative_path": "img0",
                 "planning_output": {"parsed_action": {"action_type": "click", "text": "点击设置"}}},
                {"index": 1, "image_relative_path": "img1",
                 "planning_output": {"parsed_action": {"action_type": "finished", "text": "完成"}}},
            ],
        }
        report = verifier.verify_from_payload(
            checkpoints, payload,
            checkpoint_step_map={0: 0},
        )
        assert report.total_checkpoints == 1


# ═══════════════════════════════════════════════════════════════════
# 7. Convenience function
# ═══════════════════════════════════════════════════════════════════

class TestConvenienceFunction:
    """Test the module-level verify_checkpoints convenience function."""

    def test_convenience_function(self):
        from src.verifier import verify_checkpoints

        checkpoints = [
            Checkpoint(name="进入设置首页", expected_state="设置首页"),
        ]
        step_data = [{"action_description": "进入设置首页"}]
        report = verify_checkpoints(
            checkpoints=checkpoints,
            step_data=step_data,
            task_uuid="test-uuid",
            instruction="测试",
            config=make_mock_config(),
        )
        assert report.total_checkpoints == 1
        assert report.achieved_count == 1


# ═══════════════════════════════════════════════════════════════════
# 8. Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_all_checkpoints_required_achieved_excellent(self):
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="cp1", required=True, expected_state="进入页面"),
            Checkpoint(name="cp2", required=True, expected_state="进入页面"),
        ]
        step_data = [
            {"action_description": "进入页面"},
            {"action_description": "进入页面"},
        ]
        report = verifier.verify_checkpoints(checkpoints, step_data)
        assert report.required_total == 2
        assert report.required_achieved == 2
        assert report.overall_status == "优秀"

    def test_some_optional_not_achieved_still_good(self):
        verifier = CheckpointVerifier(make_mock_config())
        checkpoints = [
            Checkpoint(name="必需步骤", required=True, expected_state="进入页面"),
            Checkpoint(name="可选步骤", required=False, expected_state="404页面"),
        ]
        step_data = [
            {"action_description": "进入页面"},
            {"action_description": "404错误页面"},
        ]
        report = verifier.verify_checkpoints(checkpoints, step_data)
        # Required achieved, optional not
        assert report.required_achieved == 1
        assert report.completion_score == 0.5  # 1/2 overall
        assert report.required_completion_score == 1.0  # 1/1 required

    def test_single_checkpoint(self):
        verifier = CheckpointVerifier(make_mock_config())
        report = verifier.verify_checkpoints(
            checkpoints=[Checkpoint(name="唯一检查点", expected_state="进入页面")],
            step_data=[{"action_description": "进入页面"}],
        )
        assert report.total_checkpoints == 1
        assert report.achieved_count == 1
