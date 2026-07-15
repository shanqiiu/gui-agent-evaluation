"""Unit tests for trajectory differential judger.

Covers the three deviation types:
    no_impact  — clean trajectory, different path same result
    remedial   — early suboptimal, self-corrected via backtrack
    cascading  — initial error propagated, task failed
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.trajectory import (
    DifferentialJudger,
    DifferentialJudgerConfig,
    judge_trajectory,
)


def _make_step(index: int, action_type: str, text: str = "", ab_label: str = "ok") -> dict:
    return {
        "index": index,
        "planning_output": {
            "parsed_action": {
                "action_type": action_type,
                "start_box": [100, 200],
                "text": text,
                "direction": "",
                "content": "",
            }
        },
        "image_relative_path": "",
        "_image_source": "",
    }


def _make_darwin(intention_ok: bool, plan_coverage: float = 1.0,
                 ab_labels: dict | None = None,
                 intention_steps: dict | None = None) -> dict:
    return {
        "intention": {"label": "ok" if intention_ok else "nok"},
        "ab_pages_result": ab_labels or {},
        "llm_intention_step": intention_steps or {},
    }


# ── Test: No-impact deviation ──────────────────────────────────

def test_no_impact_clean():
    """Clean trajectory: all steps OK, no deviations."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "scroll", "向下滑动", "ok"),
        _make_step(2, "click", "点击隐私和安全", "ok"),
        _make_step(3, "click", "点击密码保险箱", "ok"),
    ]
    payload = {"task_uuid": "test-1", "instruction": "打开密码保险箱", "seq_info": seq_info}
    darwin = _make_darwin(intention_ok=True, plan_coverage=1.0)

    result = judge_trajectory(payload, darwin)
    assert result.deviation_class == "no_impact", f"Expected no_impact, got {result.deviation_class}"
    assert result.deviation_count == 0
    assert result.final_outcome_ok
    print("  PASS: no_impact — clean trajectory")


def test_no_impact_different_path():
    """Different path but same result: agent scrolled more but found target."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "scroll", "向下滑动", "ok"),
        _make_step(2, "scroll", "向下滑动", "ok"),  # extra scroll
        _make_step(3, "scroll", "向下滑动", "ok"),  # extra scroll
        _make_step(4, "click", "点击目标", "ok"),
    ]
    payload = {"task_uuid": "test-2", "instruction": "找到目标", "seq_info": seq_info}
    darwin = _make_darwin(intention_ok=True, plan_coverage=1.0)

    result = judge_trajectory(payload, darwin)
    assert result.deviation_class == "no_impact", f"Expected no_impact, got {result.deviation_class}"
    print("  PASS: no_impact — different path, same result")


# ── Test: Remedial deviation ───────────────────────────────────

def test_remedial_self_corrected():
    """Agent clicked wrong button, went back, clicked correct one."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "click", "点击错误按钮", "nok"),  # wrong!
        _make_step(2, "back", "返回", "ok"),              # self-correct
        _make_step(3, "click", "点击正确按钮", "ok"),     # correct
    ]
    payload = {"task_uuid": "test-3", "instruction": "点击正确按钮", "seq_info": seq_info}
    darwin = _make_darwin(
        intention_ok=True, plan_coverage=1.0,
        ab_labels={
            "0": {"label": "ok"},
            "1": {"label": "nok"},
            "2": {"label": "ok"},
            "3": {"label": "ok"},
        },
    )

    result = judge_trajectory(payload, darwin)
    assert result.deviation_class == "remedial", f"Expected remedial, got {result.deviation_class}"
    assert result.recovery_count > 0, "Should have self-correction detected"
    assert result.final_outcome_ok
    print("  PASS: remedial — self-corrected after wrong click")


