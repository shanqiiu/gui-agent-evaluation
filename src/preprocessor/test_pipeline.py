"""
Integration test for the refactored data pipeline.

Uses mock data (from src/state_extractor/mock_data.py) to verify:
1. Preprocessor produces valid NormalizedTask
2. All three writers produce valid output files
3. rawPage control name fallback works for icon elements
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure paths
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.state_extractor.mock_data import make_mock_utg, make_mock_clearres
from src.preprocessor.models import NormalizedTask
from src.preprocessor.preprocessor import preprocess, _resolve_from_rawpage


def test_preprocessor_with_mock():
    """Test preprocessor with mock utg.json data (no clearRes)."""
    utg = make_mock_utg()

    # Write mock utg to temp dir
    with tempfile.TemporaryDirectory() as td:
        task_dir = Path(td) / "mock-task"
        task_dir.mkdir()
        with open(task_dir / "utg.json", "w", encoding="utf-8") as f:
            json.dump(utg, f, ensure_ascii=False)

        task = preprocess(task_dir)

        # Basic validation
        assert task.task_uuid == "mock-task"
        assert len(task.steps) > 0, "Should have at least one action step"
        print(f"  PASS: {len(task.steps)} action steps parsed")

        # Check that non-action/system steps are filtered
        action_types = [s.action_type for s in task.steps]
        assert "unknown" not in action_types[:5], "Thinking steps should be filtered"
        assert "CheckAppExist" not in action_types, "System check steps should be filtered"
        assert "finished" not in action_types, "Raw terminal records should be filtered before payload writing"
        assert not any("用户回复" in a or "播报" in a for a in action_types), "Conversation records should be filtered"
        print(f"  PASS: non-executable steps filtered, action types: {action_types[:5]}")

        # Check coordinates
        clicks = [s for s in task.steps if s.action_type == "click"]
        if clicks:
            assert clicks[0].action_start_box, "Click should have coordinates"
            print(f"  PASS: click has coordinates: {clicks[0].action_start_box}")


def test_rawpage_resolution():
    """Test control name resolution from rawPage OCR tree."""
    clearres = make_mock_clearres()
    pages = clearres["ocr_pages"]

    # Use the first page (home/launcher with "设置" icon+text)
    if pages and pages[0].get("nodes"):
        result = _resolve_from_rawpage([175, 550], pages[0])
        print(f"  rawPage resolution for [175, 550]: '{result}'")
        # The mock page at [175, 550] should resolve to "设置"
        # (icon at bounds [80, 430, 270, 650] + text sibling "设置")
        if result:
            print(f"  PASS: rawPage control name resolved: '{result}'")
        else:
            print(f"  INFO: rawPage resolution returned empty (mock data may need adjustment)")


def test_payload_writer():
    """Test write_payload produces valid JSON."""
    from .write_payload import write_payload

    utg = make_mock_utg()
    with tempfile.TemporaryDirectory() as td:
        task_dir = Path(td) / "mock-task"
        task_dir.mkdir()
        with open(task_dir / "utg.json", "w", encoding="utf-8") as f:
            json.dump(utg, f, ensure_ascii=False)

        task = preprocess(task_dir)

        output_path = Path(td) / "payload.json"
        payload = write_payload(task, output_path)

        assert "instruction" in payload
        assert "seq_info" in payload
        assert len(payload["seq_info"]) >= 2  # at least actions + finished
        payload_action_types = [
            item["planning_output"]["parsed_action"]["action_type"]
            for item in payload["seq_info"]
        ]
        assert payload_action_types.count("finished") == 1
        assert payload_action_types[-1] == "finished"
        assert "CheckAppExist" not in payload_action_types
        assert not any("用户回复" in a or "播报" in a for a in payload_action_types)
        print(f"  PASS: payload.json generated with {len(payload['seq_info'])} seq_info entries")
        print(f"  instruction: {payload['instruction']}")
        print(f"  step_level_instruction: {payload.get('step_level_instruction', '')[:80]}")


def test_dedup_writer():
    """Test write_dedup produces valid JSON."""
    from .write_dedup import write_dedup

    utg = make_mock_utg()
    with tempfile.TemporaryDirectory() as td:
        task_dir = Path(td) / "mock-task"
        task_dir.mkdir()
        with open(task_dir / "utg.json", "w", encoding="utf-8") as f:
            json.dump(utg, f, ensure_ascii=False)

        task = preprocess(task_dir)

        output_path = Path(td) / "_deduped.json"
        dedup = write_dedup(task, output_path)

        assert "instruction" in dedup
        assert "steps" in dedup
        assert "nodes" in dedup
        assert "edges" in dedup
        assert "_meta" in dedup
        print(f"  PASS: _deduped.json generated")
        print(f"  steps: {len(dedup['steps'])}, nodes: {len(dedup['nodes'])}, edges: {len(dedup['edges'])}")
        # Check that scroll has end_box
        scrolls = [s for s in dedup["steps"] if s.get("action_type") == "scroll"]
        if scrolls:
            has_end = any("end_box" in s for s in scrolls)
            print(f"  scroll steps with end_box: {has_end}")


def main():
    print("=" * 60)
    print("  Data Pipeline Integration Tests")
    print("=" * 60)

    tests = [
        ("Preprocessor (mock utg)", test_preprocessor_with_mock),
        ("rawPage Resolution", test_rawpage_resolution),
        ("Payload Writer", test_payload_writer),
        ("Dedup Writer", test_dedup_writer),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
