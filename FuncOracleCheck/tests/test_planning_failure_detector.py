import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from planning_failure_detector import detect_planning_failures


def _step(index, action_type="click", text="点击"):
    return {
        "index": index,
        "image_relative_path": f"image-{index}",
        "planning_output": {
            "parsed_action": {
                "action_type": action_type,
                "start_box": [100, 200],
                "end_box": [],
                "text": text,
                "direction": "",
            }
        },
    }


def test_detects_premature_termination_with_missing_step():
    sample = {
        "instruction": "点赞并收藏视频",
        "step_level_instruction": "点击点赞->点击收藏",
        "seq_info": [
            _step(0, text="点击点赞按钮"),
            _step(1, action_type="finished", text="任务完成"),
        ],
    }
    raw_result = {
        "intention": {"label": "nok", "wrong_reason": "收藏步骤未完成"},
        "llm_intention_step": {
            "step_1": {"step": "点击点赞", "label": "ok", "page_id": 1},
            "step_2": {"step": "点击收藏", "label": "nok", "page_id": -1, "wrong_reason": "意图执行步骤未覆盖"},
        },
        "vlm_intention_step": {},
    }
    aligned_result = {
        "整体意图测试结果": "nok",
        "路径一致性测试结果": "nok",
        "Plan步骤数": 2,
        "执行覆盖Plan步骤数": 1,
        "未覆盖Plan": [{"Plan步骤名": "点击收藏", "执行结果评估依据": "没有对应的执行步骤覆盖此Plan步骤"}],
        "存在问题的功能": [],
    }

    result = detect_planning_failures(sample, raw_result, aligned_result)

    assert result["label"] == "abnormal"
    assert result["subtype"] == "premature_termination"
    assert result["missing_checkpoints"][0]["name"] == "点击收藏"


def test_detects_fail_to_terminate_after_completion():
    sample = {
        "instruction": "点赞视频",
        "step_level_instruction": "点击点赞",
        "seq_info": [
            _step(0, text="点击点赞按钮"),
            _step(1, text="重复点击页面"),
            _step(2, text="继续点击页面"),
            _step(3, text="继续点击页面"),
            _step(4, text="继续点击页面"),
            _step(5, action_type="finished", text="任务完成"),
        ],
    }
    raw_result = {
        "intention": {"label": "ok", "wrong_reason": ""},
        "llm_intention_step": {
            "step_1": {"step": "点击点赞", "label": "ok", "page_id": 1},
        },
        "vlm_intention_step": {},
    }
    aligned_result = {
        "整体意图测试结果": "ok",
        "路径一致性测试结果": "ok",
        "Plan步骤数": 1,
        "执行覆盖Plan步骤数": 1,
        "未覆盖Plan": [],
        "存在问题的功能": [],
    }
    repeated_action_result = {"label": "abnormal"}

    result = detect_planning_failures(sample, raw_result, aligned_result, repeated_action_result)

    assert result["label"] == "abnormal"
    assert result["subtype"] == "fail_to_terminate"
    assert "repeated_action" in result["related_anomalies"]


def test_does_not_classify_function_bug_only_as_planning_failure():
    sample = {
        "instruction": "点赞视频",
        "step_level_instruction": "点击点赞",
        "seq_info": [
            _step(0, text="点击点赞按钮"),
            _step(1, action_type="finished", text="任务完成"),
        ],
    }
    raw_result = {
        "intention": {"label": "nok", "wrong_reason": "点击后页面未出现点赞选中态"},
        "llm_intention_step": {
            "step_1": {"step": "点击点赞", "label": "pok", "page_id": 1, "wrong_reason": "功能bug"},
        },
        "vlm_intention_step": {},
        "llm_intention_step_identity": {"label": "pok", "wrong_steps": [], "bug_steps": ["点击点赞"]},
    }
    aligned_result = {
        "整体意图测试结果": "nok",
        "路径一致性测试结果": "pok",
        "Plan步骤数": 1,
        "执行覆盖Plan步骤数": 1,
        "未覆盖Plan": [],
        "存在问题的功能": ["点击点赞"],
    }

    result = detect_planning_failures(sample, raw_result, aligned_result)

    assert result["label"] == "normal"
    assert result["bug_steps"] == ["点击点赞"]
