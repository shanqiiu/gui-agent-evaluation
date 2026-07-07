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

def parse_action_type(action_type_str: str) -> Optional[dict]:
    """
    解析 stepData.action_type 字符串，提取动作类型、坐标、方向。

    示例:
        "click([315, 918])"           → {"type": "click", "start_box": [315, 918]}
        "scroll([500, 800], down)"    → {"type": "scroll", "start_box": [500, 800], "direction": "down"}
        "clarify(当前页面需要手动操作);" → {"type": "clarify", "start_box": []}
    """
    at = action_type_str.strip().rstrip(";")

    m = _ACTION_CLICK.search(at)
    if m:
        return {"type": "click", "start_box": [int(m.group(1)), int(m.group(2))]}

    m = _ACTION_LONG_PRESS.search(at)
    if m:
        return {"type": "long_press", "start_box": [int(m.group(1)), int(m.group(2))]}

    m = _ACTION_SCROLL.search(at)
    if m:
        result: dict = {"type": "scroll", "start_box": [int(m.group(2)), int(m.group(3))]}
        if m.group(4):
            result["direction"] = m.group(4)
        return result

    if _ACTION_TYPE_EDIT.search(at):
        return {"type": "type", "start_box": []}

    if _ACTION_CLARIFY.search(at):
        return {"type": "clarify", "start_box": []}

    if _ACTION_OPEN.search(at):
        return {"type": "open_app", "start_box": []}

    if _ACTION_FINISHED.search(at):
        return {"type": "finished", "start_box": []}

    return None


def extract_turn_from_path(image_path: str) -> Optional[int]:
    """从节点 image 路径中提取 catchDataTurnId 编号。"""
    m = _TURN_RE.search(str(image_path))
    return int(m.group(1)) if m else None


def find_screenshot_file(task_dir: Path, turn_id: int) -> Optional[Path]:
    """在 catchDataTurnId{turn_id}/ 下找到 -origin.jpg 截图。"""
    turn_dir = task_dir / f"catchDataTurnId{turn_id}"
    if not turn_dir.is_dir():
        return None
    for f in sorted(turn_dir.iterdir()):
        if f.is_file() and "-origin" in f.name:
            return f
    return None


def screenshot_to_base64(task_dir: Path, turn_id: int) -> str:
    """读取截图并编码为 base64。"""
    filepath = find_screenshot_file(task_dir, turn_id)
    if filepath is None:
        return ""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode()


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
    """从 edge 的 events 中提取动作描述文本。"""
    for event in edge.get("events", []):
        event_str = event.get("event_str", "")
        if event_str:
            return event_str
        # 兜底：尝试从 event_type JSON 中提取 nodeText
        try:
            et = json.loads(event.get("event_type", "{}"))
            if isinstance(et, list) and et:
                et = et[0]
            node_text = et.get("nodeText", "") if isinstance(et, dict) else ""
            if node_text:
                return f"点击{node_text}"
        except (json.JSONDecodeError, TypeError):
            continue
    return ""


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


