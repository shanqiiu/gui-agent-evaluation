"""
任务分解引擎：LLM + RAG → 结构化检查点列表。

用法:
    from decomposer import Decomposer
    d = Decomposer(model_url="http://localhost:8000/v1/chat/completions",
                   model_name="qwen3-8b")
    checkpoints = d.decompose("打开密码自动填充和保存功能")
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .knowledge_store import query_knowledge


_DECOMPOSE_PROMPT = """你是一个鸿蒙手机操作助手的任务规划专家。请根据用户指令和参考知识，将任务分解为结构化的检查点列表。

## 参考知识
{knowledge}

## 用户指令
{instruction}

## 输出要求
输出一个 JSON 数组，每个元素是一个检查点，包含:
- "name": 步骤描述（简短的动宾短语，如 "点击隐私和安全"）
- "required": true/false 是否必须完成
- "preconditions": 前置条件描述，如 "已进入设置首页"
- "expected_state": 完成后页面应呈现的状态

约束:
- 必须输出 1 到 8 个检查点，禁止输出空数组 []。
- 即使参考知识为空，也必须只根据用户指令生成最小可验证检查点。
- expected_state 必须描述截图或页面中可观察到的完成条件。
- 只输出 JSON 数组，不要任何额外文字。"""

_RETRY_DECOMPOSE_PROMPT = """上一次你返回了空检查点列表，这是无效输出。
请重新根据用户指令生成 1 到 8 个 GUI 任务检查点。

## 用户指令
{instruction}

## 输出要求
只输出 JSON 数组，且数组不能为空。字段固定为:
- "name"
- "required"
- "preconditions"
- "expected_state"

如果无法确定详细路径，也要输出一个必需检查点，expected_state 描述任务目标已在页面上完成或目标设置项状态已生效。"""

class Decomposer:
    """基于 LLM + RAG 的任务分解器。"""

    def __init__(self, model_url: str, model_name: str,
                 api_key: str = "", timeout: int = 60):
        self.model_url = model_url
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout
        self.last_error = ""
        self.last_response_head = ""

    def decompose(self, instruction: str,
                  app_name: str = "settings",
                  top_k: int = 5) -> list[dict[str, Any]]:
        """
        将用户指令分解为结构化检查点。

        返回:
        [
            {"name": "输入搜索关键词", "required": true, "preconditions": "已进入设置首页", "expected_state": "搜索栏显示关键词，出现搜索结果"},
            {"name": "点击搜索结果", "required": true, "preconditions": "搜索结果已显示", "expected_state": "进入对应设置页面"},
            ...
        ]
        """
        # 1. 检索 App 相关知识
        docs = query_knowledge(instruction, app_name=app_name, top_k=top_k)
        knowledge = "\n\n".join(docs) if docs else "（无相关 App 知识）"

        # 2. 构建 prompt
        prompt = _DECOMPOSE_PROMPT.format(
            knowledge=knowledge,
            instruction=instruction,
        )

        # 3. 调用 LLM
        checkpoints = self._call_and_parse(prompt)
        if checkpoints:
            return checkpoints
        if self.last_error != "LLM returned an empty checkpoint list":
            return []

        retry_prompt = _RETRY_DECOMPOSE_PROMPT.format(instruction=instruction)
        return self._call_and_parse(retry_prompt)

    def _call_and_parse(self, prompt: str) -> list[dict[str, Any]]:
        self.last_error = ""
        self.last_response_head = ""
        result = self._call_llm(prompt)
        self.last_response_head = result[:500] if result else ""
        if not result:
            if not self.last_error:
                self.last_error = "empty LLM response"
            return []
        return self._parse_checkpoints(result)

    def _parse_checkpoints(self, result: str) -> list[dict[str, Any]]:
        try:
            checkpoints = json.loads(result)
            if isinstance(checkpoints, list):
                if not checkpoints:
                    self.last_error = "LLM returned an empty checkpoint list"
                return checkpoints
        except json.JSONDecodeError as exc:
            import re
            match = re.search(r"\[.*\]", result, re.DOTALL)
            if match:
                try:
                    checkpoints = json.loads(match.group())
                    if isinstance(checkpoints, list) and not checkpoints:
                        self.last_error = "LLM returned an empty checkpoint list"
                    return checkpoints
                except json.JSONDecodeError as nested_exc:
                    self.last_error = f"invalid JSON array from LLM: {nested_exc}"
                    return []
            self.last_error = f"invalid JSON from LLM: {exc}; response_head={result[:200]!r}"
            return []
        self.last_error = "LLM response was not a JSON array"
        return []

    def _call_llm(self, prompt: str) -> str:
        """调用 OpenAI-compatible chat completions API。"""
        import requests

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(
                self.model_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            self.last_error = f"LLM request failed: {type(exc).__name__}: {exc}"
            return ""

        if resp.status_code != 200:
            self.last_error = f"LLM API returned {resp.status_code}: {resp.text[:200]}"
            return ""

        try:
            data = resp.json()
        except ValueError as exc:
            self.last_error = f"LLM API returned non-JSON response: {exc}; body={resp.text[:200]}"
            return ""
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        self.last_error = f"LLM API returned no choices: {str(data)[:200]}"
        return ""


# ── 便捷函数 ────────────────────────────────────────────────────

_default_decomposer: Optional[Decomposer] = None


def init_decomposer(model_url: str, model_name: str,
                    api_key: str = "") -> Decomposer:
    """初始化全局分解器实例。"""
    global _default_decomposer
    _default_decomposer = Decomposer(
        model_url=model_url, model_name=model_name, api_key=api_key
    )
    return _default_decomposer


def decompose_instruction(instruction: str, **kwargs) -> list[dict[str, Any]]:
    """使用全局实例分解指令。"""
    if _default_decomposer is None:
        raise RuntimeError("请先调用 init_decomposer()")
    return _default_decomposer.decompose(instruction, **kwargs)
