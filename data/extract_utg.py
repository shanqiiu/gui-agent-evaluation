#!/usr/bin/env python3
"""
utg_demo.json 结构化抽取 & 去冗脚本
基于 data.md 字段规范，保留判定能力相关核心字段，去除冗余上下文。

输出结构：
{
  "instruction": "<用户指令>",
  "steps": [<从 stepData 提取的操作序列>],
  "nodes": [<精简后的节点>],
  "edges": [<精简后的边>]
}
"""

import json
import re
import sys
from pathlib import Path


def safe_json_loads(s: str):
    """安全解析 JSON 字符串，失败返回 None"""
    if not s or s in ("{}", '""', '""'):
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_action_from_directives(raw_directives_str: str) -> list[dict]:
    """从 directives JSON 字符串中提取有效 UI 操作"""
    directives = safe_json_loads(raw_directives_str)
    if not directives:
        return []

    actions = []
    for d in directives:
        if not isinstance(d, dict):
            continue
        header = d.get("header", {})
        namespace = header.get("namespace", "")
        name = header.get("name", "")

        # 只提取 ExecuteCommand 类型的动作
        if namespace == "SimulatingOperation" and name == "ExecuteCommand":
            payload = d.get("payload", {})
            jarvis_session_id = payload.get("jarvisSessionId", "")
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


def extract_action_from_event_type(event_type_str: str) -> dict:
    """从事件的 event_type JSON 字符串中提取结构化操作"""
    evt = safe_json_loads(event_type_str)
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
    elif isinstance(event_type, str) and "open" in event_type:
        # 处理 open("设置") / open(设置) 等格式
        cleaned_open = event_type.replace(CQ_OPEN, ASCII_DQ).replace(CQ_CLOSE, ASCII_DQ)
        open_q_m = re.match(r'open\("([^"]+)"(?:,|$)', cleaned_open)
        open_nq_m = re.match(r'open\(([^)\s][^)]*)\)', cleaned_open)
        if open_q_m:
            return {"type": "open_app", "app": open_q_m.group(1)}
        if open_nq_m:
            return {"type": "open_app", "app": open_nq_m.group(1)}
        return {"type": "open_app"}

    return {}


# Unicode 字符常量
CQ_OPEN = "\u201c"  # "
CQ_CLOSE = "\u201d"  # "
ASCII_DQ = '"'
ASCII_SQ = "'"


def action_type_parse(action_str: str) -> dict:
    """正则解析 stepData action_type 字段
    支持带引号和不带引号的格式：
    - click([x, y])
    - open("设置") / open(设置)
    - clarify(当前页面需要你手动操作);
    - back()
    - scroll([x, y], down)
    """
    click_m = re.match(r'click\((\[.*?\])\)', action_str)
    scroll_m = re.match(r'scroll\((\[.*?\]),\s*(\w+)\)', action_str)
    swipe_m = re.match(r'swipe\((\[.*?\]),\s*(\w+)\)', action_str)
    back_m = re.match(r'back\(\)', action_str, re.IGNORECASE)
    edit_m = re.match(r'edit\((\[.*?\])', action_str)

    # open("设置") / open("设置", ...) / open(设置)
    open_q_m = re.match(r'open\("([^"]+)"(?:,|$)', action_str)
    open_nq_m = re.match(r'open\(([^"(),\s][^,)]*)\)', action_str)

    # clarify("...") / clarify(...)
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


def extract_node_title(node: dict) -> dict | None:
    """从 node.title 字符串中提取判定所需的最小字段

    去除 contexts 中的冗余信息（settings、agentName、device info、screenMode、odid 等）
    仅保留 instruction、stepId、directives 中的操作部分
    """
    title_obj = safe_json_loads(node.get("title", ""))
    if not title_obj:
        return None

    # instruction — 用户指令（判定核心）
    instruction = title_obj.get("instruction", "")

    # stepId
    step_id = title_obj.get("stepId", "")

    # directives — 只保留 ExecuteCommand 类型
    raw_directives = title_obj.get("directives", "{}")
    # 如果 directives 和节点的 raw_item.directives 相同（常见情况），跳过重复
    if raw_directives == node.get("raw_item", {}).get("directives", "{}"):
        return {"stepId": step_id}

    actions = extract_action_from_directives(raw_directives)
    if not actions and not instruction:
        return None

    result = {"stepId": step_id}
    if instruction and instruction.strip():
        result["instruction"] = instruction.strip()
    if actions:
        result["actions"] = actions

    return result if result != {"stepId": step_id} else result


def extract_edge_title(edge: dict) -> dict | None:
    """从 edge.title 字符串中提取判定所需的最小字段"""
    title_obj = safe_json_loads(edge.get("title", ""))
    if not title_obj:
        return None

    instruction = title_obj.get("instruction", "")
    step_id = title_obj.get("stepId", "")

    result = {}
    if instruction and instruction.strip():
        result["instruction"] = instruction.strip()
    if step_id:
        result["stepId"] = step_id

    return result if result else None


