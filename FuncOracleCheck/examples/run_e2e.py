"""
/check_e2e 完整调用示例 — 含重复动作与规划失效判定

用法:
    # 使用真实截图
    python examples/run_e2e.py --image-dir screenshots/

    # 使用自动生成的占位图（验证链路，但模型判定不准）
    python examples/run_e2e.py --dummy

    # 指定服务地址
    python examples/run_e2e.py --image-dir screenshots/ --base-url http://remote:20025

前提: uvicorn main:app --host 0.0.0.0 --port 20025 已启动
"""

import argparse
import base64
import json
import os
import struct
import sys
import zlib
from pathlib import Path


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def png_bytes(width: int, height: int, r: int, g: int, b: int) -> bytes:
    """生成最小合法 PNG（纯色块），用于占位测试。"""

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        payload = chunk_type + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter byte
        for x in range(width):
            raw += bytes([r, g, b])

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def img_to_base64_from_file(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ─────────────────────────────────────────────
# 测试场景
# ─────────────────────────────────────────────

def scenario_normal_single(image_dir: str | None = None, dummy: bool = False):
    """场景 A：正常两步骤 — 点击视频 + 点击点赞，各不重复。"""
    images = _load_images(["step_0_click_video", "step_1_click_like"], image_dir, dummy)
    return {
        "instruction": "在抖音首页点击视频进入播放页，然后点赞",
        "step_level_instruction": "点击视频→点击点赞",
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": images[0],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [530, 1200],
                        "end_box": [],
                        "text": "点击视频",
                        "direction": "",
                    }
                },
            },
            {
                "index": 1,
                "image_relative_path": images[1],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [995, 1448],
                        "end_box": [],
                        "text": "点击点赞按钮",
                        "direction": "",
                    }
                },
            },
            {
                "index": 2,
                "image_relative_path": images[1],  # finished 不产生新截图
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "start_box": [],
                        "end_box": [],
                        "text": "任务完成",
                        "direction": "",
                    }
                },
            },
        ],
    }


def scenario_repeated_click(image_dir: str | None = None, dummy: bool = False):
    """场景 B：重复点击 — 步骤1和步骤2对同一坐标重复点击（预期判为 repeat）。"""
    images = _load_images(["step_0_click_video", "step_1_click_like", "step_2_click_like_again"], image_dir, dummy)
    return {
        "instruction": "在抖音首页点击视频进入播放页，然后点赞并收藏",
        "step_level_instruction": "点击视频→点击点赞→点击收藏",
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": images[0],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [530, 1200],
                        "end_box": [],
                        "text": "点击视频",
                        "direction": "",
                    }
                },
            },
            {
                "index": 1,
                "image_relative_path": images[1],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [995, 1448],  # 点赞坐标
                        "end_box": [],
                        "text": "点击点赞按钮",
                        "direction": "",
                    }
                },
            },
            {
                "index": 2,
                "image_relative_path": images[2],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [995, 1448],  # 同一坐标！
                        "end_box": [],
                        "text": "再次点击点赞按钮",  # 相似文本
                        "direction": "",
                    }
                },
            },
            {
                "index": 3,
                "image_relative_path": images[2],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "start_box": [],
                        "end_box": [],
                        "text": "任务完成",
                        "direction": "",
                    }
                },
            },
        ],
    }


def scenario_missing_step(image_dir: str | None = None, dummy: bool = False):
    """场景 C：遗漏步骤 — 跳过收藏直接 finished（预期判为 planning_failure）。"""
    images = _load_images(["step_0_click_video", "step_1_click_like"], image_dir, dummy)
    return {
        "instruction": "在抖音首页点击视频进入播放页，然后点赞并收藏",
        "step_level_instruction": "点击视频→点击点赞→点击收藏",
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": images[0],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [530, 1200],
                        "end_box": [],
                        "text": "点击视频",
                        "direction": "",
                    }
                },
            },
            {
                "index": 1,
                "image_relative_path": images[1],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [995, 1448],
                        "end_box": [],
                        "text": "点击点赞按钮",
                        "direction": "",
                    }
                },
            },
            {
                "index": 2,
                "image_relative_path": images[1],
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",  # 直接结束，跳过了收藏！
                        "start_box": [],
                        "end_box": [],
                        "text": "任务完成",
                        "direction": "",
                    }
                },
            },
        ],
    }


