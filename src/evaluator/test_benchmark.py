"""Tests for offline benchmark report generation."""

from __future__ import annotations

import json
from copy import deepcopy

from src.decomposer.test_schema import valid_annotation_data
from src.evaluator.benchmark import BenchmarkConfig, run_benchmark


def test_benchmark_reads_annotation_v1_v2_and_legacy(tmp_path) -> None:
    case_dir = tmp_path / "case-001"
    case_dir.mkdir()
    annotation = valid_annotation_data()
    payload = {
        "task_uuid": "case-001",
        "instruction": annotation["instruction"],
        "_task_graph": annotation["task_graph"],
        "_task_graph_schema_version": "task_graph.v1",
        "_checkpoints": [
            {
                "name": "Sample application is ready",
                "expected_state": "Sample application is ready",
            }
        ],
    }
    baseline = {
        "schema_version": "repeated_baseline.v1",
        "task_uuid": "case-001",
        "planning_failure_prediction": {
            "label": "normal",
            "subtype": "none",
        },
        "repeated_prediction": {"label": "normal"},
        "verification_report": {
            "overall_status": "通过",
            "total_checkpoints": 3,
            "achieved_count": 3,
        },
        "model_usage": {"llm_calls": 1, "vlm_calls": 2, "total_tokens": 100},
    }
    planning = {
        "schema_version": "planning_evaluation.v1",
        "label": "abnormal",
        "subtype": "dependency_violation",
        "model_calls": 1,
    }
    legacy = {
        "schema_version": "legacy_oracle.v1",
        "label": "normal",
    }
    _write_json(case_dir / "task_annotation.json", annotation)
    _write_json(case_dir / "payload.json", payload)
    _write_json(case_dir / "baseline_result.json", baseline)
    _write_json(case_dir / "planning_evaluation.json", planning)
    _write_json(case_dir / "legacy_result.json", legacy)

    report = run_benchmark(
        tmp_path,
        tmp_path / "benchmark_result.json",
        config=BenchmarkConfig(
            rule_baseline="fixture",
            model_version="mock-model",
            feature_flags={"TASK_GRAPH_ENABLED": "1"},
            code_version="test-rev",
        ),
    )

    assert report["schema_version"] == "planning_benchmark.v1"
    assert report["summary"]["sample_count"] == 1
    assert report["summary"]["parse_failures"] == 0
    assert report["summary"]["schema_incompatible"] == 0
    assert report["summary"]["v1_v2_differences"] == 1
    assert report["summary"]["model_call_stats"]["llm_calls"] == 1
    assert report["summary"]["model_call_stats"]["vlm_calls"] == 2
    assert report["summary"]["model_call_stats"]["total_model_calls"] == 4
    assert report["summary"]["model_call_stats"]["token_count"] == 100
    assert report["metadata"]["feature_flags"] == {"TASK_GRAPH_ENABLED": "1"}
    assert report["samples"][0]["annotation"]["subtask_count"] == 3
    assert report["samples"][0]["v2"]["task_graph"]["subtask_count"] == 3
    assert (tmp_path / "benchmark_result.json").is_file()


def test_benchmark_counts_parse_and_schema_errors(tmp_path) -> None:
    bad_json_dir = tmp_path / "bad-json"
    bad_json_dir.mkdir()
    (bad_json_dir / "baseline_result.json").write_text("{bad json", encoding="utf-8")

    bad_schema_dir = tmp_path / "bad-schema"
    bad_schema_dir.mkdir()
    annotation = deepcopy(valid_annotation_data())
    annotation["schema_version"] = "task_annotation.v2"
    _write_json(bad_schema_dir / "task_annotation.json", annotation)

    report = run_benchmark(tmp_path, config=BenchmarkConfig(code_version="test-rev"))

    assert report["summary"]["sample_count"] == 2
    assert report["summary"]["parse_failures"] == 1
    assert report["summary"]["schema_incompatible"] == 1
    assert report["samples"][0]["errors"] or report["samples"][1]["errors"]


def _write_json(path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
