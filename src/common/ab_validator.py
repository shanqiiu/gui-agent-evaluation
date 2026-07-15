"""AB Page Transition Validator — standalone VLM-based page transition checker.

Rebuilds Darwin's ab_pages_validate() capability as an independent module.
For each action step in a trajectory, validates whether the before→after page
transition is correct using VLM screenshot comparison.

This is the VLM dependency that both repeated_action_detector and
planning_failure_detector need.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .image_resolver import hydrate_payload_images
from .models import ABValidationReport, StepABResult

# ── VLM Prompt (adapted from Darwin's ab_test_prompts.py, wo_vp variant) ──

_AB_VALIDATE_PROMPT_PART1 = """你是一个App测试Agent，负责判定在App操作过程中，前后页面的切换是否是否符合预期。
请你基于给定的"前后页面截图信息"、"操作动作信息"，详细推理前后页面的切换是否符合预期，并在按照"输出格式要求"在"前后页面状态切换判定结果类别"中选择一个最适合的判定结果。


## 前后页面截图信息
现在我会给你两个张App页面截图，分别代表上一个页面截图以及下一个页面截图。
上一个页面截图为：
"""

_AB_VALIDATE_PROMPT_PART2 = """
下一个页面截图为：
"""

_AB_VALIDATE_PROMPT_PART3 = """

## 操作动作信息(在上一个页面所发生的动作信息）
{action_info}


## 前后页面状态切换判定结果类别
- 符合预期  # 注释：在上一个页面按照"操作动作信息"操作之后，下一个页面的页面功能、布局、数据内容这三方面都符合预期
- 不符合预期  # 注释：在上一个页面按照"操作动作信息"操作之后，下一个页面的页面功能、布局、数据内容这三方面中有存在不符合预期的情况


