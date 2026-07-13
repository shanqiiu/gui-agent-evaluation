#!/usr/bin/env python3
"""
GUI Agent 手机端测试数据端到端处理脚本。

整合功能:
    1. 解析 utg.json，匹配截图与步骤（原 process_gui_batch.py 能力）
    2. 将截图按 steps 顺序提取为扁平索引命名（原 organize_gui_data.py 能力）
    3. 输出重组后的任务目录

输入目录结构:
    base_dir/
    ├── <uuid-1>/
    │   ├── catchDataTurnId1/
    │   │   └── temp_image-screenshot-origin.jpg
    │   ├── catchDataTurnId2/
    │   │   └── temp_image-screenshot-origin.jpg
    │   └── utg.json
    ├── <uuid-2>/
    │   └── ...
    └── ...

输出目录结构:
    output_dir/
    ├── <uuid-1>/
    │   ├── 0.jpg          # step 0 的截图
    │   ├── 1.jpg          # step 1 的截图
    │   ├── ...
    │   ├── utg.json       # 原始 utg
    │   └── _processed.json # 解析后的 processed 数据
    ├── <uuid-2>/
    │   └── ...
    └── ...

用法:
    python process_gui_end_to_end.py <base_dir> [output_dir]

    base_dir:  原始数据目录（包含各 task_uuid/ 子目录）
    output_dir: 输出目录（可选，默认为 base_dir/reorg_output）

作者操作方式:
    python process_gui_end_to_end.py D:\\Projects\\data\\...\\e63dd288-af51-4147-9ac8-67cf73042651
"""

import json
import os
import re
import shutil
import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── 正则 ────────────────────────────────────────────────────────
_TURN_RE = re.compile(r"catchDataTurnId(\d+)")

# Unicode 字符常量（中文引号 vs 英文引号）
CQ_OPEN = "\u201c"  # "
CQ_CLOSE = "\u201d"  # "
ASCII_DQ = '"'


# ═══════════════════════════════════════════════════════════════════
# Phase 1: 解析 UTG & 提取步骤信息（原 process_gui_batch.py 逻辑）
# ═══════════════════════════════════════════════════════════════════

def extract_turn_id(dir_name: str) -> Optional[int]:
    """从目录名 catchDataTurnIdN 中提取 N"""
    m = _TURN_RE.search(dir_name)
    return int(m.group(1)) if m else None


def extract_screenshots(turn_dir: Path) -> list[str]:
    """返回 turn 目录下所有 -origin.jpg 图片文件名"""
    if not turn_dir.is_dir():
        return []
    files = sorted(
        [f for f in turn_dir.iterdir() if f.is_file() and "-origin" in f.name],
        key=lambda p: p.name,
    )
    return [f.name for f in files]


def extract_step_id_from_title(title_str: str) -> Optional[int]:
    """从 node title JSON 字符串中提取 stepId（仅数字 stepId）"""
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


def extract_turn_from_image_path(image_path: str) -> Optional[int]:
    """从 image 路径中提取 catchDataTurnId N"""
    m = _TURN_RE.search(image_path)
    return int(m.group(1)) if m else None


def _parse_coords(coords_str: str) -> list[list[int]]:
    """从坐标字符串解析出 [[x,y], [x,y], ...] 格式"""
    nums = [int(x.strip()) for x in coords_str.split(",") if x.strip().isdigit()]
    if len(nums) >= 4 and len(nums) % 2 == 0:
        return [[nums[i], nums[i + 1]] for i in range(0, len(nums), 2)]
    elif len(nums) == 2:
        return [[nums[0], nums[1]]]
    else:
        return []


