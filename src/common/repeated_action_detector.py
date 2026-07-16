"""Repeated action detection — independent of Darwin oracle.

Detects four types of repeated actions from trajectory data:
    1. Consecutive repeat — same action on same target with no progress
    2. Wait spam — consecutive wait/do-nothing actions
    3. Swipe spam — consecutive same-direction scrolls with no progress
    4. State-action loops — returning to same state and doing same action

Inputs:
    - payload (seq_info): action_type, start_box, text, direction
    - ABValidationReport: AB labels + page descriptions per step
    - VerificationReport (Module B): checkpoint achievement by step

Output: RepeatedActionResult with ranges, severity, confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .models import RepeatedActionResult, RepeatedActionRange


@dataclass(frozen=True)
class RepeatedActionConfig:
    lookback_window: int = 3
    loop_window: int = 8
    coord_distance_px: float = 80.0
    coord_distance_normalized: float = 0.06
    text_similarity_threshold: float = 0.95
    target_similarity_threshold: float = 0.82
    page_similarity_threshold: float = 0.88
    consecutive_wait_threshold: int = 3
    consecutive_swipe_threshold: int = 4


_GUI_ACTION_TYPES = {
    "click",
    "long_press",
    "type",
    "set_text",
    "scroll",
    "swipe",
    "drag",
    "wait",
    "do-nothing",
    "do_nothing",
    "do_nothing()",
    "open_app",
    "back",
}

_NON_GUI_ACTION_KEYWORDS = (
    "\u7528\u6237\u56de\u590d",
    "\u64ad\u62a5",
    "\u8bed\u97f3\u64ad\u62a5",
    "assistant",
    "system",
    "reply",
    "speak",
    "tts",
)


def detect_repeated_actions(
    payload: dict[str, Any],
    ab_report: Any = None,                    # ABValidationReport or compatible
    verification_report: Any = None,          # VerificationReport (Module B) or compatible
    config: RepeatedActionConfig | None = None,
    state_sequence: Any = None,               # StateSequence or compatible
) -> RepeatedActionResult:
    """Detect repeated actions from payload + AB validation + verification results.

    Args:
        payload: /check_e2e payload dict with seq_info.
        ab_report: ABValidationReport with per-step AB labels and descriptions.
        verification_report: Module B VerificationReport with checkpoint results.
        config: Optional RepeatedActionConfig.

    Returns:
        RepeatedActionResult.
    """
    detector = RepeatedActionDetector(config or RepeatedActionConfig())
    return detector.detect(payload, ab_report, verification_report, state_sequence)


class RepeatedActionDetector:
    """Model-free repeated action detector."""

    def __init__(self, config: RepeatedActionConfig):
        self.config = config

    def detect(
        self,
        payload: dict[str, Any],
        ab_report: Any = None,
        verification_report: Any = None,
        state_sequence: Any = None,
    ) -> RepeatedActionResult:
        steps = self._build_steps(payload, ab_report)
        if len(steps) < 2:
            return self._normal_result("动作序列过短，未发现重复动作。", len(steps))

        progress_by_step = self._build_progress_by_step(
            payload, ab_report, verification_report, state_sequence
        )
        ranges: list[RepeatedActionRange] = []
        ranges.extend(self._detect_consecutive_repeats(steps, progress_by_step))
        ranges.extend(self._detect_wait_repeats(steps))
        ranges.extend(self._detect_swipe_repeats(steps, progress_by_step))
        ranges.extend(self._detect_short_loops(steps, progress_by_step))

        merged = self._merge_ranges(ranges)
        if not merged:
            return self._normal_result("未发现重复动作异常。", len(steps))

        severity = self._overall_severity(merged)
        confidence = max(item.confidence for item in merged)
        return RepeatedActionResult(
            label="abnormal",
            severity=severity,
            confidence=round(confidence, 3),
            ranges=merged,
            summary=self._make_summary(merged),
            action_count=len(steps),
            repeated_range_count=len(merged),
        )

    # ── Step building ──────────────────────────────────────────

    def _build_steps(
        self, payload: dict[str, Any], ab_report: Any
    ) -> list[dict[str, Any]]:
        seq_info = payload.get("seq_info") or []
        steps: list[dict[str, Any]] = []

        for pos, item in enumerate(seq_info):
            planning_output = item.get("planning_output") or {}
            parsed_action = planning_output.get("parsed_action") or {}
            action_type = self._normalize_text(parsed_action.get("action_type"))
            if not action_type:
                continue
            if not self._is_repeated_candidate_action(action_type):
                continue

            source_step_index = int(item.get("index", pos))
            ab_result = self._get_ab_result(ab_report, source_step_index)

            steps.append({
                "step": source_step_index,
                "pos": pos,
                "action_type": action_type,
                "start_box": self._normalize_box(parsed_action.get("start_box")),
                "end_box": self._normalize_box(parsed_action.get("end_box")),
                "text": self._normalize_text(parsed_action.get("text")),
                "direction": self._normalize_text(parsed_action.get("direction")),
                "target": self._normalize_text(
                    ab_result.get("action_des")
                    or parsed_action.get("text")
                    or self._fallback_action_text(parsed_action)
                ),
                "page_before": self._normalize_text(ab_result.get("pagea_description")),
                "page_after": self._normalize_text(ab_result.get("pageb_description")),
                "ab_label": self._normalize_text(ab_result.get("label")),
                "ab_thought": self._normalize_text(ab_result.get("thought")),
            })

        return steps


    def _is_repeated_candidate_action(self, action_type: str) -> bool:
        if action_type in {"finished", "done", "clarify"}:
            return False
        if action_type in _GUI_ACTION_TYPES:
            return True
        return not any(keyword.lower() in action_type for keyword in _NON_GUI_ACTION_KEYWORDS)

    def _get_ab_result(self, ab_report: Any, step_index: int) -> dict[str, Any]:
        """Get AB result for a step from ABValidationReport or Darwin dict."""
        if ab_report is None:
            return {}
        if isinstance(ab_report, dict):
            ab_results = ab_report.get("results") or ab_report.get("ab_pages_result") or {}
            result = ab_results.get(str(step_index)) or ab_results.get(step_index) or {}
            return result if isinstance(result, dict) else {}
        # ABValidationReport
        if hasattr(ab_report, "get"):
            sr = ab_report.get(step_index)
            if hasattr(sr, "to_dict"):
                return sr.to_dict()
            return sr if isinstance(sr, dict) else {}
        return {}

    def _build_progress_by_step(
        self,
        payload: dict[str, Any],
        ab_report: Any,
        verification_report: Any,
        state_sequence: Any = None,
    ) -> dict[int, int]:
        """Build a mapping from step_index to cumulative progress.

        Progress points come from checkpoint verification results:
        each achieved checkpoint's step_index is a progress point.
        Falls back to intention step page_ids if module B not available.
        """
        progress_points: list[int] = []

        # From lightweight StateSequence transitions.
        if state_sequence is not None:
            if hasattr(state_sequence, "progress_steps"):
                progress_points.extend(
                    p for p in state_sequence.progress_steps
                    if isinstance(p, int) and p >= 0
                )
            elif isinstance(state_sequence, dict):
                progress_points.extend(
                    p for p in state_sequence.get("progress_steps", [])
                    if isinstance(p, int) and p >= 0
                )
        # From Module B VerificationReport
        if verification_report is not None and hasattr(verification_report, "results"):
            for r in verification_report.results:
                if hasattr(r, "status") and r.status == "达成":
                    if hasattr(r, "step_index") and r.step_index >= 0:
                        progress_points.append(r.step_index)

        # From legacy Darwin dict (backward compat)
        if not progress_points and isinstance(verification_report, dict):
            for key in ("llm_intention_step", "vlm_intention_step"):
                step_results = verification_report.get(key)
                if not isinstance(step_results, dict):
                    continue
                for item in step_results.values():
                    if isinstance(item, dict) and item.get("label") == "ok":
                        page_id = item.get("page_id")
                        if isinstance(page_id, list):
                            page_id = page_id[0] if page_id else -1
                        if isinstance(page_id, int) and page_id >= 0:
                            progress_points.append(page_id)

        progress_by_step: dict[int, int] = {}
        if not progress_points:
            return progress_by_step

        max_step = max(progress_points)
        for step in range(max_step + 2):
            progress_by_step[step] = sum(1 for p in progress_points if p <= step)
        return progress_by_step

    # ── Detection sub-methods ───────────────────────────────────

    def _detect_consecutive_repeats(
        self,
        steps: list[dict[str, Any]],
        progress_by_step: dict[int, int],
    ) -> list[RepeatedActionRange]:
        ranges: list[RepeatedActionRange] = []
        for i, current in enumerate(steps):
            if current["action_type"] in {"finished", "done", "clarify"}:
                continue
            start = max(0, i - self.config.lookback_window)
            for j in range(i - 1, start - 1, -1):
                previous = steps[j]
                if not self._equivalent_action(previous, current):
                    continue
                if self._is_reasonable_repeat(previous, current, i - j):
                    continue
                if not self._no_progress_between(previous, current, progress_by_step):
                    continue

                ranges.append(RepeatedActionRange(
                    start_step=previous["step"],
                    end_step=current["step"],
                    action_type=current["action_type"],
                    target=current.get("target") or self._fallback_action_text(current),
                    repeat_type="repeated_action",
                    confidence=self._repeat_confidence(previous, current),
                    evidence=[
                        f"步骤{previous['step']}和步骤{current['step']}动作等效",
                        f"目标控件/动作描述相似度"
                        f"{self._target_similarity(previous, current):.2f}",
                        "期间无新增检查点达成",
                        self._ab_evidence(current),
                    ],
                ))
                break
        return ranges

    def _detect_wait_repeats(
        self, steps: list[dict[str, Any]]
    ) -> list[RepeatedActionRange]:
        ranges: list[RepeatedActionRange] = []
        start = None
        sentinel = {"action_type": "__sentinel__", "step": -1}
        for i, step in enumerate(steps + [sentinel]):
            if step["action_type"] in {"wait", "do-nothing"}:
                if start is None:
                    start = i
                continue
            if start is not None and i - start >= self.config.consecutive_wait_threshold:
                first = steps[start]
                last = steps[i - 1]
                ranges.append(RepeatedActionRange(
                    start_step=first["step"],
                    end_step=last["step"],
                    action_type="wait",
                    repeat_type="repeated_wait",
                    confidence=0.72,
                    evidence=[
                        f"连续等待{i - start}次",
                        "连续 wait/do-nothing 通常表示页面停滞或Agent卡住",
                    ],
                ))
            start = None
        return ranges

    def _detect_swipe_repeats(
        self,
        steps: list[dict[str, Any]],
        progress_by_step: dict[int, int],
    ) -> list[RepeatedActionRange]:
        ranges: list[RepeatedActionRange] = []
        start = None
        last_signature = None
        sentinel = {"action_type": "__sentinel__", "step": -1}
        for i, step in enumerate(steps + [sentinel]):
            signature = None
            if step["action_type"] in {"scroll", "swipe", "drag"}:
                signature = (step["action_type"], step.get("direction"))

            if signature and signature == last_signature:
                if start is None:
                    start = i - 1
            else:
                if start is not None and i - start >= self.config.consecutive_swipe_threshold:
                    first = steps[start]
                    last = steps[i - 1]
                    if self._no_progress_between(first, last, progress_by_step):
                        ranges.append(RepeatedActionRange(
                            start_step=first["step"],
                            end_step=last["step"],
                            action_type=last["action_type"],
                            repeat_type="repeated_swipe",
                            confidence=0.68,
                            evidence=[
                                f"连续同方向滑动{i - start}次",
                                "期间无新增检查点达成",
                            ],
                        ))
                start = None
            last_signature = signature
        return ranges

    def _detect_short_loops(
        self,
        steps: list[dict[str, Any]],
        progress_by_step: dict[int, int],
    ) -> list[RepeatedActionRange]:
        ranges: list[RepeatedActionRange] = []
        seen: dict[tuple[str, str], int] = {}
        for i, step in enumerate(steps):
            state_sig = self._state_signature(step)
            action_sig = self._action_signature(step)
            if not state_sig or not action_sig:
                continue

            key = (state_sig, action_sig)
            prev_idx = seen.get(key)
            if prev_idx is not None and 1 < i - prev_idx <= self.config.loop_window:
                previous = steps[prev_idx]
                if self._no_progress_between(previous, step, progress_by_step):
                    ranges.append(RepeatedActionRange(
                        start_step=previous["step"],
                        end_step=step["step"],
                        action_type=step["action_type"],
                        repeat_type="state_action_loop",
                        confidence=0.8,
                        evidence=[
                            f"步骤{previous['step']}到步骤{step['step']}"
                            "出现相同页面状态和动作签名",
                            "短窗口内回到旧状态并执行等效动作",
                            "期间无新增检查点达成",
                        ],
                    ))
            seen[key] = i
        return ranges

    # ── Equivalence & similarity ────────────────────────────────

    def _equivalent_action(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left["action_type"] != right["action_type"]:
            click_types = {"click", "long_press"}
            if {left["action_type"], right["action_type"]} - click_types:
                return False

        action_type = right["action_type"]
        if action_type in {"click", "long_press"}:
            return self._same_target(left, right)
        if action_type in {"type", "set_text"}:
            return (
                self._same_target(left, right)
                and self._similarity(left["text"], right["text"])
                >= self.config.text_similarity_threshold
            )
        if action_type in {"scroll", "swipe", "drag"}:
            return left["direction"] == right["direction"] and self._same_region(
                left.get("start_box"), right.get("start_box")
            )
        return (
            self._target_similarity(left, right)
            >= self.config.target_similarity_threshold
        )

    def _same_target(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        return self._same_region(
            left.get("start_box"), right.get("start_box")
        ) or (
            self._target_similarity(left, right)
            >= self.config.target_similarity_threshold
        )

    def _same_region(
        self, left_box: list[float] | None, right_box: list[float] | None
    ) -> bool:
        if not left_box or not right_box or len(left_box) < 2 or len(right_box) < 2:
            return False
        distance = (
            (left_box[0] - right_box[0]) ** 2 + (left_box[1] - right_box[1]) ** 2
        ) ** 0.5
        if max(abs(left_box[0]), abs(left_box[1]),
               abs(right_box[0]), abs(right_box[1])) <= 1:
            return distance <= self.config.coord_distance_normalized
        return distance <= self.config.coord_distance_px

    def _no_progress_between(
        self,
        previous: dict[str, Any],
        current: dict[str, Any],
        progress_by_step: dict[int, int],
    ) -> bool:
        prev_progress = progress_by_step.get(previous["step"], 0)
        cur_progress = progress_by_step.get(current["step"], prev_progress)
        if cur_progress > prev_progress:
            return False

        if current["ab_label"] in {"不符合预期", "无法判定"}:
            return True
        if self._page_similarity(previous, current) >= self.config.page_similarity_threshold:
            return True
        if current["ab_label"] == "符合预期":
            return False
        return True

    def _is_reasonable_repeat(
        self, previous: dict[str, Any], current: dict[str, Any], distance: int
    ) -> bool:
        text = " ".join([
            previous.get("target", ""),
            current.get("target", ""),
            previous.get("ab_thought", ""),
            current.get("ab_thought", ""),
        ])
        if current["action_type"] in {"scroll", "swipe", "drag"}:
            return False
        if any(kw in text for kw in ("重试", "加载失败", "网络异常", "刷新")):
            return distance <= 2
        if any(kw in text for kw in ("多选", "勾选", "删除", "退格")):
            return True
        return False

    def _repeat_confidence(
        self, previous: dict[str, Any], current: dict[str, Any]
    ) -> float:
        confidence = 0.55
        if self._same_region(previous.get("start_box"), current.get("start_box")):
            confidence += 0.18
        if self._target_similarity(previous, current) >= self.config.target_similarity_threshold:
            confidence += 0.14
        if self._page_similarity(previous, current) >= self.config.page_similarity_threshold:
            confidence += 0.08
        if current["ab_label"] in {"不符合预期", "无法判定"}:
            confidence += 0.06
        if current["ab_label"] == "符合预期":
            confidence -= 0.08
        return max(0.0, min(confidence, 0.98))

    # ── Merging & summarization ──────────────────────────────────

    def _merge_ranges(
        self, ranges: list[RepeatedActionRange]
    ) -> list[RepeatedActionRange]:
        if not ranges:
            return []
        ranges = sorted(ranges, key=lambda r: (r.start_step, r.end_step, -r.confidence))
        merged: list[RepeatedActionRange] = []
        for item in ranges:
            if not merged or item.start_step > merged[-1].end_step:
                merged.append(item)
                continue
            current = merged[-1]
            current.end_step = max(current.end_step, item.end_step)
            current.confidence = max(current.confidence, item.confidence)
            current.severity = self._max_severity(current.severity, item.severity)
            current.evidence = self._dedupe(current.evidence + item.evidence)
            if item.repeat_type not in current.repeat_type:
                current.repeat_type = f"{current.repeat_type}+{item.repeat_type}"
        return merged

    def _overall_severity(self, ranges: list[RepeatedActionRange]) -> str:
        severity = "low"
        for r in ranges:
            severity = self._max_severity(severity, r.severity)
        return severity

    def _max_severity(self, left: str, right: str) -> str:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        return left if order.get(left, 0) >= order.get(right, 0) else right

    def _make_summary(self, ranges: list[RepeatedActionRange]) -> str:
        first = ranges[0]
        return (
            f"检测到{len(ranges)}段重复动作异常；首段位于步骤{first.start_step}到"
            f"步骤{first.end_step}，动作为{first.action_type}，目标为{first.target}。"
        )

    def _normal_result(self, summary: str, action_count: int) -> RepeatedActionResult:
        return RepeatedActionResult(
            label="normal",
            severity="none",
            confidence=0.0,
            ranges=[],
            summary=summary,
            action_count=action_count,
            repeated_range_count=0,
        )

    # ── Utility ──────────────────────────────────────────────────

    def _state_signature(self, step: dict[str, Any]) -> str:
        page_text = step.get("page_before") or step.get("page_after") or ""
        return self._compact(page_text)[:120] if page_text else ""

    def _action_signature(self, step: dict[str, Any]) -> str:
        return "|".join([
            step.get("action_type", ""),
            self._compact(step.get("target", ""))[:60],
            step.get("direction", ""),
            step.get("text", ""),
        ])

    def _target_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        return self._similarity(left.get("target", ""), right.get("target", ""))

    def _page_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        lp = left.get("page_before") or left.get("page_after") or ""
        rp = right.get("page_before") or right.get("page_after") or ""
        return self._similarity(lp, rp)

    def _similarity(self, left: str, right: str) -> float:
        left = self._compact(left)
        right = self._compact(right)
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        return SequenceMatcher(None, left, right).ratio()

    def _ab_evidence(self, step: dict[str, Any]) -> str:
        if not step.get("ab_label"):
            return ""
        return f"AB单步判定结果为{step['ab_label']}"

    def _fallback_action_text(self, parsed_action_or_step: dict[str, Any]) -> str:
        action_type = parsed_action_or_step.get("action_type", "")
        text = parsed_action_or_step.get("text", "")
        direction = parsed_action_or_step.get("direction", "")
        return " ".join(str(i) for i in (action_type, text, direction) if i)

    def _normalize_box(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value[:2]:
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                return []
        return result

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    def _compact(self, value: str) -> str:
        return "".join(str(value).lower().split())

    def _dedupe(self, values: list[str]) -> list[str]:
        result = []
        for v in values:
            if v and v not in result:
                result.append(v)
        return result
