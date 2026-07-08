"""Repeated action detection for GUI Agent execution traces.

The detector is model-free. It reuses existing Darwin outputs such as AB page
labels, action descriptions, page descriptions, and intention step coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


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


def detect_repeated_actions(
    sample_dict: dict[str, Any],
    raw_oracle_result: dict[str, Any] | None = None,
    aligned_result: dict[str, Any] | None = None,
    config: RepeatedActionConfig | None = None,
) -> dict[str, Any]:
    """Detect repeated actions from an E2E payload and Darwin oracle result."""
    detector = RepeatedActionDetector(config or RepeatedActionConfig())
    return detector.detect(sample_dict, raw_oracle_result or {}, aligned_result or {})


class RepeatedActionDetector:
    def __init__(self, config: RepeatedActionConfig):
        self.config = config

    def detect(
        self,
        sample_dict: dict[str, Any],
        raw_oracle_result: dict[str, Any],
        aligned_result: dict[str, Any],
    ) -> dict[str, Any]:
        steps = self._build_steps(sample_dict, raw_oracle_result)
        if len(steps) < 2:
            return self._normal_result("动作序列过短，未发现重复动作。", len(steps))

        progress_by_step = self._build_progress_by_step(raw_oracle_result)
        ranges: list[dict[str, Any]] = []
        ranges.extend(self._detect_consecutive_repeats(steps, progress_by_step))
        ranges.extend(self._detect_wait_repeats(steps))
        ranges.extend(self._detect_swipe_repeats(steps, progress_by_step))
        ranges.extend(self._detect_short_loops(steps, progress_by_step))

        merged = self._merge_ranges(ranges)
        if not merged:
            return self._normal_result("未发现重复动作异常。", len(steps))

        severity = self._overall_severity(merged)
        confidence = max(item["confidence"] for item in merged)
        return {
            "label": "abnormal",
            "type": "repeated_action",
            "severity": severity,
            "confidence": round(confidence, 3),
            "ranges": merged,
            "summary": self._make_summary(merged),
            "metrics": {
                "action_count": len(steps),
                "repeated_range_count": len(merged),
            },
        }

    def _build_steps(self, sample_dict: dict[str, Any], raw_oracle_result: dict[str, Any]) -> list[dict[str, Any]]:
        seq_info = sample_dict.get("seq_info") or []
        ab_results = raw_oracle_result.get("ab_pages_result") or {}
        steps: list[dict[str, Any]] = []

        for pos, item in enumerate(seq_info):
            planning_output = item.get("planning_output") or {}
            parsed_action = planning_output.get("parsed_action") or {}
            action_type = self._normalize_text(parsed_action.get("action_type"))
            if not action_type:
                continue
            if action_type in {"finished", "done"}:
                continue  # 合成终止步骤，不算实际动作

            ab_result = ab_results.get(str(pos), {}) if isinstance(ab_results, dict) else {}
            action_des = ab_result.get("action_des") or parsed_action.get("text") or self._fallback_action_text(parsed_action)

            steps.append(
                {
                    "step": int(item.get("index", pos)),
                    "pos": pos,
                    "action_type": action_type,
                    "start_box": self._normalize_box(parsed_action.get("start_box")),
                    "end_box": self._normalize_box(parsed_action.get("end_box")),
                    "text": self._normalize_text(parsed_action.get("text")),
                    "direction": self._normalize_text(parsed_action.get("direction")),
                    "target": self._normalize_text(action_des),
                    "page_before": self._normalize_text(ab_result.get("pagea_description")),
                    "page_after": self._normalize_text(ab_result.get("pageb_description")),
                    "ab_label": self._normalize_text(ab_result.get("label")),
                    "ab_thought": self._normalize_text(ab_result.get("thought")),
                }
            )

        return steps

    def _build_progress_by_step(self, raw_oracle_result: dict[str, Any]) -> dict[int, int]:
        progress_points: list[int] = []
        for key in ("llm_intention_step", "vlm_intention_step"):
            step_results = raw_oracle_result.get(key)
            if not isinstance(step_results, dict):
                continue
            for item in step_results.values():
                if not isinstance(item, dict) or item.get("label") != "ok":
                    continue
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
            progress_by_step[step] = sum(1 for point in progress_points if point <= step)
        return progress_by_step

    def _detect_consecutive_repeats(
        self,
        steps: list[dict[str, Any]],
        progress_by_step: dict[int, int],
    ) -> list[dict[str, Any]]:
        ranges: list[dict[str, Any]] = []
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

                ranges.append(
                    self._range_result(
                        previous,
                        current,
                        "repeated_action",
                        self._repeat_confidence(previous, current),
                        [
                            f"步骤{previous['step']}和步骤{current['step']}动作等效",
                            f"目标控件/动作描述相似度{self._target_similarity(previous, current):.2f}",
                            "期间无新增检查点达成",
                            self._ab_evidence(current),
                        ],
                    )
                )
                break
        return ranges

    def _detect_wait_repeats(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranges: list[dict[str, Any]] = []
        start = None
        for i, step in enumerate(steps + [{"action_type": "__sentinel__", "step": -1}]):
            if step["action_type"] in {"wait", "do-nothing"}:
                if start is None:
                    start = i
                continue
            if start is not None and i - start >= self.config.consecutive_wait_threshold:
                first = steps[start]
                last = steps[i - 1]
                ranges.append(
                    self._range_result(
                        first,
                        last,
                        "repeated_wait",
                        0.72,
                        [
                            f"连续等待{i - start}次",
                            "连续 wait/do-nothing 通常表示页面停滞或 Agent 卡住",
                        ],
                    )
                )
            start = None
        return ranges

    def _detect_swipe_repeats(
        self,
        steps: list[dict[str, Any]],
        progress_by_step: dict[int, int],
    ) -> list[dict[str, Any]]:
        ranges: list[dict[str, Any]] = []
        start = None
        last_signature = None
        for i, step in enumerate(steps + [{"action_type": "__sentinel__", "step": -1}]):
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
                        ranges.append(
                            self._range_result(
                                first,
                                last,
                                "repeated_swipe",
                                0.68,
                                [
                                    f"连续同方向滑动{i - start}次",
                                    "期间无新增检查点达成",
                                ],
                            )
                        )
                start = None
            last_signature = signature
        return ranges

    def _detect_short_loops(
        self,
        steps: list[dict[str, Any]],
        progress_by_step: dict[int, int],
    ) -> list[dict[str, Any]]:
        ranges: list[dict[str, Any]] = []
        seen: dict[tuple[str, str], int] = {}
        for i, step in enumerate(steps):
            state_sig = self._state_signature(step)
            action_sig = self._action_signature(step)
            if not state_sig or not action_sig:
                continue

            key = (state_sig, action_sig)
            previous_idx = seen.get(key)
            if previous_idx is not None and 1 < i - previous_idx <= self.config.loop_window:
                previous = steps[previous_idx]
                if self._no_progress_between(previous, step, progress_by_step):
                    ranges.append(
                        self._range_result(
                            previous,
                            step,
                            "state_action_loop",
                            0.8,
                            [
                                f"步骤{previous['step']}到步骤{step['step']}出现相同页面状态和动作签名",
                                "短窗口内回到旧状态并执行等效动作",
                                "期间无新增检查点达成",
                            ],
                        )
                    )
            seen[key] = i
        return ranges

    def _equivalent_action(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left["action_type"] != right["action_type"]:
            click_types = {"click", "long_press"}
            if {left["action_type"], right["action_type"]} - click_types:
                return False

        action_type = right["action_type"]
        if action_type in {"click", "long_press"}:
            return self._same_target(left, right)
        if action_type in {"type", "set_text"}:
            return self._same_target(left, right) and self._similarity(left["text"], right["text"]) >= self.config.text_similarity_threshold
        if action_type in {"scroll", "swipe", "drag"}:
            return left["direction"] == right["direction"] and self._same_region(left.get("start_box"), right.get("start_box"))
        if action_type in {"wait", "do-nothing"}:
            return True
        return self._target_similarity(left, right) >= self.config.target_similarity_threshold

    def _same_target(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        return self._same_region(left.get("start_box"), right.get("start_box")) or (
            self._target_similarity(left, right) >= self.config.target_similarity_threshold
        )

    def _same_region(self, left_box: list[float] | None, right_box: list[float] | None) -> bool:
        if not left_box or not right_box or len(left_box) < 2 or len(right_box) < 2:
            return False
        distance = ((left_box[0] - right_box[0]) ** 2 + (left_box[1] - right_box[1]) ** 2) ** 0.5
        if max(abs(left_box[0]), abs(left_box[1]), abs(right_box[0]), abs(right_box[1])) <= 1:
            return distance <= self.config.coord_distance_normalized
        return distance <= self.config.coord_distance_px

    def _no_progress_between(
        self,
        previous: dict[str, Any],
        current: dict[str, Any],
        progress_by_step: dict[int, int],
    ) -> bool:
        previous_progress = progress_by_step.get(previous["step"], 0)
        current_progress = progress_by_step.get(current["step"], previous_progress)
        if current_progress > previous_progress:
            return False

        if current["ab_label"] in {"不符合预期", "无法判定"}:
            return True
        if self._page_similarity(previous, current) >= self.config.page_similarity_threshold:
            return True
        if current["ab_label"] == "符合预期":
            return False
        return True

    def _is_reasonable_repeat(self, previous: dict[str, Any], current: dict[str, Any], distance: int) -> bool:
        text = " ".join(
            [
                previous.get("target", ""),
                current.get("target", ""),
                previous.get("ab_thought", ""),
                current.get("ab_thought", ""),
            ]
        )
        if current["action_type"] in {"scroll", "swipe", "drag"}:
            return False
        if any(keyword in text for keyword in ("重试", "加载失败", "网络异常", "刷新")):
            return distance <= 2
        if any(keyword in text for keyword in ("多选", "勾选", "删除", "退格")):
            return True
        return False

    def _repeat_confidence(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
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

    def _range_result(
        self,
        first: dict[str, Any],
        last: dict[str, Any],
        repeated_type: str,
        confidence: float,
        evidence: list[str],
    ) -> dict[str, Any]:
        repeat_count = last["step"] - first["step"] + 1
        severity = "high" if repeat_count >= 4 else "medium" if repeat_count >= 3 else "low"
        return {
            "start_step": first["step"],
            "end_step": last["step"],
            "action_type": last["action_type"],
            "target": last.get("target") or self._fallback_action_text(last),
            "repeat_type": repeated_type,
            "severity": severity,
            "confidence": round(confidence, 3),
            "evidence": [item for item in evidence if item],
        }

    def _merge_ranges(self, ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not ranges:
            return []
        ranges = sorted(ranges, key=lambda item: (item["start_step"], item["end_step"], -item["confidence"]))
        merged: list[dict[str, Any]] = []
        for item in ranges:
            if not merged or item["start_step"] > merged[-1]["end_step"]:
                merged.append(item)
                continue
            current = merged[-1]
            current["end_step"] = max(current["end_step"], item["end_step"])
            current["confidence"] = max(current["confidence"], item["confidence"])
            current["severity"] = self._max_severity(current["severity"], item["severity"])
            current["evidence"] = self._dedupe(current["evidence"] + item["evidence"])
            if item["repeat_type"] not in current["repeat_type"]:
                current["repeat_type"] = f"{current['repeat_type']}+{item['repeat_type']}"
        return merged

    def _overall_severity(self, ranges: list[dict[str, Any]]) -> str:
        severity = "low"
        for item in ranges:
            severity = self._max_severity(severity, item["severity"])
        return severity

    def _max_severity(self, left: str, right: str) -> str:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        return left if order.get(left, 0) >= order.get(right, 0) else right

    def _make_summary(self, ranges: list[dict[str, Any]]) -> str:
        first = ranges[0]
        return (
            f"检测到{len(ranges)}段重复动作异常；首段位于步骤{first['start_step']}到"
            f"步骤{first['end_step']}，动作为{first['action_type']}，目标为{first['target']}。"
        )

    def _normal_result(self, summary: str, action_count: int) -> dict[str, Any]:
        return {
            "label": "normal",
            "type": "repeated_action",
            "severity": "none",
            "confidence": 0.0,
            "ranges": [],
            "summary": summary,
            "metrics": {
                "action_count": action_count,
                "repeated_range_count": 0,
            },
        }

    def _state_signature(self, step: dict[str, Any]) -> str:
        page_text = step.get("page_before") or step.get("page_after") or ""
        if not page_text:
            return ""
        return self._compact(page_text)[:120]

    def _action_signature(self, step: dict[str, Any]) -> str:
        return "|".join(
            [
                step.get("action_type", ""),
                self._compact(step.get("target", ""))[:60],
                step.get("direction", ""),
                step.get("text", ""),
            ]
        )

    def _target_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        return self._similarity(left.get("target", ""), right.get("target", ""))

    def _page_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        left_page = left.get("page_before") or left.get("page_after") or ""
        right_page = right.get("page_before") or right.get("page_after") or ""
        return self._similarity(left_page, right_page)

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
        return f"达尔文单步判定结果为{step['ab_label']}"

    def _fallback_action_text(self, parsed_action: dict[str, Any]) -> str:
        action_type = parsed_action.get("action_type", "")
        text = parsed_action.get("text", "")
        direction = parsed_action.get("direction", "")
        return " ".join(str(item) for item in (action_type, text, direction) if item)

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
        for value in values:
            if value and value not in result:
                result.append(value)
        return result
