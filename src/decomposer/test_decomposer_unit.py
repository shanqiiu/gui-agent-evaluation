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


def test_action_and_compound_checkpoint_is_refined_to_observable_state():
    initial = [{
        "name": "点击搜索框然后输入关键词",
        "required": True,
        "preconditions": "应用首页可见",
        "expected_state": "准备执行搜索",
    }]
    refined = [{
        "name": "搜索结果已展示",
        "required": True,
        "preconditions": "搜索入口可用",
        "expected_state": "页面展示与关键词相关的搜索结果",
    }]
    decomposer = StubDecomposer([
        json.dumps(initial, ensure_ascii=False),
        json.dumps(refined, ensure_ascii=False),
    ])

    checkpoints = decomposer.decompose("搜索指定关键词", top_k=0)

    assert checkpoints == refined
    assert decomposer.refinement_attempted is True
    assert decomposer.last_quality_issues == []
    assert "关键可观察子状态" in decomposer.prompts[0]
    assert "粒度不符合" in decomposer.prompts[1]


def test_quality_validation_normalizes_and_removes_exact_duplicates():
    decomposer = StubDecomposer([])
    checkpoints, issues = decomposer._normalize_and_validate([
        {
            "name": " 目标页面已打开 ",
            "required": "true",
            "preconditions": " 目标入口可见 ",
            "expected_state": " 页面标题可见 ",
        },
        {
            "name": "目标页面已打开",
            "required": True,
            "preconditions": "目标入口可见",
            "expected_state": "页面标题可见",
        },
    ])

    assert checkpoints == [{
        "name": "目标页面已打开",
        "required": True,
        "preconditions": "目标入口可见",
        "expected_state": "页面标题可见",
    }]
    assert any("状态重复" in issue for issue in issues)


def test_quality_validation_rejects_missing_observable_state():
    decomposer = StubDecomposer([])
    checkpoints, issues = decomposer._normalize_and_validate([{
        "name": "目标状态已完成",
        "required": True,
        "preconditions": "",
        "expected_state": "",
    }])

    assert checkpoints == []
    assert any("缺少 expected_state" in issue for issue in issues)