## 输出格式要求
```注释：输出必须是Python可以直接解析的json
{{
    "PageB_Content": <string, 告诉我下一个界面是什么界面，并且描述一下界面中所有被选中的tab，忽略页面中的网页信息，截图顶部的电池，信号，时间等信息（请注意，页面的顶部，底部和其他位置都可能有tab栏，你要找到所有的tab栏，然后识别出每个tab栏被选中的tab，不能有任何遗漏）>,
    "Thought": <string, 这里是你的推理过程，结合上一个页面的内容、在上一个页面发生了什么动作行为、该动作的预期结果是什么、下一个页面实际展示的内容，最后推理前后页面跳转属于"前后页面状态切换判定结果类别"里的哪一类>,
    "Answer": <string, 这里是推理得出的最终答案，为枚举值：符合预期|不符合预期>
}}
```"""

# Heuristic patterns for mock/fallback mode (when VLM unavailable)
_AB_EXPECTED_PATTERNS = [
    (r"进入|跳转|打开|切换.*(页|界面|应用|设置|功能)", "符合预期"),
    (r"滑动|滚动|翻页", "符合预期"),
    (r"输入|填写|选择|勾选", "符合预期"),
    (r"返回|退出", "符合预期"),
]

_AB_UNEXPECTED_PATTERNS = [
    (r"加载中|加载失败|网络错误|超时", "不符合预期"),
    (r"404|错误页|崩溃|白屏", "不符合预期"),
    (r"登录|验证码|权限.*拒绝", "不符合预期"),
]


class ABValidatorConfig:
    """Configuration for AB page transition validator."""

    def __init__(
        self,
        vlm_model_url: str = "",
        vlm_model_name: str = "qwen3-vl-8b",
        vlm_api_key: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        request_timeout: int = 120,
        max_retries: int = 2,
        mock_mode: bool = False,
    ):
        self.vlm_model_url = vlm_model_url
        self.vlm_model_name = vlm_model_name
        self.vlm_api_key = vlm_api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.mock_mode = mock_mode


class ABValidator:
    """Standalone AB page transition validator.

    Usage:
        config = ABValidatorConfig(vlm_model_url="http://...", vlm_model_name="qwen3-vl-8b")
        validator = ABValidator(config)
        report = validator.validate_payload(payload)
        # report.results[0].label → "符合预期"
    """

    def __init__(self, config: ABValidatorConfig | None = None):
        self.config = config or ABValidatorConfig()

    def validate_payload(
        self,
        payload: dict[str, Any],
        *,
        task_uuid: str = "",
        payload_path: str = "",
        image_base_dir: str = "",
        resolve_images: bool = True,
    ) -> ABValidationReport:
        """Validate AB transitions for all steps in a payload.

        Skips finished/done steps (no AB check for terminal steps).
        For each non-terminal step, validates the transition from
        step[i]'s screenshot to step[i+1]'s screenshot via VLM.
        """
        if resolve_images:
            payload, _stats = hydrate_payload_images(
                payload,
                payload_path=payload_path or None,
                image_base_dir=image_base_dir or None,
            )

        seq_info = payload.get("seq_info", [])
        results: list[StepABResult] = []
        vlm_calls = 0
        fallbacks = 0
        previous_pageb = ""

        for i in range(len(seq_info) - 1):
            current = seq_info[i]
            next_step = seq_info[i + 1]
            source_step_index = int(current.get("index", i))

            parsed = (current.get("planning_output") or {}).get("parsed_action") or {}
            action_type = str(parsed.get("action_type", "")).strip().lower()

            # Skip terminal steps — no transition to validate
            if action_type in {"finished", "done"}:
                continue

            before_img = current.get("image_relative_path", "")
            after_img = next_step.get("image_relative_path", "")
            action_text = parsed.get("text", "")
            direction = parsed.get("direction", "")
            action_info = self._build_action_info(action_type, action_text, direction)

            result = self.validate_single(
                before_image_base64=before_img,
                after_image_base64=after_img,
                action_info=action_info,
                step_index=source_step_index,
            )
            if not result.action_des:
                result.action_des = action_info
            result.pagea_description = previous_pageb
            previous_pageb = result.pageb_description

            if not result.label:
                fallbacks += 1
            else:
                vlm_calls += 1

            results.append(result)

        return ABValidationReport(
            task_uuid=task_uuid or payload.get("task_uuid", ""),
            results=results,
            model_used=self.config.vlm_model_name if not self.config.mock_mode else "[mock]",
            total_vlm_calls=vlm_calls,
            fallback_count=fallbacks,
        )

    def validate_single(
        self,
        before_image_base64: str,
        after_image_base64: str,
        action_info: str,
        *,
        step_index: int = -1,
    ) -> StepABResult:
        """Validate a single before→after transition.

        Args:
            before_image_base64: Base64-encoded screenshot before action.
            after_image_base64: Base64-encoded screenshot after action.
            action_info: Description of the action performed.
            step_index: Step index for traceability.

        Returns:
            StepABResult with label, action_des, page descriptions, thought.
        """
        # Mock/fallback mode
        if self.config.mock_mode or not self.config.vlm_model_url:
            return self._heuristic_validate(action_info, step_index)

        # No images — cannot validate
        if not before_image_base64 and not after_image_base64:
            return self._heuristic_validate(action_info, step_index)

        # Build prompt
        prompt = (
            _AB_VALIDATE_PROMPT_PART1
            + "[操作前截图已附加]"
            + _AB_VALIDATE_PROMPT_PART2
            + "[操作后截图已附加]"
            + _AB_VALIDATE_PROMPT_PART3.format(action_info=action_info)
        )

        # Call VLM with retries
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._call_vlm(
                    prompt=prompt,
                    images=[img for img in (before_image_base64, after_image_base64) if img],
                )
                return self._parse_vlm_response(response, step_index)
            except Exception:
                if attempt == self.config.max_retries:
                    return self._heuristic_validate(action_info, step_index)

        return StepABResult.empty(step_index)

    # ── VLM call ──────────────────────────────────────────────

    def _call_vlm(self, prompt: str, images: list[str]) -> str:
        import requests

        content_parts: list[dict[str, Any]] = []
        for img in images:
            if img:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                })
        content_parts.append({"type": "text", "text": prompt})

        payload = {
            "model": self.config.vlm_model_name,
            "messages": [{"role": "user", "content": content_parts}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if self.config.vlm_api_key:
            headers["Authorization"] = f"Bearer {self.config.vlm_api_key}"

        resp = requests.post(
            self.config.vlm_model_url,
            json=payload,
            headers=headers,
            timeout=self.config.request_timeout,
        )
        if resp.status_code != 200:
            raise ValueError(f"VLM API returned {resp.status_code}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("VLM returned no choices")
        return choices[0].get("message", {}).get("content", "")

    # ── Response parsing ──────────────────────────────────────

    def _parse_vlm_response(self, response: str, step_index: int) -> StepABResult:
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        answer = str(parsed.get("Answer", "")).strip()
        pageb = str(parsed.get("PageB_Content", "")).strip()
        thought = str(parsed.get("Thought", "")).strip()

        # Normalize label
        if answer in {"符合预期"}:
            label = "符合预期"
        elif answer in {"不符合预期"}:
            label = "不符合预期"
        elif answer:
            label = "无法判定"
        else:
            label = "无法判定"

        # Derive action_des from thought (VLM sometimes puts it there)
        action_des = self._extract_action_des(parsed, thought)

        return StepABResult(
            step_index=step_index,
            label=label,
            action_des=action_des,
            pagea_description="",
            pageb_description=pageb,
            thought=thought,
            confidence=self._confidence_from_label(label),
        )

    def _extract_action_des(
        self, parsed: dict[str, Any], thought: str
    ) -> str:
        """Extract action description from parsed JSON or thought."""
        if "ActionDescription" in parsed:
            return str(parsed["ActionDescription"])
        # Try to extract from thought
        action_match = re.search(
            r"操作[动作為]?\s*[:：]?\s*(.+?)(?:[，。,\.]|\Z)", thought
        )
        if action_match:
            return action_match.group(1).strip()[:100]
        return ""

    # ── Heuristic fallback ────────────────────────────────────

    def _heuristic_validate(
        self, action_info: str, step_index: int
    ) -> StepABResult:
        """Rule-based AB validation when VLM unavailable."""
        action_lower = action_info.lower()

        for pattern, label in _AB_UNEXPECTED_PATTERNS:
            if re.search(pattern, action_lower):
                return StepABResult(
                    step_index=step_index,
                    label=label,
                    action_des=action_info,
                    thought=f"[启发式] 匹配未预期模式: {pattern}",
                    confidence=0.65,
                )

        for pattern, label in _AB_EXPECTED_PATTERNS:
            if re.search(pattern, action_lower):
                return StepABResult(
                    step_index=step_index,
                    label=label,
                    action_des=action_info,
                    thought=f"[启发式] 匹配预期模式: {pattern}",
                    confidence=0.6,
                )

        return StepABResult(
            step_index=step_index,
            label="无法判定",
            action_des=action_info,
            thought="[启发式] 无法判定",
            confidence=0.3,
        )

    # ── Helpers ────────────────────────────────────────────────

    def _build_action_info(
        self, action_type: str, text: str, direction: str
    ) -> str:
        """Build action info string for VLM prompt."""
        parts = [f"动作类型: {action_type}"]
        if text:
            parts.append(f"操作目标: {text}")
        if direction:
            parts.append(f"方向: {direction}")
        return "；".join(parts) if parts else "无操作信息"

    @staticmethod
    def _confidence_from_label(label: str) -> float:
        if label == "符合预期":
            return 0.85
        elif label == "不符合预期":
            return 0.85
        return 0.3
