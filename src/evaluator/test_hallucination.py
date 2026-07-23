"""Tests for hallucination detection."""

from __future__ import annotations

from src.evaluator.hallucination import HallucinationEvent, detect_hallucinations


# ── helpers ──────────────────────────────────────────────────────────


def _payload_with_ocr(
    ocr_pages: list[dict] | None = None,
    seq_info: list[dict] | None = None,
) -> dict:
    return {
        "_ocr_pages": ocr_pages or [],
        "seq_info": seq_info or [],
    }


def _state_seq_single(
    purposes: list[str],
    page_desc: str = "",
    label: str = "",
    step_range: tuple[int, int] = (0, 1),
    action_types: list[str] | None = None,
) -> dict:
    return {
        "states": [
            {
                "label": label,
                "step_range": list(step_range),
                "source_step_indices": list(step_range),
                "action_purposes": purposes,
                "action_types": action_types or ["click"],
                "page_description": page_desc,
            }
        ]
    }


# ── non_existent_element ─────────────────────────────────────────────


def test_non_existent_element_detected() -> None:
    payload = _payload_with_ocr()
    state_seq = _state_seq_single(
        purposes=["点击设置按钮", "进入设置页面"],
        page_desc="当前页面为首页，显示搜索栏和推荐内容",
        label="home page",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    assert len(events) >= 1
    evt = events[0]
    assert evt.subtype == "non_existent_element"
    assert "设置按钮" in evt.message


def test_non_existent_element_not_detected_when_in_ocr() -> None:
    payload = _payload_with_ocr(
        ocr_pages=[
            {
                "turnId": 0,
                "content": "设置按钮 个人中心 关于我们",
            }
        ]
    )
    state_seq = _state_seq_single(
        purposes=["点击设置按钮"],
        page_desc="settings page containing 设置按钮",
        label="settings",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    # OCR confirms the element exists — no hallucination
    assert len(events) == 0


def test_non_existent_english_element() -> None:
    payload = _payload_with_ocr()
    state_seq = _state_seq_single(
        purposes=["click the submit button", "then press save"],
        page_desc="main page with navigation bar only",
        label="main page",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    assert len(events) >= 1
    evt = events[0]
    assert evt.subtype == "non_existent_element"
    assert "submit button" in evt.message.lower()


# ── wrong_page_understanding ─────────────────────────────────────────


def test_wrong_page_understanding_detected() -> None:
    payload = _payload_with_ocr(
        ocr_pages=[
            {
                "turnId": 0,
                "content": "首页 搜索 推荐商品 热门活动",
            }
        ]
    )
    state_seq = _state_seq_single(
        purposes=["已到达设置页面，开始修改密码"],
        page_desc="settings page, modifying password now",
        label="settings state",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    # Agent claims "设置页面" but OCR shows "首页"
    assert len(events) >= 1
    subtypes = {e.subtype for e in events}
    # At minimum we should have wrong_page_understanding
    assert "wrong_page_understanding" in subtypes


def test_wrong_page_not_detected_when_confirmed() -> None:
    payload = _payload_with_ocr(
        ocr_pages=[
            {
                "turnId": 0,
                "content": "设置 修改密码 账号管理 退出登录",
            }
        ]
    )
    state_seq = _state_seq_single(
        purposes=["已到达设置页面，开始修改密码"],
        page_desc="设置页面 showing user config options",
        label="settings",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    subtypes = {e.subtype for e in events}
    # Page IS confirmed — wrong_page_understanding should NOT fire
    assert "wrong_page_understanding" not in subtypes


# ── fabricated_capability ────────────────────────────────────────────


def test_fabricated_scroll_capability_detected() -> None:
    payload = _payload_with_ocr(
        ocr_pages=[
            {
                "turnId": 0,
                "content": "设置 版本信息 退出",
            }
        ]
    )
    state_seq = _state_seq_single(
        purposes=["swipe to next page to see more options"],
        page_desc="settings page with limited options",
        label="settings",
        action_types=["swipe"],
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    assert len(events) >= 1
    subtypes = {e.subtype for e in events}
    assert "fabricated_capability" in subtypes, f"Expected fabricated_capability in {subtypes}"


def test_scroll_capability_not_fabricated_when_content_exists() -> None:
    payload = _payload_with_ocr(
        ocr_pages=[
            {
                "turnId": 0,
                "content": "商品列表 加载更多 滑动查看更多 继续滑动",
            }
        ]
    )
    state_seq = _state_seq_single(
        purposes=["scroll to next page to load more products"],
        page_desc="product list with load more",
        label="product list",
        action_types=["swipe"],
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    subtypes = {e.subtype for e in events}
    assert "fabricated_capability" not in subtypes


def test_fabricated_tap_on_unavailable() -> None:
    payload = _payload_with_ocr()
    state_seq = _state_seq_single(
        purposes=["tap the non-existent save button"],
        page_desc="view-only page",
        label="readonly page",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)

    assert len(events) >= 1
    # Should have both non_existent_element AND fabricated_capability
    subtypes = {e.subtype for e in events}
    assert "fabricated_capability" in subtypes


# ── edge cases ───────────────────────────────────────────────────────


def test_no_events_without_state_sequence() -> None:
    events = detect_hallucinations(_payload_with_ocr(), state_sequence=None)
    assert len(events) == 0


def test_no_events_with_empty_purposes() -> None:
    payload = _payload_with_ocr()
    state_seq = _state_seq_single(
        purposes=[],
        page_desc="any page",
    )

    events = detect_hallucinations(payload, state_sequence=state_seq)
    assert len(events) == 0


def test_hallucination_event_to_dict() -> None:
    evt = HallucinationEvent(
        subtype="non_existent_element",
        confidence=0.72,
        first_error_step=5,
        evidence_refs=["state_sequence.states[2]"],
        message="element not found in OCR",
    )
    d = evt.to_dict()
    assert d["category"] == "hallucination"
    assert d["subtype"] == "non_existent_element"
    assert d["first_error_step"] == 5
    assert d["end_step"] == 5  # defaults to first_error_step
    assert d["confidence"] == 0.72
    assert d["recovery_outcome"] == "unknown"
