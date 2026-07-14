"""
Mock data generator for state extraction pipeline testing.

Produces realistic utg.json and clearRes-like data matching the actual
data formats documented in data/data.md and observed in real samples.

Key constraints:
- utg.json mirrors the real 400-task dataset structure
- clearRes mirrors the OCR tree format from tmp/tmp.json
- actionPurpose entries are realistic agent reasoning text
- Screenshot paths use real naming conventions
"""

from __future__ import annotations

import json
from typing import Any


# ═══════════════════════════════════════════════════════════════════
# Mock task: "打开密码自动填充和保存功能" (开屏 → 设置首页 → 隐私设置 → 密码保险箱)
# Based on real task 0072df9f from data/data.md section 10
# ═══════════════════════════════════════════════════════════════════

MOCK_TASK = {
    "uuid": "0072df9f-1234-5678-abcd-ef0123456789",
    "instruction": "打开密码自动填充和保存功能",
    "app": "com.huawei.hmos.settings",
    "screen": {"width": 1280, "height": 2832},
}

# ── utg.json mock ─────────────────────────────────────────────────

def make_mock_utg() -> dict:
    """
    Generates a realistic utg.json for the mock task.
    
    Steps follow the real task flow:
    Step1: think
    Step5: open(设置)
    Step6: scroll (找隐私)
    Step7: click(隐私和安全)
    Step8-10: scroll (找密码保险箱)
    Step11: click(密码保险箱)
    Step12: clarify (手动操作)
    end: finished
    """
    nodes = []
    step_data = []
    edges = []

    step_defs = [
        # (stepId, label, action_type, cost_ms, image_turn, directives_data)
        ("home", "home", "", 0, "home", None),
        ("1", "Step1\n<FIRST>", "用户回复(打开密码自动填充和保存功能);", 4283, "home", None),
        ("2", "Step2", "", 4345, "home", None),
        ("3", "Step3", "", 4347, "home", None),
        ("4", "Step4", "CheckAppExist", 4395, "home", None),
        ("5", "Step5", 'open("设置", restart_app=True)', 190, "catchDataTurnId1", {
            "action": "open_app",
            "params": {"node": {"text": "设置", "type": "text", "bounds": [500, 1200, 780, 1350]}},
            "points": [640, 1275],
        }),
        ("6", "Step6", "scroll([500, 800], down)", 3309, "catchDataTurnId2", {
            "action": "scroll",
            "params": {"points": [500, 2000, 500, 800]},
            "direction": "down",
        }),
        ("7", "Step7", "click([403, 2579])", 3619, "catchDataTurnId3", {
            "action": "click",
            "params": {"node": {"text": "隐私和安全", "type": "text", "bounds": [255, 2541, 553, 2617]}},
            "points": [403, 2579],
        }),
        ("8", "Step8", "scroll([500, 800], down)", 3813, "catchDataTurnId4", {
            "action": "scroll",
            "params": {"points": [640, 2200]},
            "direction": "down",
        }),
        ("9", "Step9", "scroll([500, 800], down)", 3445, "catchDataTurnId5", {
            "action": "scroll",
            "params": {"points": [640, 2150]},
            "direction": "down",
        }),
        ("10", "Step10", "scroll([500, 800], down)", 3616, "catchDataTurnId6", {
            "action": "scroll",
            "params": {"points": [640, 2100]},
            "direction": "down",
        }),
        ("11", "Step11", "click([320, 1448])", 4232, "catchDataTurnId7", {
            "action": "click",
            "params": {"node": {"text": "密码保险箱", "type": "text", "bounds": [200, 1380, 540, 1516]}},
            "points": [320, 1448],
        }),
        ("12", "Step12", "clarify(当前页面需要你手动操作);", 702, "catchDataTurnId8", {
            "action": "clarify",
            "params": {"text": "当前页面需要你手动操作"},
        }),
        ("end", "end", "finished", 0, "end", None),
    ]

    node_id = 0
    for sid, label, at, cost, turn, directives_data in step_defs:
        # Build node
        raw_directives = "{}"
        if directives_data:
            raw_directives = _build_raw_directives(directives_data)
        
        image_url = f"/rest/sha256/abc/{turn}/temp_image-screenshot-origin.jpg"

        title_obj: dict[str, Any] = {
            "instruction": MOCK_TASK["instruction"],
            "stepId": sid if sid.isdigit() else sid,
        }
        if sid in ("2", "3", "4"):
            title_obj["contexts"] = ["<99KB device context omitted>"]

        node = {
            "id": sid if sid in ("home", "end") else int(sid) if sid.isdigit() else sid,
            "label": label,
            "shape": "image" if sid in ("home", "end") else ("dot" if sid == "1" else "star"),
            "image": image_url,
            "node_type": "normal",
            "title": json.dumps(title_obj, ensure_ascii=False),
            "raw_item": {
                "directives": raw_directives,
                "originalPageInfo": "{}" if sid in ("home", "end") else '{"<UI tree omitted>"}',
            },
        }
        nodes.append(node)

        # Build stepData
        step_entry: dict[str, Any] = {
            "stepId": sid,
            "action_type": at,
            "cost_time": str(cost),
        }
        if sid not in ("home", "end", "1", "2"):
            step_entry["type"] = "AAS"
            step_entry["thought"] = "【0】"
        step_data.append(step_entry)

        # Build edges (from previous to current)
        if node_id > 0:
            prev_id = nodes[node_id - 1]["id"]
            edge = {
                "flag": "new",
                "costTime": f"{cost}ms",
                "from": prev_id,
                "to": nodes[node_id]["id"],
                "id": f"{prev_id}_{nodes[node_id]['id']}",
                "label": prev_id,
                "title": '{"instruction":"' + MOCK_TASK["instruction"] + '"}',
                "view_images": [image_url],
                "events": _build_events(at, directives_data, MOCK_TASK["instruction"]),
            }
            edges.append(edge)

        node_id += 1

    return {
        "nodes": nodes,
        "stepData": step_data,
        "edges": edges,
        "num_nodes": len(nodes),
        "num_edges": len(edges),
    }


