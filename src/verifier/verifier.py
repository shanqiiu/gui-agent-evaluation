"""Checkpoint Verifier — Module B of the GUI Agent evaluation system.

Consumes checkpoint descriptions (from Module A decomposer), before/after screenshots,
and action information to determine whether each checkpoint's expected state has been
achieved.

Core flow:
    1. For each checkpoint, find the action step(s) that should achieve it
    2. Construct a VLM prompt with before/after screenshots + checkpoint description
    3. Parse VLM response → status (达成/未达成/不确定) + confidence + evidence
    4. Aggregate results into VerificationReport

Adapted from Darwin's AB page validation + intention predicate VLM approach,
specialized for structured checkpoint verification.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .models import (
    Checkpoint,
    CheckpointResult,
    VerificationReport,
    VerifierConfig,
)
from .alignment import align_checkpoints_to_steps, build_checkpoint_step_data

# ── VLM Prompt Template ──────────────────────────────────────────────
# Adapted from Darwin's ab_test_prompts.py + intention_predicate.py,
# specialized for structured checkpoint verification instead of generic AB testing.

_CHECKPOINT_VERIFY_PROMPT = """你是一个专业的GUI Agent测试评估专家，负责判断一个操作步骤是否达到了预定的检查点要求。

现在我会给你三组信息：
1. 检查点描述（预期应该达到什么页面状态）
2. 操作前的页面截图 + 操作动作信息（Agent 在操作前看到了什么，做了什么操作）
3. 操作后的页面截图（操作执行后的实际结果）

请你根据这些信息，判断该检查点是否已经达成。

## 检查点信息
- 检查点名称: {checkpoint_name}
- 预期状态: {expected_state}
- 前置条件: {preconditions}
- 是否必须: {required}

## 操作前页面
{before_page}

## 操作动作
{action_info}

## 操作后页面
{after_page}

## 判定要求
请仔细对比操作后页面的内容与检查点描述的预期状态：
1. 操作后页面的功能、布局、数据内容是否符合预期状态的描述
2. 是否进入了检查点要求的页面或界面
3. 如果有页面内的状态变化（如选中、输入、切换tab等），是否已经生效

注意以下边缘情况：
- 如果操作后页面是加载中/网络错误/登录页/验证框，说明检查点未达成
- 如果操作后页面内容为空（如空列表、无数据），但页面本身是正确的，仍算达成
- 如果操作后页面是预期页面的子页面或相关页面，需要具体判断是否足够匹配