def test_remedial_repeated_then_corrected():
    """Agent repeated action, then backtracked and corrected."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "click", "点击按钮", "ok"),
        _make_step(2, "click", "点击按钮", "nok"),  # repeat
        _make_step(3, "back", "返回", "ok"),         # correct
        _make_step(4, "click", "点击正确目标", "ok"),
    ]
    payload = {"task_uuid": "test-4", "instruction": "完成任务", "seq_info": seq_info}
    darwin = _make_darwin(
        intention_ok=True, plan_coverage=0.9,
        ab_labels={
            "0": {"label": "ok"},
            "1": {"label": "ok"},
            "2": {"label": "nok"},
            "3": {"label": "ok"},
            "4": {"label": "ok"},
        },
    )
    repeated = {
        "ranges": [{
            "start_step": 1, "end_step": 2,
            "action_type": "click", "target": "点击按钮"
        }]
    }

    result = judge_trajectory(payload, darwin, repeated_action_result=repeated)
    assert result.deviation_class in ("remedial", "no_impact"), \
        f"Expected remedial, got {result.deviation_class}"
    print(f"  PASS: remedial — repeated then corrected (class={result.deviation_class})")


# ── Test: Cascading deviation ──────────────────────────────────

def test_cascading_error_propagation():
    """Early grounding error cascaded into complete failure."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "click", "误点错误入口", "nok"),     # FES
        _make_step(2, "scroll", "在错误页面滑动", "nok"),   # cascaded
        _make_step(3, "click", "点击无关节按钮", "nok"),    # cascaded
        _make_step(4, "click", "仍无法找到目标", "nok"),    # cascaded
    ]
    payload = {"task_uuid": "test-5", "instruction": "完成设置", "seq_info": seq_info}
    darwin = _make_darwin(
        intention_ok=False, plan_coverage=0.3,
        ab_labels={
            "0": {"label": "ok"},
            "1": {"label": "nok"},
            "2": {"label": "nok"},
            "3": {"label": "nok"},
            "4": {"label": "nok"},
        },
    )

    result = judge_trajectory(payload, darwin)
    assert result.deviation_class == "cascading", f"Expected cascading, got {result.deviation_class}"
    assert result.first_error_step is not None
    assert not result.final_outcome_ok
    assert result.cascaded
    print(f"  PASS: cascading — error propagated, FES={result.first_error_step}")


def test_cascading_low_coverage():
    """Plan coverage below threshold → cascading."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "click", "点击", "ok"),
    ]
    payload = {"task_uuid": "test-6", "instruction": "打开密码保险箱", "seq_info": seq_info}
    darwin = _make_darwin(intention_ok=False, plan_coverage=0.3)

    result = judge_trajectory(payload, darwin)
    assert result.deviation_class == "cascading"
    print(f"  PASS: cascading — low plan coverage ({result.plan_coverage:.0%})")


# ── Test: Planning failure + cascading ─────────────────────────

def test_cascading_with_planning_failure():
    """Planning failure combined with cascading deviations."""
    seq_info = [
        _make_step(0, "open_app", "打开应用", "ok"),
        _make_step(1, "click", "点击", "nok"),
        _make_step(2, "click", "点击", "nok"),
    ]
    payload = {"task_uuid": "test-7", "instruction": "完成任务", "seq_info": seq_info}
    darwin = _make_darwin(
        intention_ok=False, plan_coverage=0.4,
        ab_labels={
            "0": {"label": "ok"},
            "1": {"label": "nok"},
            "2": {"label": "nok"},
        },
    )
    planning = {
        "label": "abnormal",
        "subtype": "missing_required_step",
        "events": [{"subtype": "missing_required_step"}],
    }

    result = judge_trajectory(payload, darwin, planning_failure_result=planning)
    assert result.deviation_class == "cascading"
    print("  PASS: cascading — with planning failure")


# ── Test: to_dict serialization ─────────────────────────────────

def test_to_dict():
    """Verify to_dict produces valid output."""
    seq_info = [_make_step(0, "open_app", "打开", "ok")]
    payload = {"task_uuid": "test-8", "instruction": "测试", "seq_info": seq_info}
    darwin = _make_darwin(intention_ok=True)

    result = judge_trajectory(payload, darwin)
    d = result.to_dict()
    assert d["task_uuid"] == "test-8"
    assert d["deviation_class"] in ("no_impact", "remedial", "cascading")
    assert "deviations" in d
    assert "evidence" in d
    print("  PASS: to_dict — valid output")


# ── Runner ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Trajectory Differential Judger — Unit Tests")
    print("=" * 60)

    tests = [
        ("no_impact — clean", test_no_impact_clean),
        ("no_impact — different path", test_no_impact_different_path),
        ("remedial — self-corrected", test_remedial_self_corrected),
        ("remedial — repeated + correct", test_remedial_repeated_then_corrected),
        ("cascading — error propagation", test_cascading_error_propagation),
        ("cascading — low coverage", test_cascading_low_coverage),
        ("cascading — with planning failure", test_cascading_with_planning_failure),
        ("to_dict serialization", test_to_dict),
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