def _build_raw_directives(data: dict | None) -> str:
    """Build a realistic directives JSON string for a single action."""
    if not data:
        return "{}"
    
    action_type = data.get("action", "click")
    params = data.get("params", {})
    points = params.get("points", data.get("points", []))  # nested or top-level

    directives = [{
        "header": {"namespace": "SimulatingOperation", "name": "ExecuteCommand"},
        "payload": {
            "jarvisSessionId": "mock-session-uuid",
            "actions": [{
                "action": action_type,
                "id": str(points) if points else "",
                "params": {
                    "node": params.get("node", {}),
                    "points": points,
                    "similarity": 0.95,
                    "localSimilarity": 0.5,
                    "enter": True,
                },
            }],
        },
    }]
    return json.dumps(directives, ensure_ascii=False)


def _build_events(action_type: str, directives_data: dict | None, instruction: str) -> list[dict]:
    """Build edge events matching real data format."""
    if not action_type:
        return []
    
    if not directives_data:
        return [{"event_id": 1, "event_type": "[]", "event_str": instruction}]

    at = directives_data.get("action", "click")
    params = directives_data.get("params", {})
    points = directives_data.get("points", [])
    node = params.get("node", {})
    direction = directives_data.get("direction", "")

    if at == "click":
        bounds = node.get("bounds", [])
        event_type_obj = {
            "type": "click",
            "id": str(points),
            "nodeText": node.get("text", ""),
            "bounds": bounds,
            "points": points,
        }
        return [{
            "event_id": 1,
            "event_type": json.dumps([event_type_obj], ensure_ascii=False),
            "event_str": f"点击{node.get('text', '页面元素')}",
        }]
    elif at == "scroll":
        event_type_obj = {
            "type": "scroll custom",
            "id": str(points) if points else "[500, 800]",
            "points": points,
        }
        return [{
            "event_id": 1,
            "event_type": json.dumps([event_type_obj], ensure_ascii=False),
            "event_str": f"向{direction}滑动",
        }]
    elif at == "clarify":
        return [{
            "event_id": 1,
            "event_type": json.dumps([{"type": "clarify", "setText": params.get("text", "")}], ensure_ascii=False),
            "event_str": params.get("text", ""),
        }]
    elif at == "open_app":
        return [{
            "event_id": 1,
            "event_type": json.dumps([{"type": 'open("设置")'}], ensure_ascii=False),
            "event_str": "打开设置应用",
        }]

    return []