def scenario_repeated_swipe(image_dir: str | None = None, dummy: bool = False):
    """场景 D：连续滑动 — 同方向滑动 ≥4 次（预期判为 repeated_swipe）。"""
    images = _load_images(["step_0_start"] + [f"step_{i}_swipe" for i in range(1, 6)], image_dir, dummy)
    seq_info = []
    for i in range(5):
        seq_info.append({
            "index": i,
            "image_relative_path": images[i],
            "planning_output": {
                "parsed_action": {
                    "action_type": "scroll",
                    "start_box": [540, 800],
                    "end_box": [540, 400],
                    "text": "向下滑动浏览",
                    "direction": "down",
                }
            },
        })
    seq_info.append({
        "index": 5,
        "image_relative_path": images[5],
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
    return {
        "instruction": "浏览抖音推荐列表",
        "step_level_instruction": "向下滑动浏览内容→查看视频→返回",
        "seq_info": seq_info,
    }


SCENARIOS = {
    "normal": ("场景A-正常轨迹", scenario_normal_single),
    "repeat": ("场景B-重复点击", scenario_repeated_click),
    "missing": ("场景C-遗漏步骤", scenario_missing_step),
    "repeat_swipe": ("场景D-连续滑动", scenario_repeated_swipe),
}


# ─────────────────────────────────────────────
# 图片加载
# ─────────────────────────────────────────────

# 占位图：不同颜色便于肉眼区分
_DUMMY_COLORS = {
    "step_0_click_video": (200, 200, 200),       # 灰 — 首页
    "step_0_start": (200, 200, 200),
    "step_1_click_like": (100, 180, 100),         # 绿 — 进入播放页
    "step_1_swipe": (130, 160, 130),
    "step_2_click_like_again": (100, 180, 100),   # 绿 — 同上（页面无变化）
    "step_2_swipe": (110, 140, 110),
    "step_3_swipe": (90, 120, 90),
    "step_4_swipe": (70, 100, 70),
    "step_5_swipe": (50, 80, 50),
}


def _load_images(names: list[str], image_dir: str | None, dummy: bool) -> list[str]:
    if image_dir:
        return [_load_image_from_dir(image_dir, name) for name in names]
    if dummy:
        return [_make_dummy_image(name) for name in names]
    return []


def _load_image_from_dir(image_dir: str, name: str) -> str:
    """从目录中按前缀匹配加载图片。支持 1.jpg, 2.png 等常见命名。"""
    candidates = [name + ext for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG")]
    for fname in candidates:
        path = os.path.join(image_dir, fname)
        if os.path.exists(path):
            return img_to_base64_from_file(path)

    # 回退：尝试按编号匹配
    import re
    match = re.match(r"step_(\d+)", name)
    if match:
        num = match.group(1)
        for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG"):
            path = os.path.join(image_dir, f"{num}{ext}")
            if os.path.exists(path):
                return img_to_base64_from_file(path)

    print(f"[WARN] 找不到图片: {name}.*，使用占位图", file=sys.stderr)
    return _make_dummy_image(name)


def _make_dummy_image(name: str) -> str:
    r, g, b = _DUMMY_COLORS.get(name, (128, 128, 128))
    data = png_bytes(360, 640, r, g, b)
    return base64.b64encode(data).decode()


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="/check_e2e 完整调用示例")
    parser.add_argument("--image-dir", help="截图目录路径")
    parser.add_argument("--dummy", action="store_true", help="使用自动生成的占位图")
    parser.add_argument("--base-url", default="http://localhost:20025", help="服务地址")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), default=None,
                        help="只运行指定场景（不传则全部运行）")
    args = parser.parse_args()

    if not args.image_dir and not args.dummy:
        parser.error("需要 --image-dir 或 --dummy")

    import requests

    selected = [args.scenario] if args.scenario else list(SCENARIOS.keys())

    for key in selected:
        name, factory = SCENARIOS[key]
        print("=" * 70)
        print(f"  {name}")
        print("=" * 70)

        payload = factory(image_dir=args.image_dir, dummy=args.dummy)
        print(f"payload: instruction={payload['instruction']}")
        print(f"         seq_info 共 {len(payload['seq_info'])} 步")
        print()

        try:
            resp = requests.post(f"{args.base_url}/check_e2e", json=payload, timeout=300)
        except requests.ConnectionError:
            print(f"[ERROR] 无法连接 {args.base_url}，请确认服务已启动")
            sys.exit(1)

        if resp.status_code != 200:
            print(f"[ERROR] HTTP {resp.status_code}: {resp.text[:500]}")
            continue

        result = resp.json().get("check_result", {})
        _print_section("重复动作判定", result.get("重复动作判定结果"), result.get("重复动作判定依据"))
        _print_section("规划失效判定", result.get("规划失效判定结果"), result.get("规划失效判定依据"))

        repeated = result.get("repeated_action_result", {})
        if repeated.get("ranges"):
            for r in repeated["ranges"]:
                print(f"  ├─ {r['repeat_type']}: 步骤{r['start_step']}→{r['end_step']}")
                print(f"  │  目标: {r['target']}  置信度: {r['confidence']}")
                for ev in r.get("evidence", []):
                    print(f"  │  · {ev}")

        planning = result.get("planning_failure_result", {})
        if planning.get("events"):
            for ev in planning["events"]:
                print(f"  ├─ {ev['subtype']}: 首错步骤{ev['first_error_step']}  置信度: {ev['confidence']}")
                for e in ev.get("evidence", []):
                    print(f"  │  · {e}")

        print()


def _print_section(title: str, label: str, evidence: str):
    symbol = "✓" if label == "normal" else "✗"
    print(f"  {symbol} {title}: {label}")
    if evidence:
        print(f"    依据: {evidence}")


if __name__ == "__main__":
    main()
