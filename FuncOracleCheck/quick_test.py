"""
快速测试脚本 — 用 screenshots/ 目录下的图片调用本地服务接口。

用法:
    python quick_test.py          # 测试所有场景
    python quick_test.py --test 1 # 只测试场景 1（单步：首页→播放页）
    python quick_test.py --test 2 # 只测试场景 2（单步：播放页→点赞）
    python quick_test.py --test 3 # 只测试场景 3（E2E 序列：首页→播放→点赞→收藏）

前提: uvicorn main:app --host 0.0.0.0 --port 20026 --reload 已启动
"""

import argparse
import base64
import json
import os
import sys

import requests

BASE_URL = "http://localhost:20026"
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


def img_to_base64(filename: str) -> str:
    path = os.path.join(SCREENSHOTS_DIR, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ─────────────────────────────────────────────
# 场景 1: /check_single_funck  首页 → 点击视频进入播放页
# ─────────────────────────────────────────────
def test_single_click_video():
    print("=" * 60)
    print("场景 1: /check_single_funck  —  点击视频进入播放页")
    print("=" * 60)

    payload = {
        "actionList": [
            {
                "img": img_to_base64("1.JPG"),
                "layout": "",
                "operType": "click",
                "startBox": [530, 1200],  # 点击视频区域
                "endBox": [],
                "text": "",
                "direction": "",
            },
            {
                "img": img_to_base64("2.JPG"),
                "layout": "",
            },
        ]
    }
    resp = requests.post(f"{BASE_URL}/check_single_funck", json=payload)
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    else:
        print(f"[ERROR] {resp.text[:500]}")
    print()


# ─────────────────────────────────────────────
# 场景 2: /check_single_funck  播放页 → 点击点赞
# ─────────────────────────────────────────────
def test_single_click_like():
    print("=" * 60)
    print("场景 2: /check_single_funck  —  点击点赞按钮")
    print("=" * 60)

    payload = {
        "actionList": [
            {
                "img": img_to_base64("2.JPG"),
                "layout": "",
                "operType": "click",
                "startBox": [995, 1448],  # 点赞心形按钮
                "endBox": [],
                "text": "",
                "direction": "",
            },
            {
                "img": img_to_base64("3.JPG"),
                "layout": "",
            },
        ]
    }
    resp = requests.post(f"{BASE_URL}/check_single_funck", json=payload)
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    else:
        print(f"[ERROR] {resp.text[:500]}")
    print()


# ─────────────────────────────────────────────
# 场景 3: /check_single_funck  点赞后 → 点击收藏
# ─────────────────────────────────────────────
def test_single_click_fav():
    print("=" * 60)
    print("场景 3: /check_single_funck  —  点击收藏按钮")
    print("=" * 60)

    payload = {
        "actionList": [
            {
                "img": img_to_base64("3.JPG"),
                "layout": "",
                "operType": "click",
                "startBox": [995, 1760],  # 收藏星星按钮
                "endBox": [],
                "text": "",
                "direction": "",
            },
            {
                "img": img_to_base64("4.JPG"),
                "layout": "",
            },
        ]
    }
    resp = requests.post(f"{BASE_URL}/check_single_funck", json=payload)
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    else:
        print(f"[ERROR] {resp.text[:500]}")
    print()


# ─────────────────────────────────────────────
# 场景 4: /check_e2e  E2E 序列: 首页 → 播放 → 点赞 → 收藏
# ─────────────────────────────────────────────
def test_e2e_sequence():
    print("=" * 60)
    print("场景 4: /check_e2e  —  E2E 完整序列: 首页→播放→点赞→收藏")
    print("=" * 60)

    payload = {
        "instruction": "在抖音首页点击视频进入播放页，然后点赞并收藏",
        "step_level_instruction": "点击视频→点击点赞→点击收藏",
        "seq_info": [
            {
                "index": 0,
                "image_relative_path": img_to_base64("1.JPG"),
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [530, 1200],
                        "end_box": [],
                        "text": "点击西游记视频",
                        "direction": "",
                    }
                },
            },
            {
                "index": 1,
                "image_relative_path": img_to_base64("2.JPG"),
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
                "image_relative_path": img_to_base64("3.JPG"),
                "planning_output": {
                    "parsed_action": {
                        "action_type": "click",
                        "start_box": [995, 1760],
                        "end_box": [],
                        "text": "点击收藏按钮",
                        "direction": "",
                    }
                },
            },
            {
                "index": 3,
                "image_relative_path": img_to_base64("4.JPG"),
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
    resp = requests.post(f"{BASE_URL}/check_e2e", json=payload)
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    else:
        print(f"[ERROR] {resp.text[:500]}")
    print()


# ─────────────────────────────────────────────
# 场景 5: /check_single_funck  加载失败页对比
# ─────────────────────────────────────────────
def test_loading_fail():
    print("=" * 60)
    print("场景 5: /check_single_funck  —  加载失败页对比")
    print("=" * 60)

    payload = {
        "actionList": [
            {
                "img": img_to_base64("pic2.jpg"),
                "layout": "",
                "operType": "click",
                "startBox": [430, 1600],  # 点击重试按钮
                "endBox": [],
                "text": "",
                "direction": "",
            },
            {
                "img": img_to_base64("pic3.jpg"),
                "layout": "",
            },
        ]
    }
    resp = requests.post(f"{BASE_URL}/check_single_funck", json=payload)
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    else:
        print(f"[ERROR] {resp.text[:500]}")
    print()


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
TESTS = {
    "1": test_single_click_video,
    "2": test_single_click_like,
    "3": test_single_click_fav,
    "4": test_e2e_sequence,
    "5": test_loading_fail,
}


def main():
    parser = argparse.ArgumentParser(description="FuncOracleCheck 快速测试")
    parser.add_argument(
        "--test",
        type=str,
        default=None,
        help="只运行指定场景编号 (1-5)，不传则运行全部",
    )
    args = parser.parse_args()

    if args.test:
        test_fn = TESTS.get(args.test)
        if test_fn is None:
            print(f"未知的场景编号: {args.test}，可选: {list(TESTS.keys())}")
            sys.exit(1)
        test_fn()
    else:
        for key, fn in TESTS.items():
            fn()

    print("所有测试完成。")


if __name__ == "__main__":
    main()
