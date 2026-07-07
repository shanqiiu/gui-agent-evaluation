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
    build_edge_to_index,
    extract_event_text,
    _is_image_path,
    hydrate_payload,
    get_screenshot_ref,
    convert_utg_to_check_e2e,
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
    assert len(edge_idx["1"]) == 1

    to_idx = build_edge_to_index(utg)
    # edge home→1: to=1, so to_idx["1"] should have it
    assert len(to_idx["1"]) == 1
    assert to_idx["1"][0]["from"] == "home"
    # edge 1→2: to=2
    assert len(to_idx["2"]) == 1

    print("[PASS] test_build_indices")


def test_extract_event_text():
    # event_type 中有 nodeText → 优先
    edge_with_nodetext = {
        "events": [{"event_type": '{"type":"click","nodeText":"隐私和安全"}'}]
    }
    assert extract_event_text(edge_with_nodetext) == "点击隐私和安全"

    # event_type 中有 scroll → 返回"滑动屏幕"
    edge_scroll = {
        "events": [{"event_type": '{"type":"scroll custom"}'}]
    }
    assert extract_event_text(edge_scroll) == "滑动屏幕"

    # event_str 被丢弃（数据不准确），无 event_type → 返回空
    edge_bad_str = {
        "events": [{"event_str": "打开密码自动填充和保存功能", "event_type": ""}]
    }
    assert extract_event_text(edge_bad_str) == ""

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