def parse_directives_regex(directives_str: str) -> dict:
    """
    使用正则从 directives 字符串中提取操作信息。
    由于 directives 包含嵌套的 JSON 字符串（如 originalPageInfo），
    无法用 json.loads 直接解析，所以用正则提取。
    """
    result = {
        "description": "",
        "points": [],
        "bounds": [],
        "node_click_points": [],
        "action_names": [],
    }

    if not directives_str or not isinstance(directives_str, str):
        return result

    # --- 提取 action 名称 ---
    actions = re.findall(r'"action"\s*:\s*"([^"]+)"', directives_str)
    if actions:
        result["action_names"] = actions
        result["description"] = actions[0]

    # --- 提取 points: "points":[x1,y1] 或 "points":[x1,y1,x2,y2,...] ---
    points_strs = re.findall(r'"points"\s*:\s*\[([^\]]+)\]', directives_str)
    for ps in points_strs:
        coords = _parse_coords(ps)
        for c in coords:
            if c not in result["points"]:
                result["points"].append(c)

    # --- 提取 bounds: "bounds":[left,top,right,bottom] ---
    bounds_strs = re.findall(r'"bounds"\s*:\s*\[([^\]]+)\]', directives_str)
    for bs in bounds_strs:
        nums = [int(x.strip()) for x in bs.split(",") if x.strip().isdigit()]
        if len(nums) == 4:
            c = [nums[0], nums[1], nums[2], nums[3]]
            if c not in result["bounds"]:
                result["bounds"].append(c)

    # --- 提取 node.actions[].points ---
    node_actions_pattern = re.compile(
        r'"node"\s*:\s*\{(?:[^{}]*\{[^{}]*\}[^{}]*)*?"actions"\s*:\s*\[((?:\{(?:[^{}]*\{[^{}]*\}[^{}]*)*\})+)\]',
        re.DOTALL,
    )
    for match in node_actions_pattern.finditer(directives_str):
        actions_block = match.group(1)
        action_items = re.findall(
            r'\{\s*"name"\s*:\s*"([^"]*)"\s*,\s*"points"\s*:\s*\[([^\]]+)\]',
            actions_block,
        )
        for act_name, pts_str in action_items:
            coords = _parse_coords(pts_str)
            for c in coords:
                if len(c) == 2 and c not in result["node_click_points"]:
                    result["node_click_points"].append(c)
            if not result["description"] and act_name:
                result["description"] = act_name

    if not result["description"] and result["action_names"]:
        result["description"] = ",".join(result["action_names"])

    return result


def extract_turn_from_label(label: str) -> Optional[int]:
    """从 label 中提取 turn 提示"""
    m = _TURN_RE.search(str(label))
    return int(m.group(1)) if m else None


def find_matching_turn(node: dict, all_turn_dirs: dict[int, Path]) -> Optional[int]:
    """
    根据各种线索匹配到对应的 catchDataTurnId。
    优先级: image 路径中的 turn > label 中的 turn > stepId
    """
    step_id = extract_step_id_from_title(node.get("title", ""))
    turn_from_image = extract_turn_from_image_path(node.get("image", ""))
    turn_from_label = extract_turn_from_label(node.get("label", ""))

    if turn_from_image is not None and turn_from_image in all_turn_dirs:
        return turn_from_image
    if turn_from_label is not None and turn_from_label in all_turn_dirs:
        return turn_from_label
    if step_id is not None and step_id in all_turn_dirs:
        return step_id

    return None


def parse_task_dir(task_dir: Path) -> dict:
    """
    Phase 1: 解析单个任务目录，返回 processed 数据。
    """
    task_uuid = task_dir.name
    utg_path = task_dir / "utg.json"

    if not utg_path.is_file():
        return {"uuid": task_uuid, "status": "no_utg_json"}

    try:
        with open(utg_path, "r", encoding="utf-8") as f:
            utg_data = json.load(f)
    except Exception as e:
        return {"uuid": task_uuid, "status": "utg_parse_error", "error": str(e)}

    # 收集所有 turn 目录
    all_turn_dirs: dict[int, Path] = {}
    for entry in task_dir.iterdir():
        tid = extract_turn_id(entry.name)
        if tid is not None and entry.is_dir():
            all_turn_dirs[tid] = entry

    nodes = utg_data.get("nodes", [])
    steps = []

    for node in nodes:
        if "image" not in node:
            continue

        matching_turn = find_matching_turn(node, all_turn_dirs)
        if matching_turn is None:
            continue

        images = extract_screenshots(all_turn_dirs[matching_turn])
        step_id = extract_step_id_from_title(node.get("title", ""))
        label = node.get("label", "")

        raw_item = node.get("raw_item") or {}
        directives_str = raw_item.get("directives", "[]")
        action_info = parse_directives_regex(directives_str)

        steps.append({
            "stepId": step_id,
            "turnId": matching_turn,
            "images": images,
            "action": action_info,
            "label": label,
        })

    steps.sort(key=lambda x: x.get("stepId") or 0)

    return {
        "uuid": task_uuid,
        "status": "ok",
        "steps": steps,
    }


