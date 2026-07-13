"""
测试 RAG 分解器。

前提: 已摄入 App 知识（python knowledge_store.py --ingest app_knowledge/）

用法:
    # 单条指令测试
    python test_decomposer.py

    # 指定 LLM 服务
    LLM_MODEL_URL=http://localhost:8000/v1/chat/completions \
    LLM_MODEL_NAME=qwen3-8b \
    python test_decomposer.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decomposer import Decomposer

TEST_INSTRUCTIONS = [
    "打开密码自动填充和保存功能",
    "把定时开关机状态设置成每周重复",
    "关闭一下发现附近的元服务功能",
    "禁止华为账号指纹验证",
    "请关闭指关节截屏功能",
]


def main():
    model_url = os.environ.get("LLM_MODEL_URL", "http://localhost:8000/v1/chat/completions")
    model_name = os.environ.get("LLM_MODEL_NAME", "qwen3-8b")
    api_key = os.environ.get("LLM_API_KEY", "")

    decomposer = Decomposer(model_url=model_url, model_name=model_name, api_key=api_key)

    for i, instr in enumerate(TEST_INSTRUCTIONS):
        print(f"\n{'=' * 60}")
        print(f"  [{i+1}] {instr}")
        print(f"{'=' * 60}")

        checkpoints = decomposer.decompose(instr)
        if not checkpoints:
            print("  → 分解失败（LLM 不可达或返回异常）")
            continue

        for j, cp in enumerate(checkpoints):
            name = cp.get("name", "?")
            required = cp.get("required", True)
            precond = cp.get("preconditions", "")
            expected = cp.get("expected_state", "")
            print(f"  [{'✓' if required else '○'}] {name}")
            if precond:
                print(f"     前置: {precond}")
            if expected:
                print(f"     期望: {expected}")

        print(f"\n  完整 JSON:\n{json.dumps(checkpoints, ensure_ascii=False, indent=4)}")


if __name__ == "__main__":
    main()