def dedup_nodes(nodes: list[dict]) -> list[dict]:
    """去冗后的节点列表"""
    out = []
    for node in nodes:
        n = {
            "id": node["id"],
            "label": node.get("label", ""),
            "shape": node.get("shape", ""),
        }

        # image — 保留关键路径片段，去除完整 REST URL
        image = node.get("image", "")
        if image:
            # 提取 catchDataTurnIdN / home / end 等关键路径
            m = re.search(r'(catchDataTurnId\d+|home|end)/temp_image-screenshot-origin\.jpg', image)
            if m:
                n["image"] = m.group(0)
            elif image.startswith("/rest/"):
                n["image"] = "[rest_image]"
            else:
                n["image"] = image

        # raw_item — 只保留 directives，去除 originalPageInfo（完整 UI 树）
        raw = node.get("raw_item", {})
        raw_directives = raw.get("directives", "{}")
        if raw_directives and raw_directives not in ("{}", '""', ''):
            actions = extract_action_from_directives(raw_directives)
            if actions:
                n["actions"] = actions

        # 从 title 提取指令和操作
        title_parsed = extract_node_title(node)
        if title_parsed:
            if "instruction" in title_parsed:
                n["instruction"] = title_parsed["instruction"]
            if "actions" in title_parsed:
                n["actions"] = title_parsed["actions"]
            if "stepId" in title_parsed and "stepId" not in n:
                n["stepId"] = title_parsed["stepId"]

        out.append(n)

    return out


def dedup_edges(edges: list[dict]) -> list[dict]:
    """去冗后的边列表"""
    out = []
    for edge in edges:
        e = {
            "from": edge["from"],
            "to": edge["to"],
        }

        # costTime
        cost = edge.get("costTime", "")
        if cost:
            e["costTime"] = cost

        # events — 保留 event_str（自然语言描述）+ 解析后的 event_type
        events = edge.get("events", [])
        parsed_events = []
        for evt in events:
            pe = {"event_str": evt.get("event_str", "")}
            event_type_raw = evt.get("event_type", "")
            parsed = extract_action_from_event_type(event_type_raw)
            if parsed:
                pe["action"] = parsed
            parsed_events.append(pe)

        if parsed_events:
            e["events"] = parsed_events

        # view_images — 简化为关键路径
        view_imgs = edge.get("view_images", [])
        simplified_imgs = []
        for img in view_imgs:
            m = re.search(r'(catchDataTurnId\d+|home|end)/temp_image-screenshot-origin\.jpg', img)
            if m:
                simplified_imgs.append(m.group(0))
        if simplified_imgs:
            e["view_images"] = simplified_imgs

        out.append(e)

    return out


def dedup_stepData(step_data: list[dict]) -> list[dict]:
    """从 stepData 提取操作序列
    home/end 跳过；空 action_type 保留为 noop（表示无 UI 操作的步骤）。
    """
    out = []
    for step in step_data:
        step_id = step.get("stepId", "")

        # home 和 end 无操作，跳过
        if step_id in ("home", "end"):
            continue

        action_str = step.get("action_type", "")
        parsed = action_type_parse(action_str)
        entry = {"stepId": str(step_id)}
        entry.update(parsed)

        # cost_time
        ct = step.get("cost_time", "")
        if ct:
            entry["cost_time"] = ct

        # type — 保留 AAS 标记（agent动作类型标识）
        stype = step.get("type", "")
        if stype:
            entry["type"] = stype

        out.append(entry)

    return out


def extract_instruction(nodes: list[dict], edges: list[dict]) -> str:
    """从 nodes 或 edges 的 title 中提取全局 instruction"""
    # 优先从中间节点提取（home/end 没有 instruction）
    for node in nodes:
        title_obj = safe_json_loads(node.get("title", ""))
        if title_obj and title_obj.get("instruction", "").strip():
            return title_obj["instruction"].strip()

    # 其次从 edge title 提取
    for edge in edges:
        title_obj = safe_json_loads(edge.get("title", ""))
        if title_obj and title_obj.get("instruction", "").strip():
            return title_obj["instruction"].strip()

    return ""


def deduplicate_utg(data: dict) -> dict:
    """主去冗逻辑"""
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    step_data = data.get("stepData", [])

    # 提取全局指令
    instruction = extract_instruction(nodes, edges)

    # 去冗各部分
    steps = dedup_stepData(step_data)
    deduped_nodes = dedup_nodes(nodes)
    deduped_edges = dedup_edges(edges)

    result = {
        "instruction": instruction,
        "steps": steps,
        "nodes": deduped_nodes,
        "edges": deduped_edges,
    }

    # 统计信息
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


def deduplicate_utg_file(input_path: str | Path, output_path: str | Path | None = None) -> dict:
    """
    读取 utg.json 文件，执行去冗，写入输出文件，返回去冗结果。

    Args:
        input_path: 输入 utg.json 文件路径
        output_path: 输出路径（默认: 输入文件同目录下 [name].deduped.json）

    Returns:
        去冗后的数据 dict（含 _meta 统计信息）
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(".deduped.json")
    else:
        output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = deduplicate_utg(data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    meta = result.get("_meta", {})
    print(f"[{input_path.name}] 原始: {meta.get('original_size_bytes', 0):,} B  |  "
          f"输出: {meta.get('output_size_bytes', 0):,} B  |  "
          f"压缩: {meta.get('compression_ratio', '?')}  |  "
          f"节点: {meta.get('node_count', 0)}  边: {meta.get('edge_count', 0)}  步骤: {meta.get('step_count', 0)}")

    return result


def main():
    if len(sys.argv) < 2:
        input_path = Path(__file__).parent / "utg_demo.json"
    else:
        input_path = Path(sys.argv[1])

    deduplicate_utg_file(input_path)


if __name__ == "__main__":
    main()