def test_step_level_instruction_not_duplicated():
    """
    回归测试：event_str 存的是指令全文时，
    step_level_instruction 不应重复指令文本，而应使用 event_type 中的动作描述。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir)

        # 构造 utg.json：模拟 "打开密码自动填充和保存功能" 任务
        utg = {
            "nodes": [
                {"id": "home", "image": f"catchDataTurnId0/dummy.jpg", "title": "{}",
                 "raw_item": {"directives": "{}"}},
                {"id": "end", "image": f"catchDataTurnId99/dummy.jpg", "title": "{}",
                 "raw_item": {"directives": "{}"}},
            ],
            "stepData": [
                {"stepId": "6", "action_type": "click([403, 2579])", "cost_time": "3309"},
                {"stepId": "7", "action_type": "click([315, 918])", "cost_time": "3619"},
                {"stepId": "8", "action_type": "scroll([500, 800], down)", "cost_time": "3813"},
            ],
            "edges": [
                {"from": "home", "to": "6",
                 "title": json.dumps({"instruction": "打开密码自动填充和保存功能"}),
                 "events": [{"event_str": "打开密码自动填充和保存功能",
                             "event_type": '{"type":"click","nodeText":"设置图标"}'}]},
                {"from": "6", "to": "7",
                 "events": [{"event_str": "打开密码自动填充和保存功能",
                             "event_type": '{"type":"click","nodeText":"隐私和安全"}'}]},
                {"from": "7", "to": "8",
                 "events": [{"event_str": "打开密码自动填充和保存功能",
                             "event_type": '{"type":"scroll custom"}'}]},
            ],
        }

        # 写 utg.json
        with open(task_dir / "utg.json", "w", encoding="utf-8") as f:
            json.dump(utg, f, ensure_ascii=False)

        # 创建假的截图
        for turn_id in (0, 6, 7, 8, 99):
            turn_dir = task_dir / f"catchDataTurnId{turn_id}"
            turn_dir.mkdir()
            with open(turn_dir / "temp_image-screenshot-origin.jpg", "wb") as f:
                f.write(b"\xff\xd8\xff\xe0")

        payload = convert_utg_to_check_e2e(task_dir, save_paths=True)

        instruction = payload["instruction"]
        step_plan = payload["step_level_instruction"]

        assert instruction == "打开密码自动填充和保存功能", f"instruction: {instruction}"
        # 关键断言：step_level_instruction 应该包含动作描述，而非重复指令
        assert "点击设置图标" in step_plan, f"step_plan: {step_plan}"
        assert "点击隐私和安全" in step_plan, f"step_plan: {step_plan}"
        assert "滑动屏幕" in step_plan, f"step_plan: {step_plan}"
        # 不应重复指令文本
        assert step_plan.count("打开密码自动填充和保存功能") <= 1, \
            f"step_plan 不应重复指令: {step_plan}"

        # 验证 seq_info 中的 text 字段也正确
        texts = [s["planning_output"]["parsed_action"]["text"] for s in payload["seq_info"]
                 if s["planning_output"]["parsed_action"]["action_type"] != "finished"]
        assert texts[0] == "点击设置图标", f"texts[0]: {texts[0]}"
        assert texts[1] == "点击隐私和安全", f"texts[1]: {texts[1]}"
        assert texts[2] == "滑动屏幕", f"texts[2]: {texts[2]}"

    print("[PASS] test_step_level_instruction_not_duplicated")


def test_same_page_consecutive_actions():
    """
    回归测试：同一页面上连续两步操作（如连点两个按钮），
    两步应有各自的截图引用（即使指向同一张图也不应被过滤掉）。
    对应问题："操作步骤 >= catchDataTurnId 数量时，截图映射不丢步"。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir)

        utg = {
            "nodes": [
                {"id": "home", "image": "catchDataTurnId0/dummy.jpg", "title": "{}",
                 "raw_item": {"directives": "{}"}},
                # node 5 是打开 App 后的页面（两个 click 共用这个 before 截图）
                {"id": "5", "image": "catchDataTurnId5/dummy.jpg", "title": "{}",
                 "raw_item": {"directives": "{}"}},
                {"id": "6", "image": "catchDataTurnId6/dummy.jpg", "title": "{}",
                 "raw_item": {"directives": "{}"}},
                {"id": "end", "image": "catchDataTurnId99/dummy.jpg", "title": "{}",
                 "raw_item": {"directives": "{}"}},
            ],
            "stepData": [
                {"stepId": "5", "action_type": "click([100, 200])", "cost_time": "100"},
                {"stepId": "6", "action_type": "click([300, 400])", "cost_time": "200"},
            ],
            "edges": [
                {"from": "home", "to": "5",
                 "title": json.dumps({"instruction": "test"}),
                 "events": [{"event_type": '{"type":"click","nodeText":"按钮A"}',
                             "event_str": ""}]},
                {"from": "5", "to": "6",
                 "events": [{"event_type": '{"type":"click","nodeText":"按钮B"}',
                             "event_str": ""}]},
            ],
        }

        with open(task_dir / "utg.json", "w", encoding="utf-8") as f:
            json.dump(utg, f, ensure_ascii=False)

        for turn_id in (0, 5, 6, 99):
            turn_dir = task_dir / f"catchDataTurnId{turn_id}"
            turn_dir.mkdir()
            with open(turn_dir / "temp_image-screenshot-origin.jpg", "wb") as f:
                f.write(b"\xff\xd8\xff\xe0")

        payload = convert_utg_to_check_e2e(task_dir, save_paths=True)

        # 应该有 2 个动作 + 1 个 finished = 3 项
        assert len(payload["seq_info"]) == 3, f"预期 3 步, 实际 {len(payload['seq_info'])}"

        # 第 0 步 (click 按钮A): before 截图 = home (turn 0)
        s0_img = payload["seq_info"][0]["image_relative_path"]
        assert "catchDataTurnId0" in s0_img, f"step0 img: {s0_img}"

        # 第 1 步 (click 按钮B): before 截图 = node 5 (turn 5)，与 step0 不同
        # 关键：这一步在修复前会因为 used_turns 而被跳过，或查到错误的 edge
        s1_img = payload["seq_info"][1]["image_relative_path"]
        assert "catchDataTurnId5" in s1_img, f"step1 img: {s1_img}"

        # 两步的截图应该不同（不同 turn）
        assert s0_img != s1_img, "两步应有不同的 before 截图"

        # finished 步: 应有 end 截图
        s_fin_img = payload["seq_info"][2]["image_relative_path"]
        assert "catchDataTurnId99" in s_fin_img, f"finished img: {s_fin_img}"

    print("[PASS] test_same_page_consecutive_actions")


if __name__ == "__main__":
    test_parse_action_type()
    test_extract_turn_from_path()
    test_build_indices()
    test_extract_event_text()
    test_extract_instruction()
    test_is_image_path()
    test_hydrate_payload()
    test_step_level_instruction_not_duplicated()
    test_same_page_consecutive_actions()
    print("\nAll tests passed.")
