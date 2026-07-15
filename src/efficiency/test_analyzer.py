"""Unit tests for efficiency analyzer.

Coverage:
    - Clean trajectory → efficient
    - Ineffective actions → lowered score
    - Exploration clusters → overhead penalty
    - Navigation loops → redundancy penalty
    - Scroll-only trajectory → low scroll efficiency
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.efficiency import (
    EfficiencyAnalyzer,
    EfficiencyConfig,
    analyze_efficiency,
)


def _step(idx: int, action_type: str, ab_label: str = "ok",
          text: str = "", page_before: str = "", page_after: str = "") -> dict:
    return {
        "index": idx,
        "planning_output": {
            "parsed_action": {
                "action_type": action_type,
                "start_box": [100, 200],
                "text": text,
                "direction": "down" if action_type == "scroll" else "",
                "content": "",
            }
        },
        "image_relative_path": "",
        "_image_source": "",
    }


def _darwin(ab_labels: dict | None = None) -> dict:
    result = {"ab_pages_result": {}}
    if ab_labels:
        for k, v in ab_labels.items():
            result["ab_pages_result"][str(k)] = v
    return result


# ── Tests ──────────────────────────────────────────────────────

def test_efficient_clean():
    """Clean, minimal trajectory should be efficient."""
    seq = [
        _step(0, "open_app", text="打开应用"),
        _step(1, "click", text="点击目标"),
    ]
    payload = {"task_uuid": "t1", "instruction": "测试", "seq_info": seq}
    darwin = _darwin({"0": {"label": "ok"}, "1": {"label": "ok"}})
    r = analyze_efficiency(payload, darwin)
    assert r.efficiency_label == "efficient", f"Got {r.efficiency_label}"
    assert r.ineffective_rate == 0.0
    print("  PASS: efficient clean")


def test_ineffective_actions():
    """AB nok should increase ineffective rate."""
    seq = [
        _step(0, "click", "nok", text="误点"),
        _step(1, "click", "ok", text="正确点击"),
    ]
    payload = {"task_uuid": "t2", "instruction": "测试", "seq_info": seq}
    darwin = _darwin({"0": {"label": "nok"}, "1": {"label": "ok"}})
    r = analyze_efficiency(payload, darwin)
    assert r.ineffective_rate > 0, f"Ineffective rate: {r.ineffective_rate}"
    assert r.ineffective_steps == 1
    assert r.overall_efficiency < 1.0
    print(f"  PASS: ineffective_rate={r.ineffective_rate}, overall={r.overall_efficiency:.2f}")


def test_exploration_cluster():
    """4+ consecutive scrolls → exploration cluster."""
    seq = [
        _step(0, "open_app", text="打开"),
        _step(1, "scroll", text="滑动"),
        _step(2, "scroll", text="滑动"),
        _step(3, "scroll", text="滑动"),
        _step(4, "scroll", text="滑动"),
        _step(5, "click", "ok", text="找到目标"),
    ]
    payload = {"task_uuid": "t3", "instruction": "测试", "seq_info": seq,
               "step_level_instruction": "打开->点击"}
    darwin = _darwin({str(i): {"label": "ok"} for i in range(6)})
    r = analyze_efficiency(payload, darwin)
    assert len(r.exploration_clusters) >= 1, f"Clusters: {len(r.exploration_clusters)}"
    assert r.exploratory_overhead > 0
    print(f"  PASS: clusters={len(r.exploration_clusters)}, overhead={r.exploratory_overhead:.2f}")


def test_navigation_loops():
    """Back to same page → navigation loop."""
    seq = [
        _step(0, "click", "ok", page_before="首页", page_after="搜索页"),
        _step(1, "back", "ok", page_before="搜索页", page_after="首页"),
        _step(2, "click", "ok", page_before="首页", page_after="设置页"),
        _step(3, "back", "ok", page_before="设置页", page_after="首页"),
    ]
    payload = {"task_uuid": "t4", "instruction": "测试", "seq_info": seq}
    darwin = _darwin({str(i): {"label": "ok"} for i in range(4)})
    r = analyze_efficiency(payload, darwin)
    assert r.back_steps == 2
    print(f"  PASS: back_steps={r.back_steps}, redundancy={r.navigation_redundancy:.2f}")


def test_scroll_inefficiency():
    """Many scrolls, no clicks → low scroll efficiency."""
    seq = [
        _step(0, "scroll", text="滑动"),
        _step(1, "scroll", text="滑动"),
        _step(2, "scroll", text="滑动"),
        _step(3, "scroll", text="滑动"),
    ]
    payload = {"task_uuid": "t5", "instruction": "测试", "seq_info": seq}
    darwin = _darwin({str(i): {"label": "ok"} for i in range(4)})
    r = analyze_efficiency(payload, darwin)
    assert r.scroll_efficiency < 1.0, f"scroll_eff: {r.scroll_efficiency}"
    assert r.scroll_steps == 4
    print(f"  PASS: scroll_eff={r.scroll_efficiency:.2f}")


def test_inefficient_overall():
    """Combination of issues → inefficient."""
    seq = []
    for i in range(5):
        seq.append(_step(i, "scroll", "nok", text="无效滑动"))
    payload = {"task_uuid": "t6", "instruction": "测试", "seq_info": seq}
    darwin = _darwin({str(i): {"label": "nok"} for i in range(5)})
    r = analyze_efficiency(payload, darwin)
    assert r.efficiency_label == "inefficient", f"Got {r.efficiency_label}"
    print(f"  PASS: {r.efficiency_label}, overall={r.overall_efficiency:.2f}")


def test_to_dict():
    seq = [_step(0, "click", "ok")]
    payload = {"task_uuid": "t7", "instruction": "测试", "seq_info": seq}
    r = analyze_efficiency(payload, _darwin({"0": {"label": "ok"}}))
    d = r.to_dict()
    assert "overall_efficiency" in d
    assert "ineffective_actions" in d
    print("  PASS: to_dict")


# ── Runner ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Efficiency Analyzer — Unit Tests")
    print("=" * 60)
    tests = [
        ("efficient clean", test_efficient_clean),
        ("ineffective actions", test_ineffective_actions),
        ("exploration cluster", test_exploration_cluster),
        ("navigation loops", test_navigation_loops),
        ("scroll inefficiency", test_scroll_inefficiency),
        ("inefficient overall", test_inefficient_overall),
        ("to_dict", test_to_dict),
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
    import sys
    ok = main()
    sys.exit(0 if ok else 1)
