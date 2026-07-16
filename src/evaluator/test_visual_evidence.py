"""Tests for screenshot/rawPage state evidence."""

from __future__ import annotations

import base64
import io

from PIL import Image

from src.evaluator.state_evidence import build_state_sequence
from src.evaluator.visual_evidence import compare_steps


def _img_b64(color: tuple[int, int, int]) -> str:
    image = Image.new("RGB", (32, 32), color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _step(index: int, image: str = "", ocr_index: int = -1) -> dict:
    return {
        "index": index,
        "image_relative_path": image,
        "_ocr_page_index": ocr_index,
        "planning_output": {
            "parsed_action": {
                "action_type": "click",
                "text": "点击入口",
            }
        },
    }


def test_visual_evidence_detects_screenshot_change():
    evidence = compare_steps(
        _step(0, _img_b64((0, 0, 0))),
        _step(1, _img_b64((255, 255, 255))),
        source_step_index=0,
        next_step_index=1,
    )

    assert evidence.has_before_image is True
    assert evidence.has_after_image is True
    assert evidence.pixel_diff_ratio == 1.0
    assert evidence.boundary_confidence > 0.3
    assert evidence.evidence_quality == "visual"


def test_state_sequence_uses_rawpage_change_without_screenshot():
    payload = {
        "task_uuid": "rawpage-case",
        "_ocr_pages": [
            {"nodes": [{"text": "首页", "bounds": [0, 0, 100, 100]}]},
            {"nodes": [{"text": "订单列表", "bounds": [0, 0, 100, 100]}]},
            {"nodes": [{"text": "订单列表", "bounds": [0, 0, 100, 100]}]},
        ],
        "seq_info": [
            _step(0, "", 0),
            _step(1, "", 1),
            {
                "index": 2,
                "image_relative_path": "",
                "_ocr_page_index": 2,
                "planning_output": {
                    "parsed_action": {
                        "action_type": "finished",
                        "text": "任务完成",
                    }
                },
            },
        ],
    }

    sequence = build_state_sequence(payload)

    assert sequence.evidence_quality == "visual"
    assert sequence.progress_steps == [0]
    assert sequence.transitions[0].visual_evidence["rawpage_changed"] is True
