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
    """从 node title JSON 字符串中提取 stepId"""
    if not title_str:
        return None
    try:
        title = json.loads(title_str)
        return title.get("stepId")
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
    复制截图到 output_dir，按顺序重命名为 0.jpg, 1.jpg, ...

    返回复制的截图数量。
    """
    image_index = 0

    for step in steps:
        turn_id = step.get("turnId")
        images = step.get("images", [])

        if not images or turn_id is None:
            continue

        for img_name in images:
            # 方法1: 直接构造路径 catchDataTurnId{turn_id}/
            turn_dir = task_dir / f"catchDataTurnId{turn_id}"
            src_file = None

            if turn_dir.is_dir():
                for f in turn_dir.iterdir():
                    if f.is_file() and f.name == img_name:
                        src_file = f
                        break

            # 方法2: 遍历所有 catchDataTurnId* 目录查找（兜底）
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
                dest_name = f"{image_index}.jpg"
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

    # 最终统计
    log.info("")
    log.info("=" * 60)
    log.info("===== 处理完成 =====")
    log.info("总任务数: %d", len(task_dirs))
    log.info("成功: %d", ok_count)
    log.info("失败: %d", err_count)
    log.info("总步骤数: %d", total_steps)
    log.info("总截图数: %d", total_images)
    log.info("失败日志: %s", error_log_path)
    log.info("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    base_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    process_all(base_dir, output_dir)
