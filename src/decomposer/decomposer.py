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
import re
from typing import Any, Optional

from .knowledge_store import query_knowledge


_DECOMPOSE_PROMPT = """你是 GUI Agent 执行评测中的任务分解专家。请将用户任务分解为最小且必要的关键可观察子状态。checkpoint 只描述必须达到什么状态，不限定点击、输入、滑动等具体操作路径。

## 参考知识
{knowledge}

## 用户指令
{instruction}

## 输出要求
输出一个 JSON 数组，每个元素是一个检查点，包含:
- "name": 简短的子状态名称，如 "搜索结果已展示"
- "required": true/false；只有任务完成不可缺少的状态才设为 true
- "preconditions": 进入该子状态前必须满足的状态，无明确条件时填空字符串
- "expected_state": 可通过截图、OCR 或页面结构观察到的具体完成条件

约束:
- 必须输出 1 到 8 个检查点，禁止输出空数组 []。
- 优先输出 1 到 5 个关键状态；不要把每次点击、输入、滑动都拆成 checkpoint。
- 一个 checkpoint 只能表示一个状态边界，禁止用“然后”“并且”“同时”等连接多个阶段。
- 不要把“点击按钮”“输入文本”“滑动页面”这类纯操作作为 checkpoint。
- 不要绑定控件坐标、固定点击路径或某一种实现方式。
- expected_state 必须描述页面中可观察到的完成条件。
- 相邻 checkpoint 必须体现任务进展，禁止输出语义重复的状态。
- 即使参考知识为空，也必须只根据用户指令生成最小可验证状态集合。
- 只输出 JSON 数组，不要任何额外文字。"""

_RETRY_DECOMPOSE_PROMPT = """上一次你返回了空检查点列表，这是无效输出。
请重新根据用户指令生成 1 到 8 个 GUI 任务关键可观察子状态。

## 用户指令
{instruction}

## 输出要求
只输出 JSON 数组，且数组不能为空。字段固定为:
- "name"
- "required"
- "preconditions"
- "expected_state"

如果无法确定详细路径，也要输出一个必需检查点，expected_state 描述任务目标已在页面上完成或目标设置项状态已生效。"""

_REFINE_DECOMPOSE_PROMPT = """你生成的 checkpoint 粒度不符合 GUI Agent 评测要求，请修正后重新输出完整 JSON 数组。

用户指令：{instruction}
上一次输出：{checkpoints}
发现的问题：{issues}

修正规则：
- checkpoint 必须是路径无关的关键可观察子状态，不是点击、输入、滑动等操作步骤。
- 一个 checkpoint 只表示一个状态边界，拆开由“然后”“并且”“同时”等连接的复合阶段。
- 删除重复、非必要和无法通过截图、OCR 或页面结构验证的状态。
- 保留任务完成所需的最小状态集合，通常为 1 到 5 项，最多 8 项。
- 字段固定为 name、required、preconditions、expected_state。
- 只输出 JSON 数组，不要 Markdown 或额外文字。"""

_ACTION_NAME_PREFIXES = (
    "点击", "输入", "滑动", "滚动", "长按", "双击", "拖动", "返回",
    "选择", "勾选", "打开应用", "启动应用", "切换到",
)
_COMPOUND_MARKERS = (
    "然后", "并且", "同时", "随后", "接着", "之后再", "and then", "->", "→", ";", "；",
)

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
        self.last_quality_issues: list[str] = []
        self.refinement_attempted = False

    def decompose(self, instruction: str,
                  app_name: str | None = None,
                  top_k: int = 5) -> list[dict[str, Any]]:
        """
        将用户指令分解为结构化检查点。

        返回:
        [
            {"name": "搜索结果已展示", "required": true, "preconditions": "搜索入口可用", "expected_state": "页面展示与关键词相关的搜索结果"},
            {"name": "目标页面已打开", "required": true, "preconditions": "目标入口已出现", "expected_state": "目标页面标题和核心内容可见"},
            ...
        ]
        """
        self.last_quality_issues = []
        self.refinement_attempted = False

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
        if not checkpoints and self.last_error != "LLM returned an empty checkpoint list":
            return []
        if not checkpoints:
            retry_prompt = _RETRY_DECOMPOSE_PROMPT.format(instruction=instruction)
            checkpoints = self._call_and_parse(retry_prompt)
            return self._finalize_checkpoints(checkpoints, allow_refinement=False)

        return self._finalize_checkpoints(
            checkpoints,
            instruction=instruction,
            allow_refinement=True,
        )

    def _finalize_checkpoints(
        self,
        checkpoints: list[dict[str, Any]],
        *,
        instruction: str = "",
        allow_refinement: bool,
    ) -> list[dict[str, Any]]:
        normalized, issues = self._normalize_and_validate(checkpoints)
        if not normalized:
            self.last_quality_issues = issues
            self.last_error = "checkpoint quality validation produced no usable checkpoints"
            return []
        if not issues:
            self.last_quality_issues = []
            self.last_error = ""
            return normalized

        if allow_refinement:
            self.refinement_attempted = True
            refine_prompt = _REFINE_DECOMPOSE_PROMPT.format(
                instruction=instruction,
                checkpoints=json.dumps(normalized, ensure_ascii=False),
                issues="；".join(issues),
            )
            refined = self._call_and_parse(refine_prompt)
            if refined:
                refined_normalized, refined_issues = self._normalize_and_validate(refined)
                if refined_normalized and not refined_issues:
                    self.last_quality_issues = []
                    self.last_error = ""
                    return refined_normalized

        self.last_quality_issues = issues
        self.last_error = "checkpoint quality issues remain: " + "; ".join(issues)
        return normalized

    def _normalize_and_validate(
        self,
        checkpoints: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        normalized: list[dict[str, Any]] = []
        issues: list[str] = []
        seen_states: set[str] = set()

        if len(checkpoints) > 8:
            issues.append(f"checkpoint 数量为 {len(checkpoints)}，超过上限 8")

        for index, raw in enumerate(checkpoints[:8]):
            if not isinstance(raw, dict):
                issues.append(f"checkpoint[{index}] 不是对象")
                continue

            name = self._clean_text(raw.get("name"))
            preconditions = self._clean_text(raw.get("preconditions"))
            expected_state = self._clean_text(raw.get("expected_state"))
            if not name:
                issues.append(f"checkpoint[{index}] 缺少 name")
                continue
            if not expected_state:
                issues.append(f"checkpoint[{index}] 缺少 expected_state")
                continue

            if name.startswith(_ACTION_NAME_PREFIXES):
                issues.append(f"checkpoint[{index}] name 是操作步骤而非子状态：{name}")
            if any(marker in name.lower() for marker in _COMPOUND_MARKERS):
                issues.append(f"checkpoint[{index}] name 包含复合阶段：{name}")

            state_key = self._state_key(f"{name}|{expected_state}")
            if state_key in seen_states:
                issues.append(f"checkpoint[{index}] 与前序状态重复：{name}")
                continue
            seen_states.add(state_key)

            normalized.append({
                "name": name,
                "required": self._as_bool(raw.get("required", True)),
                "preconditions": preconditions,
                "expected_state": expected_state,
            })

        if not normalized:
            issues.append("没有可用 checkpoint")
        return normalized, list(dict.fromkeys(issues))

    @staticmethod
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @staticmethod
    def _state_key(value: str) -> str:
        return re.sub(r"[\s，。！？、,.;；:：]+", "", value).lower()

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "否", "非必需"}
        return bool(value)

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