# ═══════════════════════════════════════════════════════════════════
# Phase 2: 截图重组 & 输出扁平目录（原 organize_gui_data.py 逻辑）
# ═══════════════════════════════════════════════════════════════════

def copy_images_from_steps(task_dir: Path, steps: list[dict], output_dir: Path) -> int:
    """
    根据 steps 中的 turnId 和 images 信息，从原始 catchDataTurnIdN/ 目录
    复制截图到 output_dir，命名为 catchDataTurnId{turn_id}.jpg。

    返回复制的截图数量。
    """
    image_index = 0

    for step in steps:
        turn_id = step.get("turnId")
        images = step.get("images", [])

        if not images or turn_id is None:
            continue

        for img_name in images:
            turn_dir = task_dir / f"catchDataTurnId{turn_id}"
            src_file = None

            if turn_dir.is_dir():
                for f in turn_dir.iterdir():
                    if f.is_file() and f.name == img_name:
                        src_file = f
                        break

            if src_file is None:
                for entry in task_dir.iterdir():
                    if entry.is_dir() and _TURN_RE.search(entry.name):
                        for f in entry.iterdir():
                            if f.is_file() and f.name == img_name:
                                src_file = f
                                break
                    if src_file:
                        break

            if src_file:
                dest_name = f"catchDataTurnId{turn_id}.jpg"
                shutil.copy2(str(src_file), str(output_dir / dest_name))
                image_index += 1

    return image_index


