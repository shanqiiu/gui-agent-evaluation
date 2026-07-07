#!/usr/bin/env python3
"""
将 GUI Agent 的 utg.json 数据转换为 /check_e2e 接口所需的 payload 格式。

支持两种输入模式:
  1. 原始任务目录（直接读 utg.json + catchDataTurnId*/ 截图）
  2. process_gui_end_to_end.py 预处理后的目录（读 _processed.json + 0.jpg, 1.jpg, ...）

用法:
    # 单个任务 → 输出 JSON 文件
    python convert_to_check_e2e.py <task_dir> -o payload.json

    # 直接向服务发送请求
    python convert_to_check_e2e.py <task_dir> --send http://localhost:20025

    # 批量转换
    python convert_to_check_e2e.py --batch <parent_dir> -o payloads/

映射关系:
    utg.json 字段                      →  /check_e2e 字段
    ─────────────────────────────────────────────────────────
    nodes[].title.instruction          →  instruction
    stepData[].action_type (解析)      →  seq_info[*].parsed_action.{action_type, start_box, direction}
    edges[].events[].event_str         →  seq_info[*].parsed_action.text
    node.image → catchDataTurnIdN/*.jpg →  seq_info[*].image_relative_path (base64)
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

# ── 正则 ────────────────────────────────────────────────────────
_TURN_RE = re.compile(r"catchDataTurnId(\d+)")
_ACTION_CLICK = re.compile(r"click\(\[(\d+),\s*(\d+)\]\)")
_ACTION_LONG_PRESS = re.compile(r"long_press\(\[(\d+),\s*(\d+)\]\)")
_ACTION_SCROLL = re.compile(r"(scroll|swipe|drag)\(\[(\d+),\s*(\d+)\],?\s*(\w+)?\)")
_ACTION_TYPE_EDIT = re.compile(r"(type|edit)\(")
_ACTION_CLARIFY = re.compile(r"clarify\(")
_ACTION_OPEN = re.compile(r"open\(")
_ACTION_FINISHED = re.compile(r"(finished|done|任务完成)")


# ═══════════════════════════════════════════════════════════════════
# 核心转换逻辑
# ═══════════════════════════════════════════════════════════════════

def parse_action_type(action_type_str: str) -> dict:
    """
    解析 stepData.action_type 字符串。
    不修改原始文本——action_type 使用原文（去尾部分号）。
    提取 start_box 和 direction（有则填，无则空）。
    永不返回 None。
    """
    at = action_type_str.strip().rstrip(";")
    result: dict = {"type": at, "start_box": [], "direction": ""}

    m = _ACTION_CLICK.search(at)
    if m:
        result["start_box"] = [int(m.group(1)), int(m.group(2))]
        return result

    m = _ACTION_LONG_PRESS.search(at)
    if m:
        result["start_box"] = [int(m.group(1)), int(m.group(2))]
        return result

    m = _ACTION_SCROLL.search(at)
    if m:
        result["start_box"] = [int(m.group(2)), int(m.group(3))]
        if m.group(4):
            result["direction"] = m.group(4)
        return result

    return result


def extract_turn_from_path(image_path: str) -> Optional[int]:
    """从节点 image 路径中提取 catchDataTurnId 编号。"""
    m = _TURN_RE.search(str(image_path))
    return int(m.group(1)) if m else None


def extract_step_id_from_title(title_str: str) -> Optional[int]:
    """从 node title JSON 字符串中提取 stepId（仅数字 stepId）。"""
    if not title_str:
        return None
    try:
        title = json.loads(title_str)
        sid = title.get("stepId")
        if sid is None:
            return None
        if isinstance(sid, int):
            return sid
        if isinstance(sid, str) and sid.isdigit():
            return int(sid)
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def extract_turn_from_label(label: str) -> Optional[int]:
    """从 node label 中提取 catchDataTurnId 提示。"""
    m = _TURN_RE.search(str(label))
    return int(m.group(1)) if m else None


def _parse_coord_str(coord_str: str) -> Optional[list[int]]:
    """解析 "[193, 964]" 格式的坐标字符串。"""
    nums = re.findall(r"\d+", coord_str)
    if len(nums) >= 2:
        return [int(nums[0]), int(nums[1])]
    return None


def parse_node_directives(node: dict) -> dict:
    """
    从 node.raw_item.directives 中提取动作信息。

    返回: {"action_type": str, "start_box": [x,y], "element_text": str}
    解析失败返回空 dict。
    """
    raw_item = node.get("raw_item") or {}
    directives_str = raw_item.get("directives", "")
    if not directives_str:
        return {}

    try:
        directives = json.loads(directives_str)
    except (json.JSONDecodeError, TypeError):
        return {}

    for cmd in directives:
        if not isinstance(cmd, dict):
            continue
        actions = (cmd.get("payload") or {}).get("actions") or []
        for action in actions:
            if not isinstance(action, dict):
                continue
            result: dict = {}
            act_type = action.get("action", "")
            if act_type:
                result["action_type"] = act_type
            coord_str = action.get("id", "")
            coords = _parse_coord_str(coord_str)
            if coords:
                result["start_box"] = coords
            node_info = (action.get("params") or {}).get("node") or {}
            if isinstance(node_info, dict):
                element_text = node_info.get("text", "")
                if element_text:
                    result["element_text"] = element_text
            if result:
                return result
    return {}


# ═══════════════════════════════════════════════════════════════════
# 核心映射：stepData ↔ node ↔ catchDataTurnId
# ═══════════════════════════════════════════════════════════════════

def find_matching_turn(node: dict, all_turn_dirs: dict[int, Path]) -> Optional[int]:
    """
    根据节点信息匹配对应的 catchDataTurnId。
    优先级: image 路径中的 turn > label 中的 turn > title 中的 stepId
    （与 process_gui_end_to_end.py 的 find_matching_turn 逻辑一致）
    """
    turn_from_image = extract_turn_from_path(node.get("image", ""))
    turn_from_label = extract_turn_from_label(node.get("label", ""))
    step_id = extract_step_id_from_title(node.get("title", ""))

    if turn_from_image is not None and turn_from_image in all_turn_dirs:
        return turn_from_image
    if turn_from_label is not None and turn_from_label in all_turn_dirs:
        return turn_from_label
    if step_id is not None and step_id in all_turn_dirs:
        return step_id

    return None


def build_step_turn_mapping(task_dir: Path, utg: dict) -> tuple[dict[str, Optional[int]], dict[int, str]]:
    """
    构建 stepId → catchDataTurnId 映射表，同时返回 turn_id → 原始 image URL。

    返回: (step_turn, turn_images)
      step_turn:  stepId → turn_id
      turn_images: turn_id → node.image 原始地址
    """
    # 收集所有 turn 目录
    all_turn_dirs: dict[int, Path] = {}
    for entry in sorted(task_dir.iterdir()):
        tid = extract_turn_from_path(entry.name)
        if tid is not None and entry.is_dir():
            all_turn_dirs[tid] = entry

    # node_id → turn_id, 同时记录 turn_id → image URL
    node_turn: dict = {}
    turn_images: dict[int, str] = {}
    for node in utg.get("nodes", []):
        nid = node.get("id")
        if nid is None:
            continue
        turn = find_matching_turn(node, all_turn_dirs)
        if turn is not None:
            node_turn[nid] = turn
            if isinstance(nid, int):
                node_turn[str(nid)] = turn
            elif isinstance(nid, str) and nid.isdigit():
                node_turn[int(nid)] = turn
            # 记录原始 image URL（取第一个匹配的）
            if turn not in turn_images:
                image_url = node.get("image", "")
                if image_url:
                    turn_images[turn] = image_url

    # stepId → turn_id
    mapping: dict[str, Optional[int]] = {}
    for sd in utg.get("stepData", []):
        step_id_str = str(sd.get("stepId", ""))
        sid_int = int(step_id_str) if step_id_str.isdigit() else None
        turn = None
        if sid_int is not None:
            turn = node_turn.get(sid_int)
        if turn is None:
            turn = node_turn.get(step_id_str)
        mapping[step_id_str] = turn

    return mapping, turn_images


def find_screenshot_file(task_dir: Path, turn_id: int) -> Optional[Path]:
    """在 catchDataTurnId{turn_id}/ 下找到 -origin.jpg 截图。"""
    turn_dir = task_dir / f"catchDataTurnId{turn_id}"
    if not turn_dir.is_dir():
        return None
    for f in sorted(turn_dir.iterdir()):
        if f.is_file() and "-origin" in f.name:
            return f
    return None


def get_screenshot_ref(task_dir: Path, turn_id: int, *, as_path: bool = False) -> str:
    """
    获取截图引用（raw 模式：catchDataTurnIdN/*-origin.jpg）。

    as_path=True:  返回相对路径
    as_path=False: 返回 base64 编码字符串
    """
    filepath = find_screenshot_file(task_dir, turn_id)
    if filepath is None:
        return ""
    if as_path:
        try:
            return str(filepath.relative_to(task_dir)).replace("\\", "/")
        except ValueError:
            return str(filepath).replace("\\", "/")
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode()


def resolve_image_from_url(task_dir: Path, image_url: str) -> Optional[Path]:
    """
    将 node.image REST URL 解析为 task_dir 下的本地文件路径。

    URL:  .../<task_uuid>/catchDataTurnId6/temp_image-screenshot-origin.jpg
    返回: task_dir / catchDataTurnId6 / temp_image-screenshot-origin.jpg
    """
    if not image_url:
        return None
    task_name = task_dir.name
    pos = image_url.find(task_name)
    if pos < 0:
        # 兜底: 尝试 turn ID 提取（catchDataTurnIdN 格式）
        turn_id = extract_turn_from_path(image_url)
        if turn_id is not None:
            return find_screenshot_file(task_dir, turn_id)
        return None
    relative = image_url[pos + len(task_name) + 1:]  # skip UUID and "/"
    filepath = task_dir / relative
    if filepath.is_file():
        return filepath
    # URL 中的文件名可能不同（如 -drawRect vs -origin），模糊匹配
    parent = filepath.parent
    basename = filepath.name
    if parent.is_dir():
        for f in parent.iterdir():
            if f.is_file() and "-origin" in f.name:
                return f
    return None


def screenshot_from_url(task_dir: Path, image_url: str, *, as_path: bool = False) -> str:
    """将 node.image URL 解析为本地文件，返回路径或 base64。"""
    filepath = resolve_image_from_url(task_dir, image_url)
    if filepath is None:
        return ""
    if as_path:
        try:
            return str(filepath.relative_to(task_dir)).replace("\\", "/")
        except ValueError:
            return str(filepath).replace("\\", "/")
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode()


def flat_screenshot_from_url(base_dir: Path, image_url: str, *, as_path: bool = False) -> str:
    """
    processed 模式：将 node.image URL 转为平铺文件。
    尝试 turn ID 提取 → catchDataTurnId{turn_id}.jpg。
    """
    turn_id = extract_turn_from_path(image_url)
    if turn_id is not None:
        return get_flat_screenshot_ref(base_dir, turn_id, as_path=as_path)
    # home/end 等无 turn ID 的：用 screenshot_from_url 兜底
    return screenshot_from_url(base_dir, image_url, as_path=as_path)


def get_flat_screenshot_ref(base_dir: Path, turn_id: int, *, as_path: bool = False) -> str:
    """
    获取截图引用（processed 模式：catchDataTurnId{turn_id}.jpg 平铺文件）。

    as_path=True:  返回文件名 (如 "catchDataTurnId6.jpg")
    as_path=False: 返回 base64 编码字符串
    """
    for ext in (".jpg", ".png", ".jpeg"):
        filepath = base_dir / f"catchDataTurnId{turn_id}{ext}"
        if filepath.is_file():
            if as_path:
                return filepath.name
            with open(filepath, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return ""


def _is_image_path(s: str) -> bool:
    """判断字符串是否可能是图片文件路径（而非 base64）。"""
    if not s:
        return False
    # 文件路径特征：包含扩展名、目录分隔符、或已知的目录前缀
    path_indicators = (".jpg", ".png", ".jpeg", "catchDataTurnId", "temp_image")
    return any(indicator in s.lower() for indicator in path_indicators)


def hydrate_payload(payload: dict) -> dict:
    """
    将 path-based payload 转为 base64-based payload，准备发送。
    """
    base_dir_str = payload.pop("_image_base_dir", "")
    image_base_dir = Path(base_dir_str) if base_dir_str else None

    for step in payload.get("seq_info", []):
        img = step.get("image_relative_path", "")
        if not img:
            continue
        # 已是 base64（长字符串且不像路径）→ 跳过
        if not _is_image_path(img) and len(img) > 100:
            continue
        if image_base_dir:
            full_path = image_base_dir / img
            if full_path.is_file():
                with open(full_path, "rb") as f:
                    step["image_relative_path"] = base64.b64encode(f.read()).decode()

    payload.pop("_image_mode", None)
    return payload


def extract_instruction(utg: dict) -> str:
    """从 utg.json 中提取用户任务指令。"""
    # 优先从 edges 的 title 中提取
    for edge in utg.get("edges", []):
        title_str = edge.get("title", "")
        if not title_str:
            continue
        try:
            title = json.loads(title_str) if isinstance(title_str, str) else title_str
            inst = title.get("instruction", "")
            if inst:
                return inst
        except (json.JSONDecodeError, TypeError):
            continue

    # 兜底：从第一个 node 的 title 提取
    for node in utg.get("nodes", []):
        title_str = node.get("title", "")
        if not title_str:
            continue
        try:
            title = json.loads(title_str) if isinstance(title_str, str) else title_str
            inst = title.get("instruction", "")
            if inst:
                return inst
        except (json.JSONDecodeError, TypeError):
            continue

    return ""


def extract_event_text(edge: dict) -> str:
    """
    从 edge 的 events 中提取动作描述文本。

    只解析 event_type JSON 获取结构化信息（nodeText + type）。
    event_str 存储的是任务指令或其他不准确文本，不采用。
    """
    for event in edge.get("events", []):
        et_str = event.get("event_type", "")
        if not et_str:
            continue
        try:
            et = json.loads(et_str)
            if isinstance(et, list) and et:
                et = et[0]
            if isinstance(et, dict):
                action_type = str(et.get("type", "")).lower()
                node_text = str(et.get("nodeText", "")).strip()
                set_text = str(et.get("setText", "")).strip()

                if node_text:
                    if "click" in action_type or "long_press" in action_type:
                        return f"点击{node_text}"
                    return node_text
                if set_text and "clarify" in action_type:
                    return f"需手动操作: {set_text}"
                if "scroll" in action_type:
                    return "滑动屏幕"
                if "edit" in action_type or "type" in action_type:
                    return "输入文本"
                if action_type:
                    return action_type
        except (json.JSONDecodeError, TypeError):
            continue

    return ""


def step_action_to_text(action: dict) -> str:
    """将已解析的 action 转为可读文本。优先使用 directives 中的元素文本。"""
    at = action["type"]
    direction = action.get("direction", "")
    start_box = action.get("start_box", [])
    element_text = action.get("element_text", "")

    at_lower = at.lower()
    if "click" in at_lower:
        if element_text:
            return f"点击{element_text}"
        if start_box and len(start_box) >= 2:
            return f"点击({start_box[0]},{start_box[1]})"
        return "点击"
    if "long_press" in at_lower:
        if element_text:
            return f"长按{element_text}"
        if start_box and len(start_box) >= 2:
            return f"长按({start_box[0]},{start_box[1]})"
        return "长按"
    if any(kw in at_lower for kw in ("scroll", "swipe", "drag")):
        dir_map = {"down": "向下滑动", "up": "向上滑动", "left": "向左滑动", "right": "向右滑动"}
        if direction:
            return dir_map.get(direction, f"向{direction}滑动")
        return "滑动"
    if any(kw in at_lower for kw in ("type", "edit")):
        return "输入文本"
    if "clarify" in at_lower:
        return "需手动操作"
    if "open" in at_lower:
        return "打开应用"
    if any(kw in at_lower for kw in ("finished", "done")):
        return "任务完成"
    # 兜底：用原文本身
    return at


def build_node_index(utg: dict) -> dict:
    """构建 node id → node 的索引（同时支持字符串和整数 key）。"""
    index: dict = {}
    for node in utg.get("nodes", []):
        nid = node.get("id")
        index[nid] = node
        if isinstance(nid, int):
            index[str(nid)] = node
        elif isinstance(nid, str) and nid.isdigit():
            index[int(nid)] = node
    return index


def build_edge_index(utg: dict) -> dict[str, list[dict]]:
    """构建 from_node_id → [edges] 的索引。"""
    index: dict = {}
    for edge in utg.get("edges", []):
        from_id = edge.get("from")
        key = str(from_id) if from_id is not None else ""
        index.setdefault(key, []).append(edge)
    return index


def build_edge_to_index(utg: dict) -> dict[str, list[dict]]:
    """构建 to_node_id → [edges] 的索引。

    边 (from=A, to=B) 描述从 A 到 B 的动作。
    用 to=B 作为 key 可查到"是什么动作导致了到达 B 这一步"。"""
    index: dict = {}
    for edge in utg.get("edges", []):
        to_id = edge.get("to")
        key = str(to_id) if to_id is not None else ""
        index.setdefault(key, []).append(edge)
    return index


def convert_utg_to_check_e2e(task_dir: Path, *, save_paths: bool = False) -> dict:
    """
    将单个任务目录的 utg.json 转换为 /check_e2e payload。

    save_paths=True:   image_relative_path 存相对路径（JSON 小、可读）
    save_paths=False:  image_relative_path 存 base64（可直接发 API）

    返回完整的 DataInfo，可直接作为 POST /check_e2e 的 body。
    """
    utg_path = task_dir / "utg.json"
    if not utg_path.is_file():
        raise FileNotFoundError(f"utg.json 不存在: {utg_path}")

    with open(utg_path, "r", encoding="utf-8") as f:
        utg = json.load(f)

    instruction = extract_instruction(utg)

    # node id → node 索引（用于从 directives 提取动作详情）
    node_by_id: dict = {}
    for node in utg.get("nodes", []):
        nid = node.get("id")
        if nid is not None:
            node_by_id[nid] = node
            if isinstance(nid, int):
                node_by_id[str(nid)] = node
            elif isinstance(nid, str) and nid.isdigit():
                node_by_id[int(nid)] = node

    action_steps: list[dict] = []
    for sd in utg.get("stepData", []):
        step_id = str(sd.get("stepId", ""))
        at = sd.get("action_type", "")

        node = node_by_id.get(step_id)
        if node is None and step_id.isdigit():
            node = node_by_id.get(int(step_id))
        if node is None:
            continue

        # 过滤无 raw_item.directives 的步骤（思考/反射，非 UI 操作）
        raw_item = node.get("raw_item") or {}
        directives_str = raw_item.get("directives", "")
        if not directives_str or directives_str == "{}":
            continue

        dir_info = parse_node_directives(node)
        action_type = dir_info.get("action_type") or at
        if not action_type:
            continue

        # 坐标从 directives 取，方向仍从 stepData 解析（directives 通常无 direction）
        coord_parsed = parse_action_type(at)
        parsed = {
            "type": action_type,
            "stepId": step_id,
            "cost_time": sd.get("cost_time", "0"),
            "start_box": dir_info.get("start_box", []) or coord_parsed.get("start_box", []),
            "element_text": dir_info.get("element_text", ""),
            "direction": coord_parsed.get("direction", ""),
        }
        action_steps.append(parsed)

    # node_id → 最佳可用截图 URL（自己的 image，没有则用前一个有的）
    node_images: dict = {}
    best_img = ""
    for node in utg.get("nodes", []):
        nid = node.get("id")
        if nid is None:
            continue
        own = node.get("image", "") or ""
        if own:
            best_img = own
        node_images[nid] = best_img
        if isinstance(nid, int):
            node_images[str(nid)] = best_img
        elif isinstance(nid, str) and nid.isdigit():
            node_images[int(nid)] = best_img

    seq_info: list[dict] = []
    descriptions: list[str] = []
    last_loaded = ""  # 兜底：上一步成功加载的截图路径

    for idx, action in enumerate(action_steps):
        step_id = action["stepId"]
        own_url = node_images.get(step_id, "")
        screenshot_ref, image_source = "", ""
        if own_url:
            screenshot_ref = screenshot_from_url(task_dir, own_url, as_path=save_paths)
            image_source = own_url
        # 文件不存在 → 用上一步的截图兜底
        if not screenshot_ref and last_loaded:
            screenshot_ref = last_loaded
        if screenshot_ref:
            last_loaded = screenshot_ref

        text = step_action_to_text(action)

        short_desc = text if text else action["type"]
        descriptions.append(short_desc)

        seq_info.append({
            "index": idx,
            "image_relative_path": screenshot_ref,
            "_image_source": image_source,
            "planning_output": {
                "parsed_action": {
                    "action_type": action["type"],
                    "start_box": action.get("start_box", []),
                    "end_box": action.get("end_box", []),
                    "text": text,
                    "direction": action.get("direction", ""),
                }
            },
        })

    if seq_info:
        # finished 步: 取 end 节点自己的 image
        last_screenshot, finished_source = "", ""
        end_url = node_images.get("end", "")
        if end_url:
            last_screenshot = screenshot_from_url(task_dir, end_url, as_path=save_paths)
            finished_source = end_url

        seq_info.append({
            "index": len(seq_info),
            "image_relative_path": last_screenshot,
            "_image_source": finished_source,
            "planning_output": {
                "parsed_action": {
                    "action_type": "finished",
                    "start_box": [], "end_box": [],
                    "text": "任务完成", "direction": "",
                }
            },
        })

    display_descs = descriptions[:10]
    if len(descriptions) > 10:
        display_descs.append("...")
    step_level_instruction = "→".join(display_descs) if descriptions else ""

    payload: dict = {
        "instruction": instruction,
        "step_level_instruction": step_level_instruction,
        "seq_info": seq_info,
    }

    if save_paths:
        payload["_image_base_dir"] = str(task_dir.resolve()).replace("\\", "/")
        payload["_image_mode"] = "path"

    return payload


# ═══════════════════════════════════════════════════════════════════
# 预处理模式：从 process_gui_end_to_end.py 输出转换
# ═══════════════════════════════════════════════════════════════════

def convert_processed_to_check_e2e(processed_dir: Path, *, save_paths: bool = False) -> dict:
    """
    从 process_gui_end_to_end.py 预处理后的目录转换。

    save_paths=True:   image_relative_path 存相对路径 ("0.jpg", "1.jpg", ...)
    save_paths=False:  image_relative_path 存 base64
    """
    utg_path = processed_dir / "utg.json"

    if not utg_path.is_file():
        raise FileNotFoundError(f"utg.json 不存在: {utg_path}")

    with open(utg_path, "r", encoding="utf-8") as f:
        utg = json.load(f)

    instruction = extract_instruction(utg)

    node_by_id_p: dict = {}
    for node in utg.get("nodes", []):
        nid = node.get("id")
        if nid is not None:
            node_by_id_p[nid] = node
            if isinstance(nid, int):
                node_by_id_p[str(nid)] = node
            elif isinstance(nid, str) and nid.isdigit():
                node_by_id_p[int(nid)] = node

    action_steps_raw: list[dict] = []
    for sd in utg.get("stepData", []):
        step_id = str(sd.get("stepId", ""))
        at = sd.get("action_type", "")

        node = node_by_id_p.get(step_id)
        if node is None and step_id.isdigit():
            node = node_by_id_p.get(int(step_id))
        if node is None:
            continue

        raw_item = node.get("raw_item") or {}
        directives_str = raw_item.get("directives", "")
        if not directives_str or directives_str == "{}":
            continue

        dir_info = parse_node_directives(node)
        action_type = dir_info.get("action_type") or at
        if not action_type:
            continue

        coord_parsed = parse_action_type(at)
        parsed = {
            "type": action_type,
            "stepId": step_id,
            "cost_time": sd.get("cost_time", "0"),
            "start_box": dir_info.get("start_box", []) or coord_parsed.get("start_box", []),
            "element_text": dir_info.get("element_text", ""),
            "direction": coord_parsed.get("direction", ""),
        }
        action_steps_raw.append(parsed)

    node_images_p: dict = {}
    best_img_p = ""
    for node in utg.get("nodes", []):
        nid = node.get("id")
        if nid is None:
            continue
        own = node.get("image", "") or ""
        if own:
            best_img_p = own
        node_images_p[nid] = best_img_p
        if isinstance(nid, int):
            node_images_p[str(nid)] = best_img_p
        elif isinstance(nid, str) and nid.isdigit():
            node_images_p[int(nid)] = best_img_p

    descriptions: list[str] = []
    seq_info: list[dict] = []
    last_loaded_p = ""

    for idx, action in enumerate(action_steps_raw):
        step_id = action["stepId"]
        own_url = node_images_p.get(step_id, "")
        screenshot_ref, image_source = "", ""
        if own_url:
            screenshot_ref = flat_screenshot_from_url(processed_dir, own_url, as_path=save_paths)
            image_source = own_url
        if not screenshot_ref and last_loaded_p:
            screenshot_ref = last_loaded_p
        if screenshot_ref:
            last_loaded_p = screenshot_ref

        text = step_action_to_text(action)
        descriptions.append(text if text else action["type"])

        seq_info.append({
            "index": idx,
            "image_relative_path": screenshot_ref,
            "_image_source": image_source,
            "planning_output": {
                "parsed_action": {
                    "action_type": action["type"],
                    "start_box": action.get("start_box", []),
                    "end_box": action.get("end_box", []),
                    "text": text,
                    "direction": action.get("direction", ""),
                }
            },
        })

    # finished: 取 end 节点自己的 image
    last_screenshot_p, finished_source_p = "", ""
    end_url_p = node_images_p.get("end", "")
    if end_url_p:
        last_screenshot_p = flat_screenshot_from_url(processed_dir, end_url_p, as_path=save_paths)
        finished_source_p = end_url_p

    seq_info.append({
        "index": len(seq_info),
        "image_relative_path": last_screenshot_p,
        "_image_source": finished_source_p,
        "planning_output": {
            "parsed_action": {
                "action_type": "finished",
                "start_box": [], "end_box": [],
                "text": "任务完成", "direction": "",
            }
        },
    })

    display_descs = descriptions[:10]
    if len(descriptions) > 10:
        display_descs.append("...")
    step_level_instruction = "→".join(display_descs) if descriptions else ""

    payload: dict = {
        "instruction": instruction,
        "step_level_instruction": step_level_instruction,
        "seq_info": seq_info,
    }

    if save_paths:
        payload["_image_base_dir"] = str(processed_dir.resolve()).replace("\\", "/")
        payload["_image_mode"] = "path"

    return payload


# ═══════════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════════

def _output_payload(payload: dict, output_path: str) -> str:
    """输出 payload 到文件，返回写入路径。"""
    json_str = json.dumps(payload, ensure_ascii=False, indent=2)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    # 只输出文件名，不过长
    print(f"    payload 已保存: {Path(output_path).name}")
    return output_path


def _save_result(result: dict, result_path: str):
    """保存判定结果到文件。"""
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"    result 已保存: {Path(result_path).name}")


def _send_payload(payload: dict, base_url: str, timeout: int = 300) -> dict:
    """向 /check_e2e 发送请求。自动将 path-based payload 转为 base64。"""
    import requests

    # 如果是 path-based，先转换为 base64
    payload = hydrate_payload(payload)

    url = f"{base_url.rstrip('/')}/check_e2e"
    print(f"    发送到 {url} ...")

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.ConnectionError:
        print(f"    [ERROR] 无法连接 {base_url}，请确认服务已启动")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"    [ERROR] HTTP {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)

    result = resp.json().get("check_result", {})

    ra = result.get("重复动作判定结果", "-")
    pf = result.get("规划失效判定结果", "-")

    repeated = result.get("repeated_action_result", {})
    repeated_ranges = len(repeated.get("ranges", []))

    planning = result.get("planning_failure_result", {})
    planning_events = len(planning.get("events", []))

    status_line = f"重复动作={ra}({repeated_ranges}段) 规划失效={pf}({planning_events}项)"
    if ra == "normal" and pf == "normal":
        status_line += " [OK]"
    else:
        status_line += " [ANOMALY]"
    print(f"    {status_line}")

    return result


DEFAULT_PAYLOAD_DIR = "payloads"
DEFAULT_RESULT_DIR = "results"


def main():
    parser = argparse.ArgumentParser(
        description="将 GUI Agent 数据转换为 /check_e2e payload",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单任务：输出 payload JSON
  python convert_to_check_e2e.py task_0072df9f/ -o payload.json

  # 单任务：发送 + 自动保存 payload 和结果
  python convert_to_check_e2e.py task_0072df9f/ --send http://localhost:20025

  # 批量：保存 payload → payloads/ 目录（可复用）
  python convert_to_check_e2e.py --batch reorg_output/ --processed

  # 批量：发送 + 保存 payload + 保存判定结果
  python convert_to_check_e2e.py --batch reorg_output/ --send http://localhost:20025 --processed
        """,
    )

    parser.add_argument("task_dir", nargs="?", help="单个任务目录路径")
    parser.add_argument("-o", "--output", help="输出文件路径（单任务）或目录（批量），默认 payloads/")
    parser.add_argument("--send", help="发送到 /check_e2e 服务地址（发送时自动保存 payload 和结果）")
    parser.add_argument("--batch", help="批量模式：父目录（包含多个 task_uuid/ 子目录）")
    parser.add_argument("--processed", action="store_true",
                        help="使用预处理模式（从 _processed.json + 扁平截图转换）")
    parser.add_argument("--no-save", action="store_true",
                        help="不保存 payload 和结果文件（仅当 --send 时有效）")
    args = parser.parse_args()

    if args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            print(f"[ERROR] 目录不存在: {args.batch}")
            sys.exit(1)

        # 确定输出目录
        payload_dir = Path(args.output) if args.output else Path(DEFAULT_PAYLOAD_DIR)
        result_dir = payload_dir / DEFAULT_RESULT_DIR if args.send else payload_dir
        payload_dir.mkdir(parents=True, exist_ok=True)
        if args.send and not args.no_save:
            result_dir.mkdir(parents=True, exist_ok=True)

        task_dirs = sorted(
            [d for d in batch_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda d: d.name,
        )

        success = 0
        fail = 0
        for i, td in enumerate(task_dirs):
            uuid = td.name
            print(f"[{i+1}/{len(task_dirs)}] {uuid}", end="")
            try:
                # 批量模式：始终存路径（JSON 小且可读），send 时自动 hydrate
                save_paths = not args.no_save
                if args.processed:
                    payload = convert_processed_to_check_e2e(td, save_paths=save_paths)
                else:
                    payload = convert_utg_to_check_e2e(td, save_paths=save_paths)

                # 保存 payload（除非 --no-save）
                if not args.no_save:
                    payload_path = payload_dir / f"{uuid}.json"
                    _output_payload(payload, str(payload_path))

                # 发送到判定服务
                if args.send:
                    result = _send_payload(payload, args.send)
                    if not args.no_save:
                        result_path = result_dir / f"{uuid}_result.json"
                        _save_result(result, str(result_path))

                success += 1
            except Exception as e:
                fail += 1
                print(f" FAIL: {e}")

        print(f"\n完成: 成功 {success}, 失败 {fail}")
        if not args.no_save:
            print(f"payload 目录: {payload_dir.resolve()}")
            if args.send:
                print(f"结果目录:   {result_dir.resolve()}")

    elif args.task_dir:
        task_dir = Path(args.task_dir)
        if not task_dir.is_dir():
            print(f"[ERROR] 目录不存在: {args.task_dir}")
            sys.exit(1)

        # 单任务：发送时不做路径保存（性能优先），存文件时用路径
        save_paths = bool(args.output) and not args.send
        if args.processed:
            payload = convert_processed_to_check_e2e(task_dir, save_paths=save_paths)
        else:
            payload = convert_utg_to_check_e2e(task_dir, save_paths=save_paths)

        if args.send:
            # 发送模式：自动保存 payload + result
            if not args.no_save:
                payload_path = args.output or f"{task_dir.name}.json"
                _output_payload(payload, payload_path)
            result = _send_payload(payload, args.send)
            if not args.no_save:
                result_path = args.output.replace(".json", "_result.json") if args.output else f"{task_dir.name}_result.json"
                _save_result(result, result_path)
        else:
            # 纯保存模式
            if args.output:
                _output_payload(payload, args.output)
            else:
                # 默认输出到 stdout
                print(json.dumps(payload, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
