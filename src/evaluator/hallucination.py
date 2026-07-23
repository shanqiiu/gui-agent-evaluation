"""Hallucination detection for GUI Agent evaluation.

A hallucination occurs when the agent's understanding of the UI state
contradicts observable evidence: it references elements or states that
the OCR, page description, or visual evidence cannot confirm.

This module is rule-based: it compares agent action_purposes and
page_descriptions against OCR evidence and state descriptions without
making additional VLM/LLM calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Chinese element-mention patterns: what agents commonly name ──

_ELEMENT_MENTION_RE = re.compile(
    r"([\u4e00-\u9fff\w]{2,16}(?:按钮|图标|入口|选项|标签|卡片|弹窗|对话框"
    r"|菜单|列表|搜索框|输入框|文本框|滑块|开关|复选框|单选框"
    r"|页|页面|界面|模块|区域|栏|通道|方式|功能|设置"
    r"))",
)

# Generic action verbs that should NOT be treated as element mentions
_ACTION_VERB_PREFIXES: frozenset[str] = frozenset({
    "点击", "滑动", "输入", "选择", "打开", "进入", "返回", "关闭",
    "切换", "确认", "取消", "提交", "保存", "搜索", "筛选",
    "click", "tap", "press", "select", "open", "close", "swipe",
    "scroll", "type", "enter", "search", "save", "submit", "cancel",
    "confirm",
})


def _clean_element(element: str) -> str:
    """Strip common action verb prefixes from a matched element name."""
    el_lower = element.lower()
    for prefix in _ACTION_VERB_PREFIXES:
        if el_lower.startswith(prefix.lower()):
            stripped = element[len(prefix):]
            if len(stripped) >= 2:
                return stripped
    return element

# English element patterns
_EN_ELEMENT_MENTION_RE = re.compile(
    r"\b(click|tap|press|select|open|close|swipe|scroll|type|enter|search|save|submit|cancel|confirm)"
    r"\s+(?:the\s+)?([\w\s-]{2,40}?(?:button|icon|tab|menu|field|bar|link|option|card|dialog|modal|screen|page|panel|list))"
    r"|(?:on|at)\s+the\s+([\w\s-]{2,40}?(?:page|screen|view|tab|panel|section|menu|dialog|modal))",
    re.IGNORECASE,
)

# ── Capability-to-element mapping ──

_FABRICATED_SCROLL_SIGNALS = (
    "swipe to next",
    "swipe to previous",
    "scroll to next page",
    "swipe left",
    "swipe right",
    "scroll further",
)

_FABRICATED_TAP_SIGNALS = (
    "tap the non-existent",
    "click on the unavailable",
    "press the disabled",
)


@dataclass
class HallucinationEvent:
    subtype: str
    confidence: float
    first_error_step: int
    end_step: int = -1
    related_subtask_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": "hallucination",
            "subtype": self.subtype,
            "first_error_step": self.first_error_step,
            "end_step": self.end_step if self.end_step >= 0 else self.first_error_step,
            "related_subtask_id": self.related_subtask_id,
            "evidence_refs": self.evidence_refs,
            "message": self.message,
            "recovery_outcome": "unknown",
            "impact": "unknown",
            "confidence": round(self.confidence, 3),
        }


def detect_hallucinations(
    payload: dict[str, Any],
    *,
    state_sequence: Any = None,
) -> list[HallucinationEvent]:
    """Detect hallucinations from baseline pipeline evidence.

    Returns a list of HallucinationEvent objects, one per detected
    hallucination.
    """
    events: list[HallucinationEvent] = []
    states = _state_items(state_sequence)
    ocr_by_page = _ocr_index(payload)

    for state_idx, state in enumerate(states):
        step_range = _step_range(state)
        first_step = step_range[0] if step_range else -1
        if first_step < 0:
            continue

        purposes = _safe_list(state.get("action_purposes"))
        page_desc = str(state.get("page_description") or "").strip()
        label = str(state.get("label") or "").strip()

        # Build the observable text corpus for this state
        ocr_texts: list[str] = []
        for s in range(step_range[0], step_range[1] + 1) if step_range else []:
            ocr_texts.append(ocr_by_page.get(s, ""))
        observable_text = " ".join(filter(None, [page_desc, label, *ocr_texts]))

        # ── non_existent_element ──
        for purpose in purposes:
            mentioned = _extract_mentioned_elements(str(purpose))
            for elem in mentioned:
                if not _element_in_text(elem, observable_text):
                    events.append(HallucinationEvent(
                        subtype="non_existent_element",
                        confidence=0.72,
                        first_error_step=first_step,
                        evidence_refs=[f"state_sequence.states[{state_idx}]"],
                        message=f"agent referenced '{elem}' in action_purpose, "
                                f"not found in OCR or page_description: '{purpose[:80]}'",
                    ))
                    break  # one event per state is sufficient

        # ── wrong_page_understanding ──
        if page_desc and purposes:
            claimed_page = _extract_claimed_page(purposes, page_desc)
            if claimed_page and not _page_confirmed(claimed_page, observable_text):
                events.append(HallucinationEvent(
                    subtype="wrong_page_understanding",
                    confidence=0.68,
                    first_error_step=first_step,
                    evidence_refs=[f"state_sequence.states[{state_idx}]"],
                    message=f"agent claimed to be on '{claimed_page}', "
                            f"but page evidence does not confirm this",
                ))

        # ── fabricated_capability ──
        for purpose in purposes:
            p = str(purpose).lower()
            if any(sig in p for sig in _FABRICATED_SCROLL_SIGNALS):
                if _has_scroll_content(observable_text):
                    continue  # scrolling is legitimate
                events.append(HallucinationEvent(
                    subtype="fabricated_capability",
                    confidence=0.65,
                    first_error_step=first_step,
                    evidence_refs=[f"state_sequence.states[{state_idx}]"],
                    message=f"agent attempted scroll/next-page when page shows "
                            f"no scrollable content: '{p[:80]}'",
                ))
                break

            if any(sig in p for sig in _FABRICATED_TAP_SIGNALS):
                events.append(HallucinationEvent(
                    subtype="fabricated_capability",
                    confidence=0.64,
                    first_error_step=first_step,
                    evidence_refs=[f"state_sequence.states[{state_idx}]"],
                    message=f"agent explicitly referenced unavailable element: '{p[:80]}'",
                ))
                break

    return events


# ── helpers ──────────────────────────────────────────────────────────


def _state_items(sequence: Any) -> list[dict[str, Any]]:
    if sequence is None:
        return []
    if hasattr(sequence, "to_dict"):
        sequence = sequence.to_dict()
    if not isinstance(sequence, dict):
        return []
    return [item for item in sequence.get("states") or [] if isinstance(item, dict)]


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _step_range(state: dict[str, Any]) -> list[int]:
    rng = state.get("step_range")
    if isinstance(rng, list) and len(rng) >= 2:
        return [int(rng[0]), int(rng[1])]
    source = state.get("source_step_indices")
    if isinstance(source, list) and source:
        return [int(source[0]), int(source[-1])]
    return []


def _ocr_index(payload: dict[str, Any]) -> dict[int, str]:
    """Build step→OCR text index from _ocr_pages."""
    index: dict[int, str] = {}
    ocr_pages = payload.get("_ocr_pages") or []
    if not isinstance(ocr_pages, list):
        return index
    for page in ocr_pages:
        if not isinstance(page, dict):
            continue
        step = -1
        for key in ("turnId", "step_index", "index", "turn"):
            val = page.get(key)
            if isinstance(val, int):
                step = val
                break
            if isinstance(val, str) and val.isdigit():
                step = int(val)
                break
        if step < 0:
            continue
        texts: list[str] = []
        content = page.get("content") or page.get("text") or page.get("ocr_text") or ""
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    texts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    texts.append(str(item))
        index[step] = " ".join(texts)
    return index


def _extract_mentioned_elements(text: str) -> list[str]:
    """Extract named UI elements from agent text."""
    elements: list[str] = []
    # Chinese patterns
    for match in _ELEMENT_MENTION_RE.finditer(text):
        group = match.group(1)
        if group and len(group) >= 2 and group.lower() not in _ACTION_VERB_PREFIXES:
            elements.append(_clean_element(group))
    # English patterns
    for match in _EN_ELEMENT_MENTION_RE.finditer(text):
        elem = match.group(2) or match.group(3)
        if elem:
            elem = elem.strip()
            if len(elem) >= 3:
                elements.append(elem)
    return _dedupe(elements)


def _element_in_text(element: str, corpus: str) -> bool:
    """Check if element name appears in observable text corpus."""
    if not element or not corpus:
        return False
    # Direct substring match (case-insensitive)
    if element.lower() in corpus.lower():
        return True
    # Also check partial: if element is "设置按钮", check if "设置" exists
    # alongside a button-type word
    shorter = re.sub(r"(按钮|图标|入口|选项|标签|卡片|弹窗|对话框|菜单|列表|搜索框|输入框|文本框|滑块|开关|复选框|单选框|页|页面|界面|模块|区域|栏|通道|方式|功能|设置)$", "", element)
    if len(shorter) >= 2 and shorter.lower() in corpus.lower():
        return True
    return False


def _extract_claimed_page(purposes: list[Any], page_desc: str) -> str:
    """Extract what page the agent claims to be on."""
    combined = " ".join(str(p) for p in purposes) + " " + page_desc
    # Heuristic: look for page-claiming patterns
    patterns = [
        r"在([\u4e00-\u9fff\w]{2,20}(?:页|页面|界面|模块|功能))",
        r"(?:进入|到达|来到|打开|已在|位于)([\u4e00-\u9fff\w]{2,20}(?:页|页面|界面))",
        r"on the ([\w\s]{2,30}?(?:page|screen|view|tab|panel))",
        r"(?:at|in|on)\s+([\w\s]{2,30}?(?:page|screen|view))",
    ]
    for pat in patterns:
        match = re.search(pat, combined)
        if match:
            return match.group(1).strip()
    return ""


def _page_confirmed(claimed: str, observable: str) -> bool:
    """Check if the claimed page can be confirmed in observable text."""
    if not claimed or not observable:
        return False
    if claimed.lower() in observable.lower():
        return True
    # For Chinese: try matching core keyword (strip "页/页面/界面")
    core = re.sub(r"(页|页面|界面|模块)$", "", claimed)
    if core and len(core) >= 2 and core in observable:
        return True
    return False


def _has_scroll_content(text: str) -> bool:
    """Check if observable text indicates scrollable content."""
    scroll_signals = [
        "查看更多", "加载更多", "查看更多内容",
        "更多结果", "更多商品", "更多", "查看更多",
        "向上滑动", "向下滑动", "滑动查看更多",
        "load more", "show more", "scroll",
        "更多推荐", "继续滑动",
    ]
    text_lower = text.lower()
    for sig in scroll_signals:
        if sig.lower() in text_lower:
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for v in values:
        if v and v not in result:
            result.append(v)
    return result
