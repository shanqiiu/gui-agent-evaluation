"""Offline benchmark reader for v1/v2 planning evaluation comparisons."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.decomposer.schema import (
    TASK_ANNOTATION_SCHEMA_VERSION,
    TASK_GRAPH_SCHEMA_VERSION,
    TaskGraphSchemaError,
    decode_task_annotation,
    decode_task_graph,
)


BENCHMARK_SCHEMA_VERSION = "planning_benchmark.v1"


@dataclass(frozen=True)
class BenchmarkConfig:
    rule_baseline: str = "current"
    model_version: str = ""
    feature_flags: dict[str, str] | None = None
    code_version: str = ""


def run_benchmark(
    benchmark_root: str | Path,
    output_path: str | Path | None = None,
    *,
    config: BenchmarkConfig | None = None,
) -> dict[str, Any]:
    """Read benchmark artifacts and write a compact comparison report."""

    config = config or BenchmarkConfig()
    benchmark_root = Path(benchmark_root)
    samples = [_read_sample(path) for path in _sample_dirs(benchmark_root)]
    summary = _summarize(samples)
    report = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "benchmark_root": str(benchmark_root),
        "metadata": _run_metadata(config),
        "summary": summary,
        "samples": samples,
    }
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output_path, report)
    return report


def _sample_dirs(root: Path) -> list[Path]:
    if _contains_sample_artifact(root):
        return [root]
    return sorted(path for path in root.iterdir() if path.is_dir() and _contains_sample_artifact(path))


def _contains_sample_artifact(path: Path) -> bool:
    names = {
        "payload.json",
        "task_annotation.json",
        "annotation.json",
        "planning_evaluation.json",
        "legacy_result.json",
        "baseline_result.json",
    }
    if any((path / name).is_file() for name in names):
        return True
    return (path / "repeated_baseline" / "baseline_result.json").is_file()


def _read_sample(sample_dir: Path) -> dict[str, Any]:
    task_id = sample_dir.name
    errors: list[dict[str, str]] = []
    annotation = _read_annotation(sample_dir, errors)
    payload = _read_payload(sample_dir, errors)
    v1 = _read_v1_baseline(sample_dir, errors)
    v2 = _read_optional_json(sample_dir / "planning_evaluation.json", "v2_planning", errors)
    legacy = _read_optional_json(sample_dir / "legacy_result.json", "legacy", errors)

    if annotation and annotation.get("task_id"):
        task_id = annotation["task_id"]
    elif payload and payload.get("task_uuid"):
        task_id = str(payload["task_uuid"])
    elif v1 and v1.get("task_uuid"):
        task_id = str(v1["task_uuid"])

    v2_graph = _read_v2_task_graph(payload, errors)
    comparison = _compare_outputs(v1, v2, legacy)

    return {
        "task_id": task_id,
        "sample_dir": str(sample_dir),
        "annotation": _annotation_summary(annotation),
        "v1": _v1_summary(v1),
        "v2": _v2_summary(v2, v2_graph),
        "legacy": _legacy_summary(legacy),
        "comparison": comparison,
        "model_call_stats": _model_call_stats(v1, v2, legacy),
        "errors": errors,
    }


def _read_annotation(sample_dir: Path, errors: list[dict[str, str]]) -> dict[str, Any] | None:
    path = _first_existing(sample_dir, ("task_annotation.json", "annotation.json"))
    if path is None:
        return None
    data = _read_optional_json(path, "annotation", errors)
    if not isinstance(data, dict):
        return None
    try:
        decoded = decode_task_annotation(data)
    except TaskGraphSchemaError as exc:
        errors.append({
            "artifact": "annotation",
            "path": str(path),
            "kind": "schema_incompatible",
            "error": _issue_text(exc),
        })
        return None
    return {
        "task_id": decoded.task_id,
        "instruction": decoded.instruction,
        "schema_version": decoded.schema_version,
        "app_name": decoded.app.app_name,
        "subtask_count": len(decoded.task_graph.subtasks),
        "statuses": [item.status for item in decoded.subtask_annotations],
        "has_first_error": decoded.first_error is not None,
        "recovery_outcome": decoded.recovery.outcome if decoded.recovery else "",
    }


def _read_payload(sample_dir: Path, errors: list[dict[str, str]]) -> dict[str, Any] | None:
    return _read_optional_json(sample_dir / "payload.json", "payload", errors)


def _read_v1_baseline(sample_dir: Path, errors: list[dict[str, str]]) -> dict[str, Any] | None:
    path = _first_existing(
        sample_dir,
        ("baseline_result.json", "repeated_baseline/baseline_result.json"),
    )
    if path is None:
        return None
    return _read_optional_json(path, "v1_baseline", errors)


def _read_v2_task_graph(
    payload: dict[str, Any] | None,
    errors: list[dict[str, str]],
) -> dict[str, Any] | None:
    if not payload or not isinstance(payload.get("_task_graph"), dict):
        return None
    graph_data = payload["_task_graph"]
    try:
        graph = decode_task_graph(graph_data)
    except TaskGraphSchemaError as exc:
        errors.append({
            "artifact": "task_graph",
            "path": "payload.json:_task_graph",
            "kind": "schema_incompatible",
            "error": _issue_text(exc),
        })
        return None
    return {
        "schema_version": graph.schema_version,
        "source": graph.metadata.source,
        "subtask_count": len(graph.subtasks),
        "required_subtask_count": sum(1 for item in graph.subtasks if item.required),
        "alternative_group_count": len(graph.alternative_groups),
    }


def _read_optional_json(
    path: Path,
    artifact: str,
    errors: list[dict[str, str]],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append({
            "artifact": artifact,
            "path": str(path),
            "kind": "parse_failed",
            "error": str(exc),
        })
        return None
    if not isinstance(data, dict):
        errors.append({
            "artifact": artifact,
            "path": str(path),
            "kind": "parse_failed",
            "error": "top-level JSON value must be an object",
        })
        return None
    return data


def _first_existing(sample_dir: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = sample_dir / name
        if path.is_file():
            return path
    return None


def _annotation_summary(annotation: dict[str, Any] | None) -> dict[str, Any]:
    if annotation is None:
        return {"present": False}
    return {"present": True, **annotation}


def _v1_summary(v1: dict[str, Any] | None) -> dict[str, Any]:
    if v1 is None:
        return {"present": False}
    repeated = v1.get("repeated_prediction") or {}
    planning = v1.get("planning_failure_prediction") or {}
    verification = v1.get("verification_report") or {}
    return {
        "present": True,
        "schema_version": v1.get("schema_version", ""),
        "task_uuid": v1.get("task_uuid", ""),
        "repeated_label": repeated.get("label", ""),
        "planning_failure_label": planning.get("label", ""),
        "planning_failure_subtype": planning.get("subtype", ""),
        "overall_status": verification.get("overall_status", ""),
        "checkpoint_count": verification.get("total_checkpoints", 0),
        "achieved_count": verification.get("achieved_count", 0),
    }


def _v2_summary(
    planning: dict[str, Any] | None,
    graph: dict[str, Any] | None,
) -> dict[str, Any]:
    if planning is None and graph is None:
        return {"present": False}
    planning = planning or {}
    return {
        "present": True,
        "schema_version": planning.get("schema_version", ""),
        "label": planning.get("label", planning.get("planning_failure_label", "")),
        "subtype": planning.get("subtype", planning.get("planning_failure_subtype", "")),
        "task_graph": graph or {"present": False},
    }


def _legacy_summary(legacy: dict[str, Any] | None) -> dict[str, Any]:
    if legacy is None:
        return {"present": False}
    return {
        "present": True,
        "schema_version": legacy.get("schema_version", ""),
        "label": legacy.get("label", legacy.get("overall_status", "")),
        "subtype": legacy.get("subtype", ""),
    }


def _compare_outputs(
    v1: dict[str, Any] | None,
    v2: dict[str, Any] | None,
    legacy: dict[str, Any] | None,
) -> dict[str, Any]:
    v1_planning = (v1 or {}).get("planning_failure_prediction") or {}
    v1_label = v1_planning.get("label", "")
    v1_subtype = v1_planning.get("subtype", "")
    v2_label = (v2 or {}).get("label", (v2 or {}).get("planning_failure_label", ""))
    v2_subtype = (v2 or {}).get("subtype", (v2 or {}).get("planning_failure_subtype", ""))
    legacy_label = (legacy or {}).get("label", (legacy or {}).get("overall_status", ""))
    return {
        "v1_v2_label_diff": bool(v1_label and v2_label and v1_label != v2_label),
        "v1_v2_subtype_diff": bool(v1_subtype and v2_subtype and v1_subtype != v2_subtype),
        "v1_legacy_label_diff": bool(v1_label and legacy_label and v1_label != legacy_label),
    }


def _model_call_stats(*artifacts: dict[str, Any] | None) -> dict[str, int]:
    stats = {
        "llm_calls": 0,
        "vlm_calls": 0,
        "total_model_calls": 0,
        "retry_count": 0,
        "token_count": 0,
    }
    key_map = {
        "llm_calls": "llm_calls",
        "vlm_calls": "vlm_calls",
        "model_calls": "total_model_calls",
        "total_model_calls": "total_model_calls",
        "retry_count": "retry_count",
        "retries": "retry_count",
        "token_count": "token_count",
        "total_tokens": "token_count",
    }
    explicit_total = 0
    for artifact in artifacts:
        for key, value in _walk_items(artifact):
            target = key_map.get(key)
            if target and isinstance(value, int) and value > 0:
                if target == "total_model_calls":
                    explicit_total += value
                else:
                    stats[target] += value
    stats["total_model_calls"] = (
        stats["llm_calls"] + stats["vlm_calls"] + explicit_total
    )
    return stats


def _walk_items(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            items.append((str(key), child))
            items.extend(_walk_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_walk_items(child))
    return items


def _summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    parse_failures = 0
    schema_incompatible = 0
    v1_v2_diffs = 0
    model_call_stats = {
        "llm_calls": 0,
        "vlm_calls": 0,
        "total_model_calls": 0,
        "retry_count": 0,
        "token_count": 0,
    }
    for sample in samples:
        for error in sample["errors"]:
            if error["kind"] == "parse_failed":
                parse_failures += 1
            elif error["kind"] == "schema_incompatible":
                schema_incompatible += 1
        if sample["comparison"]["v1_v2_label_diff"] or sample["comparison"]["v1_v2_subtype_diff"]:
            v1_v2_diffs += 1
        for key, value in sample["model_call_stats"].items():
            model_call_stats[key] += value
    return {
        "sample_count": len(samples),
        "parse_failures": parse_failures,
        "schema_incompatible": schema_incompatible,
        "v1_v2_differences": v1_v2_diffs,
        "with_annotation": sum(1 for item in samples if item["annotation"]["present"]),
        "with_v1": sum(1 for item in samples if item["v1"]["present"]),
        "with_v2": sum(1 for item in samples if item["v2"]["present"]),
        "with_legacy": sum(1 for item in samples if item["legacy"]["present"]),
        "model_call_stats": model_call_stats,
    }


def _run_metadata(config: BenchmarkConfig) -> dict[str, Any]:
    return {
        "rule_baseline": config.rule_baseline,
        "model_version": config.model_version,
        "feature_flags": config.feature_flags or {},
        "code_version": config.code_version or _git_revision(),
        "task_annotation_schema_version": TASK_ANNOTATION_SCHEMA_VERSION,
        "task_graph_schema_version": TASK_GRAPH_SCHEMA_VERSION,
    }


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _issue_text(exc: TaskGraphSchemaError) -> str:
    return "; ".join(
        f"{issue.code} at {issue.path}: {issue.message}" for issue in exc.issues
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an offline planning benchmark report")
    parser.add_argument("benchmark_root", help="Directory containing benchmark sample folders")
    parser.add_argument("--output", default="", help="Output JSON path")
    parser.add_argument("--rule-baseline", default="current")
    parser.add_argument("--model-version", default="")
    parser.add_argument(
        "--feature-flag",
        action="append",
        default=[],
        help="Feature flag in KEY=VALUE form; may be repeated",
    )
    args = parser.parse_args()
    flags = dict(item.split("=", 1) for item in args.feature_flag if "=" in item)
    report = run_benchmark(
        args.benchmark_root,
        args.output or None,
        config=BenchmarkConfig(
            rule_baseline=args.rule_baseline,
            model_version=args.model_version,
            feature_flags=flags,
        ),
    )
    print(json.dumps({
        "schema_version": report["schema_version"],
        "sample_count": report["summary"]["sample_count"],
        "parse_failures": report["summary"]["parse_failures"],
        "schema_incompatible": report["summary"]["schema_incompatible"],
        "v1_v2_differences": report["summary"]["v1_v2_differences"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
