import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repeated_action_detector import detect_repeated_actions


def _step(index, action_type="click", start_box=None, text="点击点赞按钮", direction=""):
    return {
        "index": index,
        "image_relative_path": f"image-{index}",
        "planning_output": {
            "parsed_action": {
                "action_type": action_type,
                "start_box": start_box or [100, 200],
                "end_box": [],
                "text": text,
                "direction": direction,
            }
        },
    }


def test_detects_repeated_click_without_progress():
    sample = {
        "instruction": "点赞视频",
        "step_level_instruction": "点击点赞",
        "seq_info": [
            _step(0),
            _step(1, text="再次点击点赞按钮"),
            _step(2, action_type="finished", start_box=[], text="任务完成"),
        ],
    }
    raw_result = {
        "ab_pages_result": {
            "0": {
                "label": "符合预期",
                "action_des": "点击播放页右侧点赞按钮",
                "pagea_description": "播放页，右侧有点赞按钮",
                "pageb_description": "播放页，右侧有点赞按钮",
            },
            "1": {
                "label": "无法判定",
                "action_des": "点击播放页右侧点赞按钮",
                "pagea_description": "播放页，右侧有点赞按钮",
                "pageb_description": "播放页，右侧有点赞按钮",
            },
        },
        "llm_intention_step": {},
        "vlm_intention_step": {},
    }

    result = detect_repeated_actions(sample, raw_result)

    assert result["label"] == "abnormal"
    assert result["type"] == "repeated_action"
    assert result["ranges"][0]["start_step"] == 0
    assert result["ranges"][0]["end_step"] == 1


def test_allows_same_target_when_progress_is_added():
    sample = {
        "instruction": "点赞并收藏视频",
        "step_level_instruction": "点击点赞->点击收藏",
        "seq_info": [
            _step(0, text="点击点赞按钮"),
            _step(1, text="再次点击点赞按钮"),
            _step(2, action_type="finished", start_box=[], text="任务完成"),
        ],
    }
    raw_result = {
        "ab_pages_result": {
            "0": {
                "label": "符合预期",
                "action_des": "点击播放页右侧点赞按钮",
                "pagea_description": "播放页，点赞未选中",
                "pageb_description": "播放页，点赞已选中",
            },
            "1": {
                "label": "符合预期",
                "action_des": "点击播放页右侧点赞按钮",
                "pagea_description": "播放页，点赞已选中",
                "pageb_description": "播放页，点赞已选中并出现提示",
            },
        },
        "llm_intention_step": {
            "step_1": {"label": "ok", "page_id": 0},
            "step_2": {"label": "ok", "page_id": 1},
        },
        "vlm_intention_step": {},
    }

    result = detect_repeated_actions(sample, raw_result)

    assert result["label"] == "normal"