def convert_utg_to_check_e2e(task_dir: Path) -> dict:
    """
    将单个任务目录的 utg.json 转换为 /check_e2e payload。

    返回完整的 DataInfo，可直接作为 POST /check_e2e 的 body。
    """
    utg_path = task_dir / "utg.json"
    if not utg_path.is_file():
        raise FileNotFoundError(f"utg.json 不存在: {utg_path}")

    with open(utg_path, "r", encoding="utf-8") as f:
        utg = json.load(f)

    # ── 1. 提取 instruction ──
    instruction = extract_instruction(utg)

    # ── 2. 索引 ──
    node_index = build_node_index(utg)
    edge_index = build_edge_index(utg)

    # ── 3. 筛选实际动作步骤 ──
    # stepData 中 type="AAS" 且 action_type 可被 parse_action_type 解析
    # 的条目才是实际 UI 操作。过滤掉 thought/open_app 等非 UI 动作。
    action_steps: list[dict] = []
    for sd in utg.get("stepData", []):
        at = sd.get("action_type", "")
        parsed = parse_action_type(at)
        if parsed is None:
            continue
        # 跳过系统级或非 UI 动作（这些不适合做截图前后对比判定）
        if parsed["type"] in ("open_app", "clarify"):
            continue
        parsed["stepId"] = sd.get("stepId", "")
        parsed["cost_time"] = sd.get("cost_time", "0")
        parsed["raw_action_type"] = at
        action_steps.append(parsed)

    # ── 4. 为每个动作查找截图和描述 ──
    seq_info: list[dict] = []
    descriptions: list[str] = []
    used_turns: set = set()  # 避免重复使用同一张截图

    for idx, action in enumerate(action_steps):
        step_id = action["stepId"]
        sid_int = int(step_id) if str(step_id).isdigit() else None

        # 4a. 获取"动作执行前"的截图
        # 规则：上一个动作的 to 节点截图，或首次操作时为 home 截图
        screenshot_b64 = ""
        if idx == 0 and "home" in node_index:
            # 第一个动作：用 home 截图
            home_node = node_index["home"]
            home_turn = extract_turn_from_path(home_node.get("image", ""))
            if home_turn is not None and home_turn not in used_turns:
                screenshot_b64 = screenshot_to_base64(task_dir, home_turn)
                used_turns.add(home_turn)
        else:
            # 非首个：找 this stepId 对应的 from 节点截图
            edges_from_prev = edge_index.get(str(step_id), [])
            if edges_from_prev:
                # edge 的 from 节点就是当前动作的"before"截图
                from_id = edges_from_prev[0].get("from")
                from_node = node_index.get(from_id)
                if from_node:
                    turn = extract_turn_from_path(from_node.get("image", ""))
                    if turn is not None and turn not in used_turns:
                        screenshot_b64 = screenshot_to_base64(task_dir, turn)
                        used_turns.add(turn)
            # 兜底：直接用当前 stepId 对应的 node 截图
            if not screenshot_b64 and sid_int is not None:
                node = node_index.get(sid_int) or node_index.get(str(step_id))
                if node:
                    turn = extract_turn_from_path(node.get("image", ""))
                    if turn is not None and turn not in used_turns:
                        screenshot_b64 = screenshot_to_base64(task_dir, turn)
                        used_turns.add(turn)

        # 4b. 获取动作文本描述
        text = action.get("raw_action_type", "")
        edges_for_step = edge_index.get(str(step_id), [])
        if edges_for_step:
            event_text = extract_event_text(edges_for_step[0])
            if event_text:
                text = event_text

        # 4c. 收集描述用于 step_level_instruction
        short_desc = text if text else action["type"]
        descriptions.append(short_desc)

        seq_info.append({
            "index": idx,
            "image_relative_path": screenshot_b64,
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

    # ── 5. 追加 finished 步骤 ──
    if seq_info:
        # 最后一张截图：end 节点或最后一个步骤的截图
        last_screenshot = ""
        if "end" in node_index:
            end_turn = extract_turn_from_path(node_index["end"].get("image", ""))
            if end_turn is not None:
                last_screenshot = screenshot_to_base64(task_dir, end_turn)
        elif action_steps:
            # 用最后一个动作的 to 节点
            last_step_id = action_steps[-1]["stepId"]
            edges_for_last = edge_index.get(str(last_step_id), [])
            if edges_for_last:
                to_id = edges_for_last[0].get("to")
                to_node = node_index.get(to_id)
                if to_node:
                    turn = extract_turn_from_path(to_node.get("image", ""))
                    if turn is not None:
                        last_screenshot = screenshot_to_base64(task_dir, turn)

        seq_info.append({
            "index": len(seq_info),
            "image_relative_path": last_screenshot,
            "planning_output": {
                "parsed_action": {
                    "action_type": "finished",
                    "start_box": [],
                    "end_box": [],
                    "text": "任务完成",
                    "direction": "",
                }
            },
        })

    # ── 6. 构建 step_level_instruction ──
    # 截取前 10 个描述，超过则加省略
    display_descs = descriptions[:10]
    if len(descriptions) > 10:
        display_descs.append("...")
    step_level_instruction = "→".join(display_descs) if descriptions else ""

    return {
        "instruction": instruction,
        "step_level_instruction": step_level_instruction,
        "seq_info": seq_info,
    }


# ═══════════════════════════════════════════════════════════════════
# 预处理模式：从 process_gui_end_to_end.py 输出转换
# ═══════════════════════════════════════════════════════════════════

def convert_processed_to_check_e2e(processed_dir: Path) -> dict:
    """
    从 process_gui_end_to_end.py 预处理后的目录转换。
    目录结构: 0.jpg, 1.jpg, ..., _processed.json, utg.json
    """
    processed_path = processed_dir / "_processed.json"
    utg_path = processed_dir / "utg.json"

    if not utg_path.is_file():
        raise FileNotFoundError(f"utg.json 不存在: {utg_path}")

    with open(utg_path, "r", encoding="utf-8") as f:
        utg = json.load(f)

    instruction = extract_instruction(utg)

    # 读取 _processed.json 获取 steps
    steps: list[dict] = []
    if processed_path.is_file():
        with open(processed_path, "r", encoding="utf-8") as f:
            processed = json.load(f)
        steps = processed.get("steps", [])

    # 读取扁平化截图 (0.jpg, 1.jpg, ...)
    screenshots: list[str] = []
    img_idx = 0
    while True:
        for ext in (".jpg", ".png", ".jpeg"):
            img_path = processed_dir / f"{img_idx}{ext}"
            if img_path.is_file():
                with open(img_path, "rb") as f:
                    screenshots.append(base64.b64encode(f.read()).decode())
                break
        else:
            break
        img_idx += 1

    # 构建 action_steps，复用 convert_utg_to_check_e2e 的核心逻辑
    # 先用 utg 的 stepData 提取动作
    action_steps_raw: list[dict] = []
    for sd in utg.get("stepData", []):
        at = sd.get("action_type", "")
        parsed = parse_action_type(at)
        if parsed is None or parsed["type"] in ("open_app", "clarify"):
            continue
        parsed["stepId"] = sd.get("stepId", "")
        parsed["cost_time"] = sd.get("cost_time", "0")
        parsed["raw_action_type"] = at
        action_steps_raw.append(parsed)

    edge_index = build_edge_index(utg)
    descriptions: list[str] = []
    seq_info: list[dict] = []

    for idx, action in enumerate(action_steps_raw):
        # 截图: 从扁平化截图中按索引取
        screenshot_b64 = screenshots[idx] if idx < len(screenshots) else ""

        text = action.get("raw_action_type", "")
        edges_for_step = edge_index.get(str(action["stepId"]), [])
        if edges_for_step:
            event_text = extract_event_text(edges_for_step[0])
            if event_text:
                text = event_text

        descriptions.append(text if text else action["type"])

        seq_info.append({
            "index": idx,
            "image_relative_path": screenshot_b64,
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

    # finished
    last_screenshot = screenshots[-1] if screenshots else ""
    seq_info.append({
        "index": len(seq_info),
        "image_relative_path": last_screenshot,
        "planning_output": {
            "parsed_action": {
                "action_type": "finished",
                "start_box": [],
                "end_box": [],
                "text": "任务完成",
                "direction": "",
            }
        },
    })

    display_descs = descriptions[:10]
    if len(descriptions) > 10:
        display_descs.append("...")
    step_level_instruction = "→".join(display_descs) if descriptions else ""

    return {
        "instruction": instruction,
        "step_level_instruction": step_level_instruction,
        "seq_info": seq_info,
    }


# ═══════════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════════

def _output_payload(payload: dict, output_path: Optional[str]):
    """输出 payload 到文件或 stdout。"""
    json_str = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"已写入: {output_path}")
    else:
        print(json_str)


def _send_payload(payload: dict, base_url: str, timeout: int = 300):
    """向 /check_e2e 发送请求并打印结果。"""
    import requests

    url = f"{base_url.rstrip('/')}/check_e2e"
    print(f"发送到 {url} ...")
    print(f"  instruction: {payload['instruction']}")
    print(f"  seq_info: {len(payload['seq_info'])} 步")
    print()

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.ConnectionError:
        print(f"[ERROR] 无法连接 {base_url}，请确认服务已启动")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)

    result = resp.json().get("check_result", {})
    print("=" * 60)
    print("判定结果")
    print("=" * 60)

    ra = result.get("重复动作判定结果", "-")
    pf = result.get("规划失效判定结果", "-")
    print(f"  重复动作: {ra}")
    print(f"  规划失效: {pf}")
    print()

    repeated = result.get("repeated_action_result", {})
    if repeated.get("ranges"):
        print("  重复动作详情:")
        for r in repeated["ranges"]:
            print(f"    步骤{r['start_step']}→{r['end_step']}: {r['repeat_type']} "
                  f"({r['target']}) 置信度={r['confidence']}")

    planning = result.get("planning_failure_result", {})
    if planning.get("events"):
        print("  规划失效详情:")
        for ev in planning["events"]:
            print(f"    {ev['subtype']}, 首错步骤={ev['first_error_step']}, "
                  f"置信度={ev['confidence']}")

    # 也输出完整 JSON（可选）
    output_file = f"check_e2e_result_{os.getpid()}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="将 GUI Agent 数据转换为 /check_e2e payload",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python convert_to_check_e2e.py task_0072df9f/ -o payload.json
  python convert_to_check_e2e.py task_0072df9f/ --send http://localhost:20025
  python convert_to_check_e2e.py --batch reorg_output/ -o payloads/
  python convert_to_check_e2e.py --batch reorg_output/ --processed
        """,
    )

    parser.add_argument("task_dir", nargs="?", help="单个任务目录路径")
    parser.add_argument("-o", "--output", help="输出 JSON 文件路径（默认输出到 stdout）")
    parser.add_argument("--send", help="直接发送到 /check_e2e 服务地址")
    parser.add_argument("--batch", help="批量模式：父目录（包含多个 task_uuid/ 子目录）")
    parser.add_argument("--processed", action="store_true",
                        help="使用预处理模式（从 _processed.json + 扁平截图转换）")
    args = parser.parse_args()

    if args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            print(f"[ERROR] 目录不存在: {args.batch}")
            sys.exit(1)

        task_dirs = sorted(
            [d for d in batch_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda d: d.name,
        )

        success = 0
        fail = 0
        for i, td in enumerate(task_dirs):
            uuid = td.name
            print(f"[{i+1}/{len(task_dirs)}] {uuid} ...", end=" ")
            try:
                if args.processed:
                    payload = convert_processed_to_check_e2e(td)
                else:
                    payload = convert_utg_to_check_e2e(td)

                if args.output:
                    out_dir = Path(args.output)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{uuid}.json"
                    _output_payload(payload, str(out_path))
                elif args.send:
                    _send_payload(payload, args.send)
                else:
                    _output_payload(payload, None)

                success += 1
                print("OK")
            except Exception as e:
                fail += 1
                print(f"FAIL: {e}")

        print(f"\n完成: 成功 {success}, 失败 {fail}")

    elif args.task_dir:
        task_dir = Path(args.task_dir)
        if not task_dir.is_dir():
            print(f"[ERROR] 目录不存在: {args.task_dir}")
            sys.exit(1)

        if args.processed:
            payload = convert_processed_to_check_e2e(task_dir)
        else:
            payload = convert_utg_to_check_e2e(task_dir)

        if args.send:
            _send_payload(payload, args.send)
        else:
            _output_payload(payload, args.output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