## 输出格式要求
输出必须是可直接解析的 JSON：
```json
{{
    "checkpoint_achieved": <bool, 检查点是否达成>,
    "confidence": <float, 0.0到1.0之间的置信度>,
    "page_description": <string, 操作后页面是什么页面，描述其主要内容和布局>,
    "thought": <string, 详细推理过程：操作前页面状态→执行了什么动作→操作后页面实际是什么→与预期状态对比→结论>,
    "mismatch_reason": <string, 如果未达成，具体说明哪里不符合预期；如果达成了，填"">
}}
```"""


# ── Heuristic fallback patterns (used when VLM unavailable or in mock mode) ──

_ACHIEVED_PATTERNS = [
    (r"进入.*页", 0.85),           # "进入设置首页", "进入隐私页面"
    (r"跳转.*页", 0.85),           # "跳转到支付页"
    (r"打开.*应用", 0.85),          # "打开设置应用"
    (r"搜索.*结果", 0.80),          # "搜索结果已显示"
    (r"显示.*列表", 0.80),          # "显示商品列表"
    (r"选中|勾选|切换", 0.75),       # "选中复选框", "勾选同意"
    (r"输入.*完成|已输入", 0.75),    # "输入完成"
    (r"提交|保存.*成功", 0.90),     # "提交订单成功", "保存成功"
    (r"支付.*完成", 0.90),          # "支付已完成"
    (r"下单.*成功", 0.90),          # "下单成功"
]

_NOT_ACHIEVED_PATTERNS = [
    (r"加载中|加载失败|网络错误", 0.90),
    (r"登录|验证码|验证框", 0.85),    # broader match
    (r"404|错误页|崩溃", 0.95),
    (r"空白页|无内容", 0.60),
    (r"返回.*首页|回到.*桌面", 0.80),
]


class CheckpointVerifier:
    """VLM-based checkpoint verification engine.

    Usage:
        config = VerifierConfig(vlm_model_url="http://...", vlm_model_name="qwen3-vl-8b")
        verifier = CheckpointVerifier(config)

        result = verifier.verify_checkpoint(
            checkpoint=Checkpoint(name="点击隐私和安全", expected_state="进入隐私设置页面"),
            before_image_base64="...",
            after_image_base64="...",
            action_description="点击'隐私和安全'按钮",
        )

        # Or batch verification:
        checkpoints = [Checkpoint(name="步骤1", ...), Checkpoint(name="步骤2", ...)]
        # Map each checkpoint to a (before_img, after_img, action_desc) tuple
        step_data = [...]  # one tuple per checkpoint
        report = verifier.verify_checkpoints(
            checkpoints=checkpoints,
            step_data=step_data,
            task_uuid="...",
            instruction="...",
        )
    """

    def __init__(self, config: VerifierConfig | None = None):
        self.config = config or VerifierConfig()

    # ── Single checkpoint verification ─────────────────────────────

    def verify_checkpoint(
        self,
        checkpoint: Checkpoint,
        before_image_base64: str = "",
        after_image_base64: str = "",
        action_description: str = "",
        *,
        step_index: int = -1,
    ) -> CheckpointResult:
        """Verify whether a single checkpoint has been achieved.

        Args:
            checkpoint: The checkpoint to verify (from Module A decomposer).
            before_image_base64: Base64-encoded screenshot before the action.
            after_image_base64: Base64-encoded screenshot after the action.
            action_description: What action the Agent performed.
            step_index: Index of the action step (for traceability).

        Returns:
            CheckpointResult with status, confidence, and evidence.
        """
        # If in mock mode or no VLM configured, use heuristics
        if self.config.mock_mode or not self.config.vlm_model_url:
            return self._heuristic_verify(
                checkpoint, action_description, step_index
            )

        # If both images are empty in production mode, return uncertain
        if not before_image_base64 and not after_image_base64:
            return CheckpointResult(
                checkpoint=checkpoint,
                status="不确定",
                confidence=0.0,
                evidence="缺少截图数据，无法进行VLM判定",
                step_index=step_index,
                action_description=action_description,
                fallback=True,
            )

        # Build the VLM prompt
        prompt = _CHECKPOINT_VERIFY_PROMPT.format(
            checkpoint_name=checkpoint.name,
            expected_state=checkpoint.expected_state or checkpoint.name,
            preconditions=checkpoint.preconditions or "无",
            required="是" if checkpoint.required else "否",
            before_page="[操作前截图已附加]" if before_image_base64 else "[无截图]",
            after_page="[操作后截图已附加]" if after_image_base64 else "[无截图]",
            action_info=action_description or "无操作描述",
        )

        # Call VLM with retries
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._call_vlm(
                    prompt=prompt,
                    images=self._build_image_list(
                        before_image_base64, after_image_base64
                    ),
                )
                result = self._parse_vlm_response(response, checkpoint, step_index,
                                                  action_description)
                # Apply confidence threshold
                result = self._apply_confidence_threshold(result)
                return result
            except Exception:
                if attempt == self.config.max_retries:
                    if self.config.enable_heuristic_fallback:
                        result = self._heuristic_verify(
                            checkpoint, action_description, step_index
                        )
                        result.fallback = True
                        return result
                    raise

        # Unreachable, but keep type checker happy
        return CheckpointResult(
            checkpoint=checkpoint,
            status="不确定",
            confidence=0.0,
            evidence="VLM调用失败",
            step_index=step_index,
            action_description=action_description,
            fallback=True,
        )

    # ── Batch verification ────────────────────────────────────────

    def verify_checkpoints(
        self,
        checkpoints: list[Checkpoint],
        step_data: list[dict[str, Any]],
        *,
        task_uuid: str = "",
        instruction: str = "",
    ) -> VerificationReport:
        """Verify all checkpoints for a task trajectory.

        Args:
            checkpoints: List of checkpoints from Module A decomposer.
            step_data: List of dicts, one per checkpoint, each with:
                - before_image_base64: str
                - after_image_base64: str
                - action_description: str
                - step_index: int
            task_uuid: Task identifier.
            instruction: Original task instruction.

        Returns:
            VerificationReport aggregating all results.
        """
        results: list[CheckpointResult] = []
        vlm_calls = 0
        fallbacks = 0

        for i, checkpoint in enumerate(checkpoints):
            data = step_data[i] if i < len(step_data) else {}
            result = self.verify_checkpoint(
                checkpoint=checkpoint,
                before_image_base64=data.get("before_image_base64", ""),
                after_image_base64=data.get("after_image_base64", ""),
                action_description=data.get("action_description", ""),
                step_index=data.get("step_index", -1),
            )
            if not result.fallback:
                vlm_calls += 1
            else:
                fallbacks += 1
            results.append(result)

        return self._build_report(
            results=results,
            task_uuid=task_uuid,
            instruction=instruction,
            total_vlm_calls=vlm_calls,
            fallback_count=fallbacks,
        )

    def verify_from_payload(
        self,
        checkpoints: list[Checkpoint],
        payload: dict[str, Any],
        *,
        checkpoint_step_map: dict[int, int] | None = None,
        ab_report: Any = None,
    ) -> VerificationReport:
        """Verify checkpoints using a full /check_e2e payload.

        This automatically pairs checkpoints with before/after screenshots
        from the payload's seq_info.

        Args:
            checkpoints: Checkpoints to verify.
            payload: Full /check_e2e payload dict with seq_info.
            checkpoint_step_map: Optional mapping from checkpoint_index to
                source seq_info step index. If None, aligns checkpoints by
                action/page evidence with monotonic ordering.

        Returns:
            VerificationReport.
        """
        seq_info = payload.get("seq_info", [])
        step_data: list[dict[str, Any]] = []

        if checkpoint_step_map is None:
            alignments = align_checkpoints_to_steps(
                checkpoints,
                payload,
                ab_report=ab_report,
            )
            step_data = build_checkpoint_step_data(checkpoints, payload, alignments)
        else:
            by_source = {
                int(step.get("index", pos)): (pos, step)
                for pos, step in enumerate(seq_info)
            }
            for cp_idx in range(len(checkpoints)):
                step_idx = checkpoint_step_map.get(cp_idx, -1)
                pos, step = by_source.get(step_idx, (-1, {}))
                next_step = seq_info[pos + 1] if pos >= 0 and pos + 1 < len(seq_info) else {}
                parsed = step.get("planning_output", {}).get("parsed_action", {})
                step_data.append({
                    "before_image_base64": step.get("image_relative_path", ""),
                    "after_image_base64": next_step.get("image_relative_path", ""),
                    "action_description": (
                        f"{parsed.get('action_type', '')}: {parsed.get('text', '')}"
                    ),
                    "step_index": step_idx,
                })

        return self.verify_checkpoints(
            checkpoints=checkpoints,
            step_data=step_data,
            task_uuid=payload.get("task_uuid", ""),
            instruction=payload.get("instruction", ""),
        )

    # ── VLM call ──────────────────────────────────────────────────

    def _call_vlm(self, prompt: str, images: list[str]) -> str:
        """Call the VLM endpoint (OpenAI-compatible chat/completions).

        Args:
            prompt: Text prompt for the VLM.
            images: List of base64-encoded image strings.

        Returns:
            Raw VLM response text.

        Raises:
            ConnectionError, Timeout, ValueError on failure.
        """
        import requests

        # Build content array with images + text
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
            raise ValueError(
                f"VLM API returned status {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("VLM API returned no choices")

        return choices[0].get("message", {}).get("content", "")

    # ── Response parsing ──────────────────────────────────────────

    def _parse_vlm_response(
        self,
        response: str,
        checkpoint: Checkpoint,
        step_index: int,
        action_description: str,
    ) -> CheckpointResult:
        """Parse VLM JSON response into a CheckpointResult."""
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        achieved = parsed.get("checkpoint_achieved", None)
        confidence = float(parsed.get("confidence", 0.5))
        thought = parsed.get("thought", response[:500])
        page_desc = parsed.get("page_description", "")
        mismatch = parsed.get("mismatch_reason", "")

        if achieved is True:
            status = "达成"
        elif achieved is False:
            status = "未达成"
        else:
            status = "不确定"
            confidence = min(confidence, 0.4)

        evidence_parts = [thought]
        if page_desc:
            evidence_parts.insert(0, f"[操作后页面]: {page_desc}")
        if mismatch:
            evidence_parts.append(f"[不符合原因]: {mismatch}")

        return CheckpointResult(
            checkpoint=checkpoint,
            status=status,
            confidence=confidence,
            evidence="\n".join(evidence_parts),
            step_index=step_index,
            action_description=action_description,
            fallback=False,
        )

    def _apply_confidence_threshold(self, result: CheckpointResult) -> CheckpointResult:
        """Demote status to '不确定' if confidence is below threshold."""
        if result.confidence < self.config.low_confidence_threshold:
            result.status = "不确定"
        elif result.status in ("达成", "未达成") and \
                result.confidence < self.config.high_confidence_threshold:
            result.status = "不确定"
        return result

    # ── Heuristic fallback ────────────────────────────────────────

    def _heuristic_verify(
        self,
        checkpoint: Checkpoint,
        action_description: str,
        step_index: int,
    ) -> CheckpointResult:
        """Rule-based heuristic verification when VLM is unavailable.

        Uses pattern matching on the action description + checkpoint name
        to estimate whether the checkpoint was achieved.

        This is a degraded fallback — results should be treated as low-confidence.
        """
        combined = f"{action_description} {checkpoint.name}"

        # Check not-achieved patterns first (negative signals take priority)
        for pattern, conf in _NOT_ACHIEVED_PATTERNS:
            if re.search(pattern, combined):
                return CheckpointResult(
                    checkpoint=checkpoint,
                    status="未达成",
                    confidence=conf * 0.7,
                    evidence=f"[启发式判定] 匹配未达成模式: '{pattern}'",
                    step_index=step_index,
                    action_description=action_description,
                    fallback=True,
                )

        # Check achieved patterns
        for pattern, conf in _ACHIEVED_PATTERNS:
            if re.search(pattern, combined):
                return CheckpointResult(
                    checkpoint=checkpoint,
                    status="达成",
                    confidence=conf * 0.7,
                    evidence=f"[启发式判定] 匹配达成模式: '{pattern}'",
                    step_index=step_index,
                    action_description=action_description,
                    fallback=True,
                )

        # Default: uncertain
        return CheckpointResult(
            checkpoint=checkpoint,
            status="不确定",
            confidence=0.3,
            evidence="[启发式判定] 无法确定，无匹配模式",
            step_index=step_index,
            action_description=action_description,
            fallback=True,
        )

    # ── Report building ───────────────────────────────────────────

    def _build_report(
        self,
        results: list[CheckpointResult],
        task_uuid: str,
        instruction: str,
        total_vlm_calls: int,
        fallback_count: int,
    ) -> VerificationReport:
        """Build an aggregated VerificationReport from individual results."""
        achieved = sum(1 for r in results if r.status == "达成")
        not_achieved = sum(1 for r in results if r.status == "未达成")
        uncertain = sum(1 for r in results if r.status == "不确定")

        required = [r for r in results if r.checkpoint.required]
        required_achieved = sum(1 for r in required if r.status == "达成")

        total = len(results)
        completion = achieved / total if total > 0 else 0.0
        req_completion = required_achieved / len(required) if required else 1.0

        # Determine overall status
        if total == 0:
            overall = "未判定"
        elif req_completion >= 1.0:
            overall = "优秀"
        elif req_completion >= 0.8:
            overall = "良好"
        elif req_completion >= 0.5:
            overall = "一般"
        else:
            overall = "失败"

        evidence: list[str] = []
        for r in results:
            status_mark = {"达成": "[OK]", "未达成": "[FAIL]", "不确定": "[?]"}.get(r.status, "?")
            evidence.append(
                f"{status_mark} [{r.checkpoint.name}] → {r.status} "
                f"(confidence={r.confidence:.2f})"
            )

        return VerificationReport(
            task_uuid=task_uuid,
            instruction=instruction,
            results=results,
            total_checkpoints=total,
            achieved_count=achieved,
            not_achieved_count=not_achieved,
            uncertain_count=uncertain,
            required_total=len(required),
            required_achieved=required_achieved,
            completion_score=completion,
            required_completion_score=req_completion,
            overall_status=overall,
            evidence=evidence,
            model_used=self.config.vlm_model_name if not self.config.mock_mode else "[mock]",
            total_vlm_calls=total_vlm_calls,
            fallback_count=fallback_count,
        )

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_image_list(before: str, after: str) -> list[str]:
        """Build image list, filtering out empty strings."""
        return [img for img in (before, after) if img]