# ── clearRes mock (OCR tree + actionPurpose) ──────────────────────

def make_mock_clearres() -> dict[str, Any]:
    """
    Generates a realistic clearRes.json for the mock task.
    
    Returns a dict with:
    - ocr_pages: list of OCR tree snapshots (one per stable screen)
    - action_purposes: list of Agent reasoning strings per step
    """
    action_purposes = [
        "接收用户指令并分析任务目标",
        "检查目标应用设置是否存在",
        "确认设置应用已安装，准备打开",
        "正在打开设置应用",
        "进入设置首页，向下滑动寻找隐私和安全选项",
        "点击隐私和安全，进入隐私设置页面",
        "在隐私页面中向下滑动寻找密码保险箱",
        "继续向下滑动，密码保险箱选项尚未出现",
        "密码保险箱选项已出现在屏幕中",
        "点击密码保险箱打开密码和自动填充管理",
        "该页面需要身份验证，无法自动完成，提示用户手动操作",
    ]

    # OCR tree snapshots — one per "screen state"
    # State 0: Home/launcher
    ocr_home = {
        "width": 1280, "height": 2832,
        "nodes": [
            _ocr_node("0", "layout", "", [0, 0, 1280, 2832], [
                _ocr_node("0_0", "layout", "", [50, 400, 300, 700], [
                    _ocr_node("0_0_0", "icon", "", [80, 430, 270, 650], ori_type="imageview"),
                    _ocr_node("0_0_1", "text", "设置", [60, 660, 290, 700]),
                ], [{"name": "clickable", "points": [175, 550]}]),
                _ocr_node("0_1", "layout", "", [400, 400, 650, 700], [
                    _ocr_node("0_1_0", "icon", "", [430, 430, 620, 650], ori_type="imageview"),
                    _ocr_node("0_1_1", "text", "相机", [410, 660, 640, 700]),
                ]),
            ]),
        ],
    }

    # State 1: 设置首页 (scrollable list)
    ocr_settings_home = {
        "width": 1280, "height": 2832,
        "nodes": [
            _ocr_node("0", "layout", "", [0, 0, 1280, 2832], [
                _ocr_node("0_0", "layout", "", [0, 100, 1280, 250], [
                    _ocr_node("0_0_0", "text", "搜索", [100, 120, 200, 200]),
                    _ocr_node("0_0_1", "edittext", "设置项、应用", [250, 120, 1200, 230]),
                ]),
                _ocr_node("0_1", "layout", "", [0, 250, 1280, 600], [
                    _ocr_node("0_1_0", "text", "华为账号", [80, 280, 500, 350]),
                    _ocr_node("0_1_1", "text", "云空间", [80, 380, 400, 450]),
                ]),
                _ocr_node("0_2", "layout", "", [0, 600, 1280, 950], [
                    _ocr_node("0_2_0", "text", "WLAN", [80, 630, 300, 700]),
                    _ocr_node("0_2_1", "text", "蓝牙", [80, 730, 300, 800]),
                    _ocr_node("0_2_2", "text", "移动网络", [80, 830, 400, 900]),
                ]),
                _ocr_node("0_3", "layout", "", [0, 950, 1280, 1300], [
                    _ocr_node("0_3_0", "text", "桌面和个性化", [80, 980, 500, 1050]),
                    _ocr_node("0_3_1", "text", "显示和亮度", [80, 1080, 500, 1150]),
                    _ocr_node("0_3_2", "text", "声音和振动", [80, 1180, 500, 1250]),
                ]),
            ]),
        ],
    }

    # State 2: 设置首页滚动后 (scroll reveals 隐私)
    ocr_settings_scrolled = {
        "width": 1280, "height": 2832,
        "nodes": [
            _ocr_node("0", "layout", "", [0, 0, 1280, 2832], [
                _ocr_node("0_0", "layout", "", [0, 0, 1280, 2000], [
                    _ocr_node("0_0_0", "text", "系统和更新", [80, 200, 500, 300]),
                    _ocr_node("0_0_1", "layout", "", [0, 400, 1280, 700], [
                        _ocr_node("0_0_1_0", "text", "隐私", [80, 430, 250, 550]),
                        _ocr_node("0_0_1_1", "text", "隐私和安全", [600, 430, 1200, 550]),
                    ], [{"name": "clickable", "points": [900, 490]}]),
                    _ocr_node("0_0_2", "text", "密码保险箱", [600, 600, 1200, 750]),
                    _ocr_node("0_0_3", "text", "辅助功能", [80, 800, 500, 1000]),
                ]),
            ]),
        ],
    }

    # State 3: 隐私设置页
    ocr_privacy = {
        "width": 1280, "height": 2832,
        "nodes": [
            _ocr_node("0", "layout", "", [0, 0, 1280, 2832], [
                _ocr_node("0_0", "text", "隐私", [0, 100, 1280, 250]),
                _ocr_node("0_1", "layout", "", [0, 250, 1280, 400], [
                    _ocr_node("0_1_0", "text", "权限管理", [80, 260, 500, 380]),
                ]),
                _ocr_node("0_2", "layout", "", [0, 400, 1280, 550], [
                    _ocr_node("0_2_0", "text", "位置信息", [80, 410, 500, 530]),
                ]),
            ]),
        ],
    }

    # State 4: 隐私设置页滚动后 (密码保险箱出现)
    ocr_privacy_scrolled = {
        "width": 1280, "height": 2832,
        "nodes": [
            _ocr_node("0", "layout", "", [0, 0, 1280, 2832], [
                _ocr_node("0_0", "layout", "", [0, 0, 1280, 2832], [
                    _ocr_node("0_0_0", "text", "位置信息", [80, 400, 500, 520]),
                    _ocr_node("0_0_1", "layout", "", [0, 600, 1280, 900], [
                        _ocr_node("0_0_1_0", "icon", "", [80, 620, 200, 800], ori_type="imageview"),
                        _ocr_node("0_0_1_1", "text", "密码保险箱", [250, 630, 800, 750]),
                        _ocr_node("0_0_1_2", "text", "管理保存的密码和自动填充", [250, 760, 1000, 850]),
                    ], [{"name": "clickable", "points": [500, 725]}]),
                ]),
            ]),
        ],
    }

    # State 5: 密码保险箱页面 (需要手动操作)
    ocr_password_vault = {
        "width": 1280, "height": 2832,
        "nodes": [
            _ocr_node("0", "layout", "", [0, 0, 1280, 2832], [
                _ocr_node("0_0", "text", "密码保险箱", [0, 100, 1280, 250]),
                _ocr_node("0_1", "text", "需要验证身份", [80, 400, 800, 600]),
                _ocr_node("0_2", "layout", "", [0, 800, 1280, 1000], [
                    _ocr_node("0_2_0", "text", "当前页面需要手动操作", [80, 820, 1200, 980]),
                ]),
            ]),
        ],
    }

    ocr_pages = [
        ocr_home,
        ocr_settings_home,
        ocr_settings_scrolled,
        ocr_privacy,
        ocr_privacy_scrolled,
        ocr_password_vault,
    ]

    return {
        "action_purposes": action_purposes,
        "ocr_pages": ocr_pages,
    }


def _ocr_node(
    nid: str,
    ntype: str,
    text: str,
    bounds: list[int],
    children: list[dict] | None = None,
    actions: list[dict] | None = None,
    ori_type: str = "",
) -> dict:
    """Helper to create an OCR tree node matching clearRes format."""
    result: dict[str, Any] = {
        "confidence": 0.9,
        "bounds": bounds,
        "id": nid,
        "subNodes": children or [],
        "text": text,
        "type": ntype,
        "actions": actions or [],
        "content": "",
    }
    if ori_type:
        result["oriType"] = ori_type
    return result


# ── Full mock task data ───────────────────────────────────────────

def generate_mock_task() -> dict[str, Any]:
    """
    Generate a complete mock task dataset matching real data formats.
    
    Returns:
        {
            "task_uuid": str,
            "instruction": str,
            "utg": dict,          # complete utg.json
            "clearres": dict,     # {action_purposes, ocr_pages}
            "expected_graph": dict, # expected output for validation
        }
    """
    utg = make_mock_utg()
    clearres = make_mock_clearres()
    
    return {
        "task_uuid": MOCK_TASK["uuid"],
        "instruction": MOCK_TASK["instruction"],
        "utg": utg,
        "clearres": clearres,
    }
