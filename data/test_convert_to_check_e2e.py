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
    _is_image_path,
    hydrate_payload,
    get_screenshot_ref,
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


def test_is_image_path():
    """验证图片路径检测逻辑。"""
    # 图片路径 → True
    assert _is_image_path("catchDataTurnId6/temp_image-screenshot-origin.jpg")
    assert _is_image_path("0.jpg")
    assert _is_image_path("screenshot.png")
    # base64 → False
    assert not _is_image_path("/9j/4AAQSkZJRgABAQEASABIAAD...")
    assert not _is_image_path("a" * 500)
    # 空字符串
    assert not _is_image_path("")
    print("[PASS] test_is_image_path")


def test_hydrate_payload():
    """验证 payload hydration: path → base64。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        img_path = base_dir / "test.jpg"
        with open(img_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c\x20\x24\x2e\x27\x20\x22\x2c\x23\x1c\x1c\x28\x37\x29\x2c\x30\x31\x34\x34\x34\x1f\x27\x39\x3d\x38\x32\x3c\x2e\x33\x34\x32\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01\x7d\x01\x02\x03\x00\x04\x11\x05\x12\x21\x31\x41\x06\x13\x51\x61\x07\x22\x71\x14\x32\x81\x91\xa1\x08\x23\x42\xb1\xc1\x15\x52\xd1\xf0\x24\x33\x62\x72\x82\x09\x0a\x16\x17\x18\x19\x1a\x25\x26\x27\x28\x29\x2a\x34\x35\x36\x37\x38\x39\x3a\x43\x44\x45\x46\x47\x48\x49\x4a\x53\x54\x55\x56\x57\x58\x59\x5a\x63\x64\x65\x66\x67\x68\x69\x6a\x73\x74\x75\x76\x77\x78\x79\x7a\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xf9\xfe\x8a\x28\xa0\x0f\xff\xd9")

        # 构造 path-based payload
        payload = {
            "instruction": "test",
            "step_level_instruction": "test",
            "_image_base_dir": str(base_dir),
            "_image_mode": "path",
            "seq_info": [
                {
                    "index": 0,
                    "image_relative_path": "test.jpg",
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "click", "start_box": [1, 2],
                            "end_box": [], "text": "test", "direction": "",
                        }
                    }
                }
            ],
        }

        # hydrate
        hydrated = hydrate_payload(payload.copy())
        # 应该变成 base64（不再是路径）
        img = hydrated["seq_info"][0]["image_relative_path"]
        assert not _is_image_path(img), f"Expected base64, got path-like: {img[:80]}..."
        assert len(img) > 100, f"Expected long base64, got len={len(img)}"
        # 不应再有 _image_base_dir
        assert "_image_base_dir" not in hydrated
        assert "_image_mode" not in hydrated

        # 验证已有 base64 的不会被重复编码
        already_b64 = payload.copy()
        already_b64["seq_info"][0]["image_relative_path"] = "a" * 500
        hydrated2 = hydrate_payload(already_b64)
        assert hydrated2["seq_info"][0]["image_relative_path"] == "a" * 500

    print("[PASS] test_hydrate_payload")


if __name__ == "__main__":
    test_parse_action_type()
    test_extract_turn_from_path()
    test_build_indices()
    test_extract_event_text()
    test_extract_instruction()
    test_is_image_path()
    test_hydrate_payload()
    print("\nAll tests passed.")