def process_single_task(task_dir: Path, output_dir: Path) -> Dict[str, Any]:
    """
    处理单个任务: 解析 UTG → 提取步骤 → 重组截图 → 输出目录。
    """
    task_uuid = task_dir.name
    output_task_dir = output_dir / task_uuid

    # Phase 1: 解析 processed 数据
    processed = parse_task_dir(task_dir)

    if processed.get("status") != "ok":
        return {"uuid": task_uuid, "status": "error", "steps": 0, "images": 0}

    steps = processed.get("steps", [])
    if not steps:
        return {"uuid": task_uuid, "status": "empty", "steps": 0, "images": 0}

    # 创建输出目录
    output_task_dir.mkdir(parents=True, exist_ok=True)

    # 复制 utg.json
    utg_src = task_dir / "utg.json"
    if utg_src.is_file():
        shutil.copy2(str(utg_src), str(output_task_dir / "utg.json"))

    # 复制 _processed.json（中间产物）
    with open(output_task_dir / "_processed.json", "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    # Phase 2: 复制截图并索引命名
    copied = copy_images_from_steps(task_dir, steps, output_task_dir)

    return {
        "uuid": task_uuid,
        "status": "ok",
        "steps": len(steps),
        "images": copied,
    }


# ═══════════════════════════════════════════════════════════════════
# 批量处理入口
# ═══════════════════════════════════════════════════════════════════

def process_all(base_dir: str, output_dir: Optional[str] = None) -> None:
    """批量处理所有任务目录。"""
    base = Path(base_dir)
    if not base.is_dir():
        log.error("目录不存在: %s", base_dir)
        sys.exit(1)

    if output_dir is None:
        output_dir = str(base / "reorg_output")

    output_path = Path(output_dir)

    task_dirs = sorted(
        [d for d in base.iterdir() if d.is_dir()
         and not d.name.startswith('.')
         and d.name not in (output_path.name, '__pycache__')],
        key=lambda d: d.name,
    )

    log.info("=" * 60)
    log.info("GUI Agent 数据端到端处理")
    log.info("=" * 60)
    log.info("输入目录: %s", base_dir)
    log.info("输出目录: %s", output_dir)
    log.info("找到任务数: %d", len(task_dirs))
    log.info("")

    all_results = []
    ok_count = 0
    err_count = 0
    total_steps = 0
    total_images = 0
    errors: list[Dict[str, Any]] = []   # 记录失败详情

    for i, task_dir in enumerate(task_dirs, 1):
        result = process_single_task(task_dir, output_path)
        all_results.append(result)

        if result["status"] == "ok":
            ok_count += 1
            total_steps += result["steps"]
            total_images += result["images"]
        else:
            err_count += 1
            errors.append({
                "uuid": result["uuid"],
                "status": result["status"],
            })

            if (i + 1) % 50 == 0:
                log.info("  进度: %d/%d | 成功: %d | 错误: %d", i, len(task_dirs), ok_count, err_count)

    # ── 输出失败任务日志 ──
    error_log_path = os.path.join(base_dir, "error_data_log.txt")
    with open(error_log_path, "w", encoding="utf-8") as f:
        f.write(f"=== GUI Agent 失败任务日志 ===\n")
        f.write(f"生成时间: 处理结束时自动写入\n")
        f.write(f"总任务数: {len(task_dirs)}\n")
        f.write(f"成功: {ok_count}\n")
        f.write(f"失败: {err_count}\n")
        f.write(f"\n")
        f.write(f"--- 失败任务列表 ---\n")
        for entry in errors:
            uuid_str = repr(entry["uuid"])
            f.write(f"{uuid_str}\n")
        f.write(f"\n共 {err_count} 个失败任务（纯 UUID 列表，一行一个）\n")

    log.info("失败任务日志已输出: %s", error_log_path)

# ═══════════════════════════════════════════════════════════════════
# Phase 3: UTG 去冗（structured deduplication）
# 基于 data.md 字段规范，去除与判定能力无关的冗余上下文
# ═══════════════════════════════════════════════════════════════════


def _safe_json_loads(s: str):
    """安全解析 JSON 字符串，失败返回 None"""
    if not s or s in ("{}", '""', '""'):
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_action_from_directives(raw_directives_str: str) -> list[dict]:
    """从 directives JSON 字符串中提取有效 UI 操作"""
    directives = _safe_json_loads(raw_directives_str)
    if not directives:
        return []

    actions = []
    for d in directives:
        if not isinstance(d, dict):
            continue
        header = d.get("header", {})
        namespace = header.get("namespace", "")
        name = header.get("name", "")

        if namespace == "SimulatingOperation" and name == "ExecuteCommand":
            payload = d.get("payload", {})
            action_list = payload.get("actions", [])
            for action_item in action_list:
                action_type = action_item.get("action", "")
                if action_type == "clarify":
                    actions.append({
                        "type": "clarify",
                        "message": action_item.get("params", {}).get("text", ""),
                    })
                else:
                    params = action_item.get("params", {})
                    node = params.get("node", {})
                    coord = action_item.get("id", "")
                    target_text = node.get("text", "") if node else ""
                    bounds = node.get("bounds", []) if node else []
                    actions.append({
                        "type": action_type,
                        "coords": coord,
                        "target": target_text,
                        "bounds": bounds if bounds else None,
                    })

    return actions


def _action_type_parse(action_str: str) -> dict:
    """正则解析 stepData action_type 字段"""
    click_m = re.match(r'click\((\[.*?\])\)', action_str)
    scroll_m = re.match(r'scroll\((\[.*?\]),\s*(\w+)\)', action_str)
    swipe_m = re.match(r'swipe\((\[.*?\]),\s*(\w+)\)', action_str)
    back_m = re.match(r'back\(\)', action_str, re.IGNORECASE)
    edit_m = re.match(r'edit\((\[.*?\])', action_str)

    open_q_m = re.match(r'open\("([^"]+)"(?:,|$)', action_str)
    open_nq_m = re.match(r'open\(([^"(),\s][^,)]*)\)', action_str)

    clar_q_m = re.match(r'clarify\("([^"]+)"\)', action_str)
    clar_nq_m = re.match(r'clarify\(([^),]+)\)', action_str)

    if click_m:
        return {"action_type": "click", "start_box": click_m.group(1)}
    if scroll_m:
        return {"action_type": "scroll", "start_box": scroll_m.group(1), "direction": scroll_m.group(2)}
    if swipe_m:
        return {"action_type": "swipe", "start_box": swipe_m.group(1), "direction": swipe_m.group(2)}
    if open_q_m:
        return {"action_type": "open_app", "app": open_q_m.group(1)}
    if open_nq_m:
        return {"action_type": "open_app", "app": open_nq_m.group(1)}
    if clar_q_m:
        return {"action_type": "clarify", "message": clar_q_m.group(1)}
    if clar_nq_m:
        return {"action_type": "clarify", "message": clar_nq_m.group(1)}
    if edit_m:
        return {"action_type": "edit", "start_box": edit_m.group(1)}
    if back_m:
        return {"action_type": "back"}
    if action_str == "":
        return {"action_type": "noop"}
    return {"action_type": "custom", "raw": action_str}


def _extract_action_from_event_type(event_type_str: str) -> dict:
    """从事件的 event_type JSON 字符串中提取结构化操作"""
    evt = _safe_json_loads(event_type_str)
    if not evt:
        return {}

    if isinstance(evt, list):
        evt = evt[0] if evt else {}

    event_type = evt.get("type", "")
    if not isinstance(event_type, str):
        return {}

    if event_type == "click":
        return {
            "type": "click",
            "coords": evt.get("id", ""),
            "target": evt.get("nodeText", ""),
            "bounds": evt.get("bounds"),
            "points": evt.get("points"),
        }
    elif event_type == "scroll custom":
        return {
            "type": "scroll",
            "direction": "custom",
            "points": evt.get("points"),
        }
    elif event_type == "clarify":
        return {
            "type": "clarify",
            "message": evt.get("setText", ""),
        }
    elif "open" in event_type:
        cleaned = event_type.replace(CQ_OPEN, ASCII_DQ).replace(CQ_CLOSE, ASCII_DQ)
        open_q = re.match(r'open\("([^"]+)"(?:,|$)', cleaned)
        open_nq = re.match(r'open\(([^)\s][^)]*)\)', cleaned)
        if open_q:
            return {"type": "open_app", "app": open_q.group(1)}
        if open_nq:
            return {"type": "open_app", "app": open_nq.group(1)}
        return {"type": "open_app"}

    return {}


def _dedup_nodes(nodes: list[dict]) -> list[dict]:
    """去冗后的节点列表"""
    _IMG_RE = re.compile(r'(catchDataTurnId\d+|home|end)/temp_image-screenshot-origin\.jpg')
    out = []
    for node in nodes:
        n = {
            "id": node["id"],
            "label": node.get("label", ""),
            "shape": node.get("shape", ""),
        }

        # image — 简化为关键路径
        image = node.get("image", "")
        if image:
            _img_match = _IMG_RE.search(image)
            if _img_match:
                n["image"] = _img_match.group(0)
            elif image.startswith("/rest/"):
                n["image"] = "[rest_image]"
            else:
                n["image"] = image

        # raw_item.directives → 提取 actions，去除 originalPageInfo
        raw = node.get("raw_item", {})
        raw_directives = raw.get("directives", "{}")
        if raw_directives and raw_directives not in ("{}", '""', ''):
            actions = _extract_action_from_directives(raw_directives)
            if actions:
                n["actions"] = actions

        # title → 提取 instruction + actions，去除 contexts
        title_obj = _safe_json_loads(node.get("title", ""))
        if title_obj:
            inst = title_obj.get("instruction", "")
            step_id = title_obj.get("stepId", "")
            if inst and inst.strip():
                n["instruction"] = inst.strip()
            raw_dt = title_obj.get("directives", "{}")
            if raw_dt != raw.get("directives", "{}"):
                actions = _extract_action_from_directives(raw_dt)
                if actions:
                    n["actions"] = actions

        out.append(n)
    return out


def _dedup_edges(edges: list[dict]) -> list[dict]:
    """去冗后的边列表"""
    _IMG_RE = re.compile(r'(catchDataTurnId\d+|home|end)/temp_image-screenshot-origin\.jpg')
    out = []
    for edge in edges:
        e = {
            "from": edge["from"],
            "to": edge["to"],
        }

        cost = edge.get("costTime", "")
        if cost:
            e["costTime"] = cost

        # events — 保留 event_str + 解析后的 action，去除 title/contexts
        events = edge.get("events", [])
        parsed_events = []
        for evt in events:
            pe = {"event_str": evt.get("event_str", "")}
            parsed = _extract_action_from_event_type(evt.get("event_type", ""))
            if parsed:
                pe["action"] = parsed
            parsed_events.append(pe)
        if parsed_events:
            e["events"] = parsed_events

        # view_images — 简化为关键路径
        view_imgs = edge.get("view_images", [])
        simplified = []
        for img in view_imgs:
            _img_match = _IMG_RE.search(img)
            if _img_match:
                simplified.append(_img_match.group(0))
        if simplified:
            e["view_images"] = simplified

        out.append(e)
    return out


def _dedup_stepData(step_data: list[dict]) -> list[dict]:
    """从 stepData 提取操作序列"""
    out = []
    for step in step_data:
        sid = step.get("stepId", "")
        if sid in ("home", "end"):
            continue
        action_str = step.get("action_type", "")
        parsed = _action_type_parse(action_str)
        entry = {"stepId": str(sid)}
        entry.update(parsed)
        ct = step.get("cost_time", "")
        if ct:
            entry["cost_time"] = ct
        stype = step.get("type", "")
        if stype:
            entry["type"] = stype
        out.append(entry)
    return out


def _extract_instruction(nodes: list[dict], edges: list[dict]) -> str:
    """从 nodes 或 edges title 中提取全局 instruction（去重后提至根级）"""
    for node in nodes:
        title_obj = _safe_json_loads(node.get("title", ""))
        if title_obj:
            inst = title_obj.get("instruction", "").strip()
            if inst:
                return inst
    for edge in edges:
        title_obj = _safe_json_loads(edge.get("title", ""))
        if title_obj:
            inst = title_obj.get("instruction", "").strip()
            if inst:
                return inst
    return ""


def deduplicate_utg(data: dict) -> dict:
    """
    UTG 去冗：去除与判定能力无关的冗余字段，保留结构化核心信息。

    处理:
        - nodes.title.contexts: 去除 99KB+ 设备/系统上下文
        - nodes.raw_item.originalPageInfo: 去除完整 UI Tree
        - edges.title.contexts: 同上（与 node.title 重复）
        - edges.flag/label/id: 固定值或可从 from/to 推导

    返回:
        包含 instruction / steps / nodes / edges / _meta 的去冗后数据
    """
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    step_data = data.get("stepData", [])

    instruction = _extract_instruction(nodes, edges)
    steps = _dedup_stepData(step_data)
    deduped_nodes = _dedup_nodes(nodes)
    deduped_edges = _dedup_edges(edges)

    result = {
        "instruction": instruction,
        "steps": steps,
        "nodes": deduped_nodes,
        "edges": deduped_edges,
    }

    original_size = len(json.dumps(data, ensure_ascii=False))
    output_size = len(json.dumps(result, ensure_ascii=False))
    result["_meta"] = {
        "original_size_bytes": original_size,
        "output_size_bytes": output_size,
        "compression_ratio": f"{output_size / original_size:.1%}" if original_size > 0 else "0%",
        "node_count": len(deduped_nodes),
        "edge_count": len(deduped_edges),
        "step_count": len(steps),
    }

    return result


# ── UTG 去冗集成（复用 extract_utg 模块）─────────────────────────

try:
    from extract_utg import deduplicate_utg as _extract_deduplicate
except ImportError:
    _extract_deduplicate = None


def _dedup_single_utg(task_dir: Path, output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    对单个任务的 utg.json 执行去冗。

    输出路径:
        - 如果指定 output_dir: 输出到 <output_dir>/<task_uuid>/_deduped.json
        - 否则: 输出到 <task_dir>/_deduped.json

    Returns:
        {uuid, status, original_size, output_size, compression_ratio,
         node_count, edge_count, step_count}
    """
    task_uuid = task_dir.name
    utg_path = task_dir / "utg.json"

    if not utg_path.is_file():
        return {"uuid": task_uuid, "status": "no_utg_json"}

    try:
        with open(utg_path, "r", encoding="utf-8") as f:
            utg_data = json.load(f)
    except Exception as e:
        return {"uuid": task_uuid, "status": "utg_parse_error", "error": str(e)}

    # 优先使用 extract_utg 模块的 deduplicate_utg
    deduped = _extract_deduplicate(utg_data) if _extract_deduplicate else deduplicate_utg(utg_data)

    # 确定输出路径
    if output_dir is not None:
        output_task_dir = output_dir / task_uuid
        output_task_dir.mkdir(parents=True, exist_ok=True)
        deduped_path = output_task_dir / "_deduped.json"
    else:
        deduped_path = task_dir / "_deduped.json"

    with open(deduped_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=4)

    meta = deduped.get("_meta", {})
    return {
        "uuid": task_uuid,
        "status": "ok",
        "original_size": meta.get("original_size_bytes", 0),
        "output_size": meta.get("output_size_bytes", 0),
        "compression_ratio": meta.get("compression_ratio", "0%"),
        "node_count": meta.get("node_count", 0),
        "edge_count": meta.get("edge_count", 0),
        "step_count": meta.get("step_count", 0),
    }


def batch_dedup_utg(base_dir: str, output_dir: Optional[str] = None, task_uuids: Optional[list[str]] = None) -> None:
    """
    批量 UTG 去冗。

    输入目录结构:
        base_dir/
        ├── <uuid-1>/
        │   ├── utg.json
        │   └── ...
        ├── <uuid-2>/
        │   ├── utg.json
        │   └── ...
        └── ...

    输出:
        - 如果指定 output_dir: <output_dir>/<uuid>/_deduped.json
        - 否则: base_dir 同级目录下 <uuid>/_deduped.json

    Args:
        base_dir: 包含各 uuid 子目录的路径
        output_dir: 输出目录（可选，默认: base_dir/reorg_output/<uuid>/_deduped.json）
        task_uuids: 可选，指定要处理的 uuid 列表（默认处理所有）
    """
    base = Path(base_dir)
    if not base.is_dir():
        log.error("目录不存在: %s", base_dir)
        sys.exit(1)

    # 默认输出到 base_dir/reorg_output
    if output_dir is None:
        output_dir = str(base / "reorg_output")

    output_path = Path(output_dir)

    # 收集 uuid 子目录（注意：base.iterdir() 返回相对路径，必须用 .name 拼接）
    task_dirs = sorted(
        [base / d.name for d in base.iterdir() if d.is_dir()
         and not d.name.startswith('.')
         and d.name not in ('__pycache__', 'reorg_output', 'dedup_output')],
        key=lambda d: d.name,
    )

    if task_uuids:
        task_dirs = [d for d in task_dirs if d.name in task_uuids]

    if not task_dirs:
        log.warning("未找到任何待处理的 uuid 子目录")
        return

    log.info("=" * 60)
    log.info("UTG 批量去冗")
    log.info("=" * 60)
    log.info("输入目录: %s", base_dir)
    log.info("输出目录: %s", output_dir)
    log.info("待处理任务数: %d", len(task_dirs))
    log.info("")

    ok_count = 0
    err_count = 0
    total_orig = 0
    total_out = 0
    errors: list[Dict[str, Any]] = []

    for i, task_dir in enumerate(task_dirs, 1):
        result = _dedup_single_utg(task_dir, output_path)
        status = result["status"]

        if result["status"] == "ok":
            ok_count += 1
            total_orig += result.get("original_size", 0)
            total_out += result.get("output_size", 0)
            if i % 50 == 0:
                log.info("  进度: %d/%d | 成功: %d | 失败: %d", i, len(task_dirs), ok_count, err_count)
        else:
            err_count += 1
            errors.append({"uuid": result["uuid"], "status": result["status"]})

    total_reduction = total_orig - total_out
    save_pct = f"{total_out / total_orig * 100:.1%}" if total_orig > 0 else "N/A"

    log.info("")
    log.info("=" * 60)
    log.info("===== UTG 去冗完成 =====")
    log.info("总任务数: %d", len(task_dirs))
    log.info("成功: %d | 失败: %d", ok_count, err_count)
    log.info("原始总大小: %s B", f"{total_orig:,}")
    log.info("输出总大小: %s B", f"{total_out:,}")
    log.info("节省空间: %s B (%s)", f"{total_reduction:,}", save_pct)
    if errors:
        log.info("失败日志: %d 个任务失败", err_count)
    log.info("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n用法:")
        print("  python process_gui_end_to_end.py <base_dir> [output_dir]         # 端到端处理(截图+步骤)")
        print("  python process_gui_end_to_end.py <base_dir> dedup                # 仅 UTG 去冗")
        print("\n去冗模式会将 deduped 数据写入每个 uuid 子目录下的 _deduped.json")
        sys.exit(1)

    base_dir = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else None

    if mode == "dedup":
        batch_dedup_utg(base_dir)
    else:
        output_dir = mode if mode else None
        process_all(base_dir, output_dir)
