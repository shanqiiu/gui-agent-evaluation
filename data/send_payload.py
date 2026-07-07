#!/usr/bin/env python3
"""
将已保存的 path-based payload JSON 发送到 /check_e2e 判定服务。

自动检测 image_relative_path 是否为文件路径，按需读取截图并 base64 编码后发送。
payload 中的 _image_base_dir 指向原始截图目录。

用法:
    # 单文件发送
    python data/send_payload.py payloads/0072df9f-xxx.json --send http://localhost:20025

    # 批量发送 + 保存结果到 results/
    python data/send_payload.py payloads/ --send http://localhost:20025 -o results/

    # 将路径 payload 转为 base64 payload（不发送）
    python data/send_payload.py payloads/0072df9f-xxx.json --hydrate -o hydrated.json

前提:
    payload JSON 由 convert_to_check_e2e.py 生成（含 _image_base_dir 字段）
"""

import argparse
import base64
import json
import sys
from pathlib import Path


def _is_image_path(s: str) -> bool:
    if not s:
        return False
    path_indicators = (".jpg", ".png", ".jpeg", "catchDataTurnId", "temp_image")
    return any(indicator in s.lower() for indicator in path_indicators)


def hydrate_payload(payload: dict) -> dict:
    """将 path-based payload 转为 base64-based payload。"""
    base_dir_str = payload.pop("_image_base_dir", "")
    image_base_dir = Path(base_dir_str) if base_dir_str else None

    for step in payload.get("seq_info", []):
        img = step.get("image_relative_path", "")
        if not img:
            continue
        if not _is_image_path(img) and len(img) > 100:
            continue
        if image_base_dir:
            full_path = image_base_dir / img
            if full_path.is_file():
                with open(full_path, "rb") as f:
                    step["image_relative_path"] = base64.b64encode(f.read()).decode()

    payload.pop("_image_mode", None)
    return payload


def send_payload(payload: dict, base_url: str, timeout: int = 300) -> dict:
    """发送 payload 到 /check_e2e，返回判定结果。"""
    import requests

    url = f"{base_url.rstrip('/')}/check_e2e"
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)
    return resp.json().get("check_result", {})


def print_result(result: dict):
    """简洁打印判定结果。"""
    ra = result.get("重复动作判定结果", "-")
    pf = result.get("规划失效判定结果", "-")

    repeated = result.get("repeated_action_result", {})
    ra_ranges = len(repeated.get("ranges", []))

    planning = result.get("planning_failure_result", {})
    pf_events = len(planning.get("events", []))

    print(f"    重复动作: {ra} ({ra_ranges}段)")
    print(f"    规划失效: {pf} ({pf_events}项)")

    if ra_ranges:
        for r in repeated["ranges"]:
            print(f"      └ 步骤{r['start_step']}→{r['end_step']} {r['repeat_type']} ({r.get('target','')})")
    if pf_events:
        for ev in planning["events"]:
            print(f"      └ {ev['subtype']} 首错步骤={ev.get('first_error_step','?')}")


def main():
    parser = argparse.ArgumentParser(
        description="发送 path-based payload 到 /check_e2e 判定服务",
    )
    parser.add_argument("input", help="payload JSON 文件或目录（目录时批量发送所有 .json 文件）")
    parser.add_argument("--send", help="发送到 /check_e2e 服务地址")
    parser.add_argument("-o", "--output", help="结果输出目录（默认当前目录）")
    parser.add_argument("--hydrate", action="store_true",
                        help="仅转换为 base64 payload，不发送（需配合 -o）")
    parser.add_argument("--timeout", type=int, default=300, help="请求超时秒数")
    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_dir():
        # 批量模式
        json_files = sorted(input_path.glob("*.json"))
        if not json_files:
            print(f"[ERROR] 目录下无 JSON 文件: {input_path}")
            sys.exit(1)

        result_dir = Path(args.output) if args.output else Path("results")
        result_dir.mkdir(parents=True, exist_ok=True)

        success = 0
        for jf in json_files:
            print(f"{jf.name} ...", end=" ")
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                payload = hydrate_payload(payload)

                if args.send:
                    result = send_payload(payload, args.send, args.timeout)
                    result_path = result_dir / jf.name.replace(".json", "_result.json")
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                    print_result(result)
                else:
                    print("hydrated (no --send)")

                success += 1
            except Exception as e:
                print(f"FAIL: {e}")

        print(f"\n完成: {success}/{len(json_files)}")

    elif input_path.is_file():
        with open(input_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload = hydrate_payload(payload)

        if args.hydrate and args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"已输出 base64 payload: {args.output}")
        elif args.send:
            result = send_payload(payload, args.send, args.timeout)
            print_result(result)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"结果已保存: {args.output}")
        else:
            print("[ERROR] 需指定 --send 或 --hydrate -o")
            sys.exit(1)

    else:
        print(f"[ERROR] 路径不存在: {args.input}")
        sys.exit(1)


if __name__ == "__main__":
    main()
