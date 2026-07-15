"""Unit tests for decomposer parsing and retry behavior."""

from __future__ import annotations

import json

from src.decomposer.decomposer import Decomposer


class StubDecomposer(Decomposer):
    def __init__(self, responses: list[str]):
        super().__init__(model_url="http://unused", model_name="unused")
        self.responses = responses
        self.prompts: list[str] = []

    def _call_llm(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_empty_checkpoint_list_retries_with_strict_prompt():
    expected = [{
        "name": "打开目标设置",
        "required": True,
        "preconditions": "已进入设置应用",
        "expected_state": "目标设置页面已打开",
    }]
    decomposer = StubDecomposer([
        "[]",
        json.dumps(expected, ensure_ascii=False),
    ])

    checkpoints = decomposer.decompose("打开目标设置", top_k=0)

    assert checkpoints == expected
    assert len(decomposer.prompts) == 2
    assert "无效输出" in decomposer.prompts[1]
