"""
验证 convert_to_check_e2e.py 核心逻辑的最小测试。

可以直接运行:
    python data/test_convert_to_check_e2e.py
"""

import json
import sys
from pathlib import Path

# 确保可以导入 convert_to_check_e2e
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

from convert_to_check_e2e import (
    parse_action_type,
    extract_instruction,
    extract_turn_from_path,
    build_node_index,
    build_edge_index,
    extract_event_text,
)


def test_parse_action_type():
    """验证各种 action_type 字符串的解析。"""
    cases = [
        ("click([315, 918])",          {"type": "click", "start_box": [315, 918]}),
        ("click([100, 200])",          {"type": "click", "start_box": [100, 200]}),
        ("long_press([500, 800])",     {"type": "long_press", "start_box": [500, 800]}),
        ("scroll([500, 800], down)",   {"type": "scroll", "start_box": [500, 800], "direction": "down"}),
        ("scroll([300, 600], up)",     {"type": "scroll", "start_box": [300, 600], "direction": "up"}),
        ("swipe([200, 400], left)",    {"type": "scroll", "start_box": [200, 400], "direction": "left"}),
        ("drag([100, 200], right)",    {"type": "scroll", "start_box": [100, 200], "direction": "right"}),
        ("type(something)",            {"type": "type", "start_box": []}),
        ("edit(...)",                  {"type": "type", "start_box": []}),
        ("clarify(需要手动操作);",       {"type": "clarify", "start_box": []}),
        ("open(\"设置\", restart=True)", {"type": "open_app", "start_box": []}),
        ("用户回复(打开密码自动填充和保存功能);", None),  # 非 UI 动作
        ("", None),
    ]

    for raw, expected in cases:
        result = parse_action_type(raw)
        assert result == expected, f"\n  input:  {raw!r}\n  got:    {result}\n  expect: {expected}"
    print("[PASS] test_parse_action_type")


def test_extract_turn_from_path():
    assert extract_turn_from_path("/rest/.../catchDataTurnId6/temp_image-screenshot-origin.jpg") == 6
    assert extract_turn_from_path("catchDataTurnId12/image.jpg") == 12
    assert extract_turn_from_path("no_turn_here") is None
    print("[PASS] test_extract_turn_from_path")


def test_build_indices():
    """用 synthetic utg 验证索引构建。"""
    utg = {
        "nodes": [
            {"id": "home", "image": "catchDataTurnId0/home.jpg"},
            {"id": 1, "image": "catchDataTurnId1/screenshot.jpg"},
            {"id": "end", "image": "catchDataTurnId10/end.jpg"},
        ],
        "edges": [
            {"from": "home", "to": 1,
             "events": [{"event_str": "点击设置图标", "event_type": "{}"}]},
            {"from": 1, "to": 2,
             "events": [{"event_str": "点击隐私和安全", "event_type": '{"nodeText":"隐私和安全"}'}]},
        ],
        "stepData": [
            {"stepId": "1", "action_type": "click([315, 918])", "cost_time": "100"},
            {"stepId": "2", "action_type": "click([400, 500])", "cost_time": "200"},
        ],
    }

    node_idx = build_node_index(utg)
    assert node_idx["home"]["id"] == "home"
    assert node_idx[1]["id"] == 1
    assert node_idx["end"]["id"] == "end"

    edge_idx = build_edge_index(utg)
    assert len(edge_idx["home"]) == 1
    assert edge_idx["home"][0]["from"] == "home"
    assert len(edge_idx["1"]) == 1
    assert edge_idx["1"][0]["from"] == 1

    print("[PASS] test_build_indices")


def test_extract_event_text():
    edge_with_str = {
        "events": [{"event_str": "点击设置图标", "event_type": "{}"}]
    }
    assert extract_event_text(edge_with_str) == "点击设置图标"

    edge_with_nodetext = {
        "events": [{"event_str": "", "event_type": '{"nodeText":"隐私和安全"}'}]
    }
    assert extract_event_text(edge_with_nodetext) == "点击隐私和安全"

    edge_empty = {"events": []}
    assert extract_event_text(edge_empty) == ""

    print("[PASS] test_extract_event_text")


def test_extract_instruction():
    utg = {
        "edges": [
            {"title": json.dumps({"instruction": "打开密码自动填充和保存功能"})},
        ],
        "nodes": [],
    }
    assert extract_instruction(utg) == "打开密码自动填充和保存功能"

    # 兜底：从 node title 提取
    utg2 = {
        "edges": [],
        "nodes": [
            {"title": json.dumps({"instruction": "禁止华为账号指纹验证"})},
        ],
    }
    assert extract_instruction(utg2) == "禁止华为账号指纹验证"

    # 无 instruction
    assert extract_instruction({"nodes": [], "edges": []}) == ""
    print("[PASS] test_extract_instruction")


if __name__ == "__main__":
    test_parse_action_type()
    test_extract_turn_from_path()
    test_build_indices()
    test_extract_event_text()
    test_extract_instruction()
    print("\nAll tests passed.")
