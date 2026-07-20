"""Strict schema parsing and validation for TaskGraph annotations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import (
    AlternativeGroup,
    AnnotationMetadata,
    AppDescriptor,
    Constraint,
    Dependency,
    EvidenceReference,
    FirstErrorAnnotation,
    Goal,
    RecoveryAnnotation,
    StepSpan,
    Subtask,
    SubtaskAnnotation,
    TaskAnnotation,
    TaskGraph,
    TaskGraphMetadata,
    TrajectorySource,
    VerificationCriterion,
)


TASK_GRAPH_SCHEMA_VERSION = "task_graph.v1"
TASK_ANNOTATION_SCHEMA_VERSION = "task_annotation.v1"
MIN_SUBTASKS = 3
MAX_SUBTASKS = 8

ALLOWED_CONSTRAINT_TYPES = {"must", "must_not", "prefer"}
ALLOWED_EDGE_TYPES = {"requires", "recommended"}
ALLOWED_EVIDENCE_TYPES = {
    "screenshot",
    "ocr",
    "ui_tree",
    "action_log",
    "system_state",
}
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
ALLOWED_SUBTASK_STATUSES = {
    "achieved",
    "partial",
    "failed",
    "uncertain",
    "not_attempted",
}
ALLOWED_RECOVERY_OUTCOMES = {"none", "successful", "failed", "uncertain"}
ALLOWED_ARTIFACT_TYPES = {
    "utg",
    "clear_res",
    "screenshot",
    "ui_tree",
    "ocr",
    "action_purpose",
    "phone_log",
}

_ACTION_NAME_PREFIXES = (
    "click",
    "tap",
    "type",
    "input",
    "scroll",
    "swipe",
    "drag",
    "点击",
    "输入",
    "滑动",
    "滚动",
    "拖动",
)
_COMPOUND_MARKERS = (" then ", " and ", "然后", "并且", "同时", "随后", "接着", "->", "→")
_OPAQUE_REFERENCE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]*:[a-zA-Z0-9._:-]+$")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


class TaskGraphSchemaError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]):
        self.issues = issues
        detail = "; ".join(
            f"{issue.code} at {issue.path}: {issue.message}" for issue in issues
        )
        super().__init__(detail or "invalid TaskGraph schema")


def decode_task_graph(data: Mapping[str, Any]) -> TaskGraph:
    """Parse and validate a strict task_graph.v1 mapping."""

    graph = _decode_task_graph(_as_mapping(data, "$"), "$")
    _raise_if_invalid(validate_task_graph(graph))
    return graph


def encode_task_graph(graph: TaskGraph) -> dict[str, Any]:
    """Serialize a TaskGraph into its stable JSON-compatible representation."""

    return {
        "schema_version": graph.schema_version,
        "goal": _encode_goal(graph.goal),
        "constraints": [_encode_constraint(item) for item in graph.constraints],
        "subtasks": [_encode_subtask(item) for item in graph.subtasks],
        "edges": [_encode_dependency(item) for item in graph.edges],
        "alternative_groups": [
            _encode_alternative_group(item) for item in graph.alternative_groups
        ],
        "metadata": _encode_task_graph_metadata(graph.metadata),
    }


def loads_task_graph(payload: str) -> TaskGraph:
    return decode_task_graph(_load_json_mapping(payload, "$"))


def dumps_task_graph(graph: TaskGraph, *, indent: int = 2) -> str:
    _raise_if_invalid(validate_task_graph(graph))
    return json.dumps(encode_task_graph(graph), ensure_ascii=False, indent=indent)


def decode_task_annotation(data: Mapping[str, Any]) -> TaskAnnotation:
    """Parse and validate a strict task_annotation.v1 mapping."""

    annotation = _decode_task_annotation(_as_mapping(data, "$"), "$")
    _raise_if_invalid(validate_task_annotation(annotation))
    return annotation


def encode_task_annotation(annotation: TaskAnnotation) -> dict[str, Any]:
    return {
        "schema_version": annotation.schema_version,
        "annotation_id": annotation.annotation_id,
        "task_id": annotation.task_id,
        "app": {
            "app_name": annotation.app.app_name,
            "package_name": annotation.app.package_name,
            "app_version": annotation.app.app_version,
            "platform": annotation.app.platform,
            "language": annotation.app.language,
        },
        "instruction": annotation.instruction,
        "source": {
            "source_ref": annotation.source.source_ref,
            "step_count": annotation.source.step_count,
            "artifact_types": list(annotation.source.artifact_types),
        },
        "task_graph": encode_task_graph(annotation.task_graph),
        "subtask_annotations": [
            {
                "subtask_id": item.subtask_id,
                "status": item.status,
                "attempt_spans": [
                    {
                        "start_step_index": span.start_step_index,
                        "end_step_index": span.end_step_index,
                    }
                    for span in item.attempt_spans
                ],
                "evidence_ids": list(item.evidence_ids),
                "notes": item.notes,
            }
            for item in annotation.subtask_annotations
        ],
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "evidence_type": item.evidence_type,
                "step_index": item.step_index,
                "source_step_id": item.source_step_id,
                "artifact_ref": item.artifact_ref,
                "description": item.description,
            }
            for item in annotation.evidence
        ],
        "first_error": _encode_first_error(annotation.first_error),
        "recovery": _encode_recovery(annotation.recovery),
        "metadata": {
            "annotator": annotation.metadata.annotator,
            "revision": annotation.metadata.revision,
            "notes": annotation.metadata.notes,
        },
    }


def loads_task_annotation(payload: str) -> TaskAnnotation:
    return decode_task_annotation(_load_json_mapping(payload, "$"))


def dumps_task_annotation(annotation: TaskAnnotation, *, indent: int = 2) -> str:
    _raise_if_invalid(validate_task_annotation(annotation))
    return json.dumps(encode_task_annotation(annotation), ensure_ascii=False, indent=indent)


def validate_task_graph(graph: TaskGraph) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []

    if graph.schema_version != TASK_GRAPH_SCHEMA_VERSION:
        _add(
            issues,
            "unsupported_schema_version",
            "$.schema_version",
            f"expected {TASK_GRAPH_SCHEMA_VERSION}",
        )

    _validate_text(issues, graph.goal.description, "$.goal.description")
    _validate_criteria(issues, graph.goal.success_criteria, "$.goal.success_criteria")

    minimum_subtasks = (
        1 if graph.metadata.source == "checkpoint_migration" else MIN_SUBTASKS
    )
    if not minimum_subtasks <= len(graph.subtasks) <= MAX_SUBTASKS:
        _add(
            issues,
            "invalid_subtask_count",
            "$.subtasks",
            f"expected {minimum_subtasks}-{MAX_SUBTASKS} semantic subtasks, "
            f"got {len(graph.subtasks)}",
        )

    constraint_ids: set[str] = set()
    for index, constraint in enumerate(graph.constraints):
        path = f"$.constraints[{index}]"
        _validate_unique_id(issues, constraint.constraint_id, constraint_ids, f"{path}.constraint_id")
        if constraint.type not in ALLOWED_CONSTRAINT_TYPES:
            _add(issues, "invalid_constraint_type", f"{path}.type", constraint.type)
        _validate_text(issues, constraint.description, f"{path}.description")
        _validate_text(
            issues,
            constraint.observable_condition,
            f"{path}.observable_condition",
            code="unobservable_constraint",
        )

    subtask_ids: set[str] = set()
    normalized_names: set[str] = set()
    for index, subtask in enumerate(graph.subtasks):
        path = f"$.subtasks[{index}]"
        _validate_unique_id(issues, subtask.subtask_id, subtask_ids, f"{path}.subtask_id")
        _validate_text(issues, subtask.name, f"{path}.name")
        _validate_text(issues, subtask.description, f"{path}.description")
        normalized_name = _normalize_text(subtask.name)
        if normalized_name in normalized_names:
            _add(issues, "duplicate_subtask_state", f"{path}.name", subtask.name)
        normalized_names.add(normalized_name)
        lowered = subtask.name.lower()
        if lowered.startswith(_ACTION_NAME_PREFIXES):
            _add(issues, "action_level_subtask", f"{path}.name", subtask.name)
        if any(marker in lowered for marker in _COMPOUND_MARKERS):
            _add(issues, "compound_subtask", f"{path}.name", subtask.name)
        if subtask.risk_level not in ALLOWED_RISK_LEVELS:
            _add(issues, "invalid_risk_level", f"{path}.risk_level", subtask.risk_level)
        if len(set(subtask.depends_on)) != len(subtask.depends_on):
            _add(issues, "duplicate_dependency", f"{path}.depends_on", "dependency repeated")
        _validate_criteria(issues, subtask.success_criteria, f"{path}.success_criteria")

    required_count = sum(1 for item in graph.subtasks if item.required)
    if required_count == 0:
        _add(issues, "missing_required_subtask", "$.subtasks", "at least one subtask must be required")

    for index, subtask in enumerate(graph.subtasks):
        for dependency_index, dependency_id in enumerate(subtask.depends_on):
            path = f"$.subtasks[{index}].depends_on[{dependency_index}]"
            if dependency_id not in subtask_ids:
                _add(issues, "unknown_dependency", path, dependency_id)
            if dependency_id == subtask.subtask_id:
                _add(issues, "self_dependency", path, dependency_id)

    edge_keys: set[tuple[str, str, str]] = set()
    required_edges: set[tuple[str, str]] = set()
    for index, edge in enumerate(graph.edges):
        path = f"$.edges[{index}]"
        key = (edge.from_subtask_id, edge.to_subtask_id, edge.type)
        if key in edge_keys:
            _add(issues, "duplicate_edge", path, str(key))
        edge_keys.add(key)
        if edge.type not in ALLOWED_EDGE_TYPES:
            _add(issues, "invalid_edge_type", f"{path}.type", edge.type)
        if edge.from_subtask_id not in subtask_ids:
            _add(issues, "unknown_edge_source", f"{path}.from", edge.from_subtask_id)
        if edge.to_subtask_id not in subtask_ids:
            _add(issues, "unknown_edge_target", f"{path}.to", edge.to_subtask_id)
        if edge.from_subtask_id == edge.to_subtask_id:
            _add(issues, "self_dependency", path, edge.from_subtask_id)
        if edge.type == "requires":
            required_edges.add((edge.from_subtask_id, edge.to_subtask_id))

    declared_dependencies = {
        (dependency_id, subtask.subtask_id)
        for subtask in graph.subtasks
        for dependency_id in subtask.depends_on
    }
    for edge in sorted(declared_dependencies - required_edges):
        _add(
            issues,
            "missing_requires_edge",
            "$.edges",
            f"depends_on {edge[0]} -> {edge[1]} has no requires edge",
        )
    for edge in sorted(required_edges - declared_dependencies):
        _add(
            issues,
            "missing_depends_on",
            "$.subtasks",
            f"requires edge {edge[0]} -> {edge[1]} is absent from depends_on",
        )

    cycle = _find_cycle(subtask_ids, required_edges)
    if cycle:
        _add(issues, "dependency_cycle", "$.edges", " -> ".join(cycle))

    group_ids: set[str] = set()
    member_to_group: dict[str, str] = {}
    for index, group in enumerate(graph.alternative_groups):
        path = f"$.alternative_groups[{index}]"
        _validate_unique_id(issues, group.group_id, group_ids, f"{path}.group_id")
        if len(group.member_subtask_ids) < 2:
            _add(issues, "small_alternative_group", f"{path}.member_subtask_ids", "at least two members required")
        if len(set(group.member_subtask_ids)) != len(group.member_subtask_ids):
            _add(issues, "duplicate_alternative_member", f"{path}.member_subtask_ids", "member repeated")
        if not 1 <= group.required_count <= len(group.member_subtask_ids):
            _add(issues, "invalid_required_count", f"{path}.required_count", str(group.required_count))
        for member in group.member_subtask_ids:
            if member not in subtask_ids:
                _add(issues, "unknown_alternative_member", f"{path}.member_subtask_ids", member)
            previous = member_to_group.get(member)
            if previous and previous != group.group_id:
                _add(issues, "multiple_alternative_groups", f"{path}.member_subtask_ids", member)
            member_to_group[member] = group.group_id

    for index, subtask in enumerate(graph.subtasks):
        expected_group = member_to_group.get(subtask.subtask_id, "")
        if subtask.alternative_group_id != expected_group:
            _add(
                issues,
                "alternative_group_mismatch",
                f"$.subtasks[{index}].alternative_group_id",
                f"expected {expected_group!r}",
            )

    return tuple(issues)


def validate_task_annotation(annotation: TaskAnnotation) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if annotation.schema_version != TASK_ANNOTATION_SCHEMA_VERSION:
        _add(
            issues,
            "unsupported_schema_version",
            "$.schema_version",
            f"expected {TASK_ANNOTATION_SCHEMA_VERSION}",
        )
    _validate_text(issues, annotation.annotation_id, "$.annotation_id")
    _validate_text(issues, annotation.task_id, "$.task_id")
    _validate_text(issues, annotation.app.app_name, "$.app.app_name")
    _validate_text(issues, annotation.instruction, "$.instruction")
    _validate_text(issues, annotation.source.source_ref, "$.source.source_ref")
    _validate_opaque_reference(
        issues,
        annotation.source.source_ref,
        "$.source.source_ref",
    )
    if annotation.source.step_count <= 0:
        _add(issues, "invalid_step_count", "$.source.step_count", str(annotation.source.step_count))
    if not annotation.source.artifact_types:
        _add(
            issues,
            "missing_artifact_type",
            "$.source.artifact_types",
            "at least one remote artifact type is required",
        )
    for index, artifact_type in enumerate(annotation.source.artifact_types):
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            _add(issues, "invalid_artifact_type", f"$.source.artifact_types[{index}]", artifact_type)

    for issue in validate_task_graph(annotation.task_graph):
        issues.append(
            ValidationIssue(issue.code, f"$.task_graph{issue.path[1:]}", issue.message)
        )

    graph_subtask_ids = {item.subtask_id for item in annotation.task_graph.subtasks}
    evidence_ids: set[str] = set()
    for index, evidence in enumerate(annotation.evidence):
        path = f"$.evidence[{index}]"
        _validate_unique_id(issues, evidence.evidence_id, evidence_ids, f"{path}.evidence_id")
        if evidence.evidence_type not in ALLOWED_EVIDENCE_TYPES:
            _add(issues, "invalid_evidence_type", f"{path}.evidence_type", evidence.evidence_type)
        _validate_step_index(issues, evidence.step_index, annotation.source.step_count, f"{path}.step_index")
        if evidence.artifact_ref:
            _validate_opaque_reference(
                issues,
                evidence.artifact_ref,
                f"{path}.artifact_ref",
            )

    annotated_ids: set[str] = set()
    for index, item in enumerate(annotation.subtask_annotations):
        path = f"$.subtask_annotations[{index}]"
        _validate_unique_id(issues, item.subtask_id, annotated_ids, f"{path}.subtask_id")
        if item.subtask_id not in graph_subtask_ids:
            _add(issues, "unknown_annotated_subtask", f"{path}.subtask_id", item.subtask_id)
        if item.status not in ALLOWED_SUBTASK_STATUSES:
            _add(issues, "invalid_subtask_status", f"{path}.status", item.status)
        if item.status == "not_attempted" and item.attempt_spans:
            _add(issues, "unexpected_attempt_span", f"{path}.attempt_spans", item.status)
        if item.status in {"achieved", "partial", "failed"} and not item.attempt_spans:
            _add(issues, "missing_attempt_span", f"{path}.attempt_spans", item.status)
        for span_index, span in enumerate(item.attempt_spans):
            _validate_span(
                issues,
                span,
                annotation.source.step_count,
                f"{path}.attempt_spans[{span_index}]",
            )
        _validate_evidence_refs(issues, item.evidence_ids, evidence_ids, f"{path}.evidence_ids")

    missing_annotations = graph_subtask_ids - annotated_ids
    for subtask_id in sorted(missing_annotations):
        _add(issues, "missing_subtask_annotation", "$.subtask_annotations", subtask_id)

    if annotation.first_error is not None:
        first_error = annotation.first_error
        _validate_text(issues, first_error.error_type, "$.first_error.error_type")
        _validate_step_index(
            issues,
            first_error.step_index,
            annotation.source.step_count,
            "$.first_error.step_index",
        )
        if first_error.subtask_id and first_error.subtask_id not in graph_subtask_ids:
            _add(issues, "unknown_first_error_subtask", "$.first_error.subtask_id", first_error.subtask_id)
        _validate_evidence_refs(
            issues,
            first_error.evidence_ids,
            evidence_ids,
            "$.first_error.evidence_ids",
        )

    if annotation.recovery is not None:
        recovery = annotation.recovery
        if recovery.outcome not in ALLOWED_RECOVERY_OUTCOMES:
            _add(issues, "invalid_recovery_outcome", "$.recovery.outcome", recovery.outcome)
        if not recovery.attempted:
            if recovery.outcome != "none":
                _add(issues, "unexpected_recovery_outcome", "$.recovery.outcome", recovery.outcome)
            if recovery.start_step_index != -1 or recovery.end_step_index != -1:
                _add(issues, "unexpected_recovery_span", "$.recovery", "recovery was not attempted")
        else:
            _validate_span(
                issues,
                StepSpan(recovery.start_step_index, recovery.end_step_index),
                annotation.source.step_count,
                "$.recovery",
            )
        _validate_evidence_refs(issues, recovery.evidence_ids, evidence_ids, "$.recovery.evidence_ids")

    if annotation.metadata.revision < 1:
        _add(issues, "invalid_revision", "$.metadata.revision", str(annotation.metadata.revision))
    return tuple(issues)


def _decode_task_graph(data: Mapping[str, Any], path: str) -> TaskGraph:
    _check_keys(
        data,
        required={"schema_version", "goal", "subtasks", "edges"},
        optional={"constraints", "alternative_groups", "metadata"},
        path=path,
    )
    return TaskGraph(
        schema_version=_string(data, "schema_version", path),
        goal=_decode_goal(_mapping_field(data, "goal", path), f"{path}.goal"),
        constraints=tuple(
            _decode_constraint(item, item_path)
            for item, item_path in _mapping_items(data.get("constraints", []), f"{path}.constraints")
        ),
        subtasks=tuple(
            _decode_subtask(item, item_path)
            for item, item_path in _mapping_items(data.get("subtasks", []), f"{path}.subtasks")
        ),
        edges=tuple(
            _decode_dependency(item, item_path)
            for item, item_path in _mapping_items(data.get("edges", []), f"{path}.edges")
        ),
        alternative_groups=tuple(
            _decode_alternative_group(item, item_path)
            for item, item_path in _mapping_items(
                data.get("alternative_groups", []), f"{path}.alternative_groups"
            )
        ),
        metadata=_decode_task_graph_metadata(
            _as_mapping(data.get("metadata", {}), f"{path}.metadata"),
            f"{path}.metadata",
        ),
    )


def _decode_goal(data: Mapping[str, Any], path: str) -> Goal:
    _check_keys(data, {"description", "success_criteria"}, set(), path)
    return Goal(
        description=_string(data, "description", path),
        success_criteria=tuple(
            _decode_criterion(item, item_path)
            for item, item_path in _mapping_items(data["success_criteria"], f"{path}.success_criteria")
        ),
    )


def _decode_criterion(data: Mapping[str, Any], path: str) -> VerificationCriterion:
    _check_keys(data, {"criterion_id", "description", "evidence_types"}, {"required"}, path)
    return VerificationCriterion(
        criterion_id=_string(data, "criterion_id", path),
        description=_string(data, "description", path),
        evidence_types=_string_tuple(data["evidence_types"], f"{path}.evidence_types"),
        required=_bool(data.get("required", True), f"{path}.required"),
    )


def _decode_constraint(data: Mapping[str, Any], path: str) -> Constraint:
    _check_keys(
        data,
        {"constraint_id", "type", "description", "observable_condition"},
        set(),
        path,
    )
    return Constraint(
        constraint_id=_string(data, "constraint_id", path),
        type=_string(data, "type", path),
        description=_string(data, "description", path),
        observable_condition=_string(data, "observable_condition", path),
    )


def _decode_subtask(data: Mapping[str, Any], path: str) -> Subtask:
    _check_keys(
        data,
        {"subtask_id", "name", "description", "required", "success_criteria"},
        {
            "depends_on",
            "preconditions",
            "forbidden_states",
            "risk_level",
            "reversible",
            "allowed_reorder",
            "alternative_group_id",
            "checkpoint_ids",
        },
        path,
    )
    return Subtask(
        subtask_id=_string(data, "subtask_id", path),
        name=_string(data, "name", path),
        description=_string(data, "description", path),
        required=_bool(data["required"], f"{path}.required"),
        depends_on=_string_tuple(data.get("depends_on", []), f"{path}.depends_on"),
        preconditions=_string_tuple(data.get("preconditions", []), f"{path}.preconditions"),
        success_criteria=tuple(
            _decode_criterion(item, item_path)
            for item, item_path in _mapping_items(data["success_criteria"], f"{path}.success_criteria")
        ),
        forbidden_states=_string_tuple(data.get("forbidden_states", []), f"{path}.forbidden_states"),
        risk_level=_optional_string(data, "risk_level", path, "low"),
        reversible=_bool(data.get("reversible", True), f"{path}.reversible"),
        allowed_reorder=_bool(data.get("allowed_reorder", False), f"{path}.allowed_reorder"),
        alternative_group_id=_optional_string(data, "alternative_group_id", path, ""),
        checkpoint_ids=_string_tuple(data.get("checkpoint_ids", []), f"{path}.checkpoint_ids"),
    )


def _decode_dependency(data: Mapping[str, Any], path: str) -> Dependency:
    _check_keys(data, {"from", "to", "type"}, {"condition"}, path)
    return Dependency(
        from_subtask_id=_string(data, "from", path),
        to_subtask_id=_string(data, "to", path),
        type=_string(data, "type", path),
        condition=_optional_string(data, "condition", path, ""),
    )


def _decode_alternative_group(data: Mapping[str, Any], path: str) -> AlternativeGroup:
    _check_keys(data, {"group_id", "member_subtask_ids"}, {"required_count"}, path)
    return AlternativeGroup(
        group_id=_string(data, "group_id", path),
        member_subtask_ids=_string_tuple(data["member_subtask_ids"], f"{path}.member_subtask_ids"),
        required_count=_int(data.get("required_count", 1), f"{path}.required_count"),
    )


def _decode_task_graph_metadata(data: Mapping[str, Any], path: str) -> TaskGraphMetadata:
    _check_keys(data, set(), {"source", "model", "rag_hits", "quality_status"}, path)
    return TaskGraphMetadata(
        source=_optional_string(data, "source", path, ""),
        model=_optional_string(data, "model", path, ""),
        rag_hits=_string_tuple(data.get("rag_hits", []), f"{path}.rag_hits"),
        quality_status=_optional_string(data, "quality_status", path, ""),
    )


def _decode_task_annotation(data: Mapping[str, Any], path: str) -> TaskAnnotation:
    _check_keys(
        data,
        {
            "schema_version",
            "annotation_id",
            "task_id",
            "app",
            "instruction",
            "source",
            "task_graph",
            "subtask_annotations",
            "evidence",
        },
        {"first_error", "recovery", "metadata"},
        path,
    )
    first_error_data = data.get("first_error")
    recovery_data = data.get("recovery")
    return TaskAnnotation(
        schema_version=_string(data, "schema_version", path),
        annotation_id=_string(data, "annotation_id", path),
        task_id=_string(data, "task_id", path),
        app=_decode_app(_mapping_field(data, "app", path), f"{path}.app"),
        instruction=_string(data, "instruction", path),
        source=_decode_source(_mapping_field(data, "source", path), f"{path}.source"),
        task_graph=_decode_task_graph(_mapping_field(data, "task_graph", path), f"{path}.task_graph"),
        subtask_annotations=tuple(
            _decode_subtask_annotation(item, item_path)
            for item, item_path in _mapping_items(
                data["subtask_annotations"], f"{path}.subtask_annotations"
            )
        ),
        evidence=tuple(
            _decode_evidence(item, item_path)
            for item, item_path in _mapping_items(data["evidence"], f"{path}.evidence")
        ),
        first_error=(
            None
            if first_error_data is None
            else _decode_first_error(_as_mapping(first_error_data, f"{path}.first_error"), f"{path}.first_error")
        ),
        recovery=(
            None
            if recovery_data is None
            else _decode_recovery(_as_mapping(recovery_data, f"{path}.recovery"), f"{path}.recovery")
        ),
        metadata=_decode_annotation_metadata(
            _as_mapping(data.get("metadata", {}), f"{path}.metadata"),
            f"{path}.metadata",
        ),
    )


def _decode_app(data: Mapping[str, Any], path: str) -> AppDescriptor:
    _check_keys(data, {"app_name"}, {"package_name", "app_version", "platform", "language"}, path)
    return AppDescriptor(
        app_name=_string(data, "app_name", path),
        package_name=_optional_string(data, "package_name", path, ""),
        app_version=_optional_string(data, "app_version", path, ""),
        platform=_optional_string(data, "platform", path, ""),
        language=_optional_string(data, "language", path, ""),
    )


def _decode_source(data: Mapping[str, Any], path: str) -> TrajectorySource:
    _check_keys(data, {"source_ref", "step_count", "artifact_types"}, set(), path)
    return TrajectorySource(
        source_ref=_string(data, "source_ref", path),
        step_count=_int(data["step_count"], f"{path}.step_count"),
        artifact_types=_string_tuple(data["artifact_types"], f"{path}.artifact_types"),
    )


def _decode_evidence(data: Mapping[str, Any], path: str) -> EvidenceReference:
    _check_keys(
        data,
        {"evidence_id", "evidence_type", "step_index"},
        {"source_step_id", "artifact_ref", "description"},
        path,
    )
    return EvidenceReference(
        evidence_id=_string(data, "evidence_id", path),
        evidence_type=_string(data, "evidence_type", path),
        step_index=_int(data["step_index"], f"{path}.step_index"),
        source_step_id=_optional_string(data, "source_step_id", path, ""),
        artifact_ref=_optional_string(data, "artifact_ref", path, ""),
        description=_optional_string(data, "description", path, ""),
    )


def _decode_span(data: Mapping[str, Any], path: str) -> StepSpan:
    _check_keys(data, {"start_step_index", "end_step_index"}, set(), path)
    return StepSpan(
        start_step_index=_int(data["start_step_index"], f"{path}.start_step_index"),
        end_step_index=_int(data["end_step_index"], f"{path}.end_step_index"),
    )


def _decode_subtask_annotation(data: Mapping[str, Any], path: str) -> SubtaskAnnotation:
    _check_keys(data, {"subtask_id", "status"}, {"attempt_spans", "evidence_ids", "notes"}, path)
    return SubtaskAnnotation(
        subtask_id=_string(data, "subtask_id", path),
        status=_string(data, "status", path),
        attempt_spans=tuple(
            _decode_span(item, item_path)
            for item, item_path in _mapping_items(data.get("attempt_spans", []), f"{path}.attempt_spans")
        ),
        evidence_ids=_string_tuple(data.get("evidence_ids", []), f"{path}.evidence_ids"),
        notes=_optional_string(data, "notes", path, ""),
    )


def _decode_first_error(data: Mapping[str, Any], path: str) -> FirstErrorAnnotation:
    _check_keys(data, {"error_type", "step_index"}, {"subtask_id", "evidence_ids"}, path)
    return FirstErrorAnnotation(
        error_type=_string(data, "error_type", path),
        step_index=_int(data["step_index"], f"{path}.step_index"),
        subtask_id=_optional_string(data, "subtask_id", path, ""),
        evidence_ids=_string_tuple(data.get("evidence_ids", []), f"{path}.evidence_ids"),
    )


def _decode_recovery(data: Mapping[str, Any], path: str) -> RecoveryAnnotation:
    _check_keys(
        data,
        {"attempted", "outcome"},
        {"start_step_index", "end_step_index", "evidence_ids"},
        path,
    )
    return RecoveryAnnotation(
        attempted=_bool(data["attempted"], f"{path}.attempted"),
        outcome=_string(data, "outcome", path),
        start_step_index=_int(data.get("start_step_index", -1), f"{path}.start_step_index"),
        end_step_index=_int(data.get("end_step_index", -1), f"{path}.end_step_index"),
        evidence_ids=_string_tuple(data.get("evidence_ids", []), f"{path}.evidence_ids"),
    )


def _decode_annotation_metadata(data: Mapping[str, Any], path: str) -> AnnotationMetadata:
    _check_keys(data, set(), {"annotator", "revision", "notes"}, path)
    return AnnotationMetadata(
        annotator=_optional_string(data, "annotator", path, ""),
        revision=_int(data.get("revision", 1), f"{path}.revision"),
        notes=_optional_string(data, "notes", path, ""),
    )


def _encode_goal(goal: Goal) -> dict[str, Any]:
    return {
        "description": goal.description,
        "success_criteria": [_encode_criterion(item) for item in goal.success_criteria],
    }


def _encode_criterion(item: VerificationCriterion) -> dict[str, Any]:
    return {
        "criterion_id": item.criterion_id,
        "description": item.description,
        "evidence_types": list(item.evidence_types),
        "required": item.required,
    }


def _encode_constraint(item: Constraint) -> dict[str, Any]:
    return {
        "constraint_id": item.constraint_id,
        "type": item.type,
        "description": item.description,
        "observable_condition": item.observable_condition,
    }


def _encode_subtask(item: Subtask) -> dict[str, Any]:
    return {
        "subtask_id": item.subtask_id,
        "name": item.name,
        "description": item.description,
        "required": item.required,
        "depends_on": list(item.depends_on),
        "preconditions": list(item.preconditions),
        "success_criteria": [_encode_criterion(value) for value in item.success_criteria],
        "forbidden_states": list(item.forbidden_states),
        "risk_level": item.risk_level,
        "reversible": item.reversible,
        "allowed_reorder": item.allowed_reorder,
        "alternative_group_id": item.alternative_group_id,
        "checkpoint_ids": list(item.checkpoint_ids),
    }


def _encode_dependency(item: Dependency) -> dict[str, Any]:
    return {
        "from": item.from_subtask_id,
        "to": item.to_subtask_id,
        "type": item.type,
        "condition": item.condition,
    }


def _encode_alternative_group(item: AlternativeGroup) -> dict[str, Any]:
    return {
        "group_id": item.group_id,
        "member_subtask_ids": list(item.member_subtask_ids),
        "required_count": item.required_count,
    }


def _encode_task_graph_metadata(item: TaskGraphMetadata) -> dict[str, Any]:
    return {
        "source": item.source,
        "model": item.model,
        "rag_hits": list(item.rag_hits),
        "quality_status": item.quality_status,
    }


def _encode_first_error(item: FirstErrorAnnotation | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "error_type": item.error_type,
        "step_index": item.step_index,
        "subtask_id": item.subtask_id,
        "evidence_ids": list(item.evidence_ids),
    }


def _encode_recovery(item: RecoveryAnnotation | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "attempted": item.attempted,
        "outcome": item.outcome,
        "start_step_index": item.start_step_index,
        "end_step_index": item.end_step_index,
        "evidence_ids": list(item.evidence_ids),
    }


def _validate_criteria(
    issues: list[ValidationIssue],
    criteria: tuple[VerificationCriterion, ...],
    path: str,
) -> None:
    if not criteria:
        _add(issues, "missing_success_criteria", path, "at least one criterion is required")
        return
    criterion_ids: set[str] = set()
    for index, criterion in enumerate(criteria):
        item_path = f"{path}[{index}]"
        _validate_unique_id(issues, criterion.criterion_id, criterion_ids, f"{item_path}.criterion_id")
        _validate_text(
            issues,
            criterion.description,
            f"{item_path}.description",
            code="unobservable_criterion",
        )
        if not criterion.evidence_types:
            _add(issues, "missing_evidence_type", f"{item_path}.evidence_types", "empty")
        for evidence_index, evidence_type in enumerate(criterion.evidence_types):
            if evidence_type not in ALLOWED_EVIDENCE_TYPES:
                _add(
                    issues,
                    "invalid_evidence_type",
                    f"{item_path}.evidence_types[{evidence_index}]",
                    evidence_type,
                )


def _validate_unique_id(
    issues: list[ValidationIssue], value: str, seen: set[str], path: str
) -> None:
    _validate_text(issues, value, path, code="missing_id")
    if value in seen:
        _add(issues, "duplicate_id", path, value)
    seen.add(value)


def _validate_text(
    issues: list[ValidationIssue], value: str, path: str, *, code: str = "missing_text"
) -> None:
    if not value.strip():
        _add(issues, code, path, "value must be non-empty")


def _validate_step_index(
    issues: list[ValidationIssue], value: int, step_count: int, path: str
) -> None:
    if value < 0 or value >= step_count:
        _add(issues, "step_index_out_of_range", path, f"{value} not in [0, {step_count})")


def _validate_span(
    issues: list[ValidationIssue], span: StepSpan, step_count: int, path: str
) -> None:
    _validate_step_index(issues, span.start_step_index, step_count, f"{path}.start_step_index")
    _validate_step_index(issues, span.end_step_index, step_count, f"{path}.end_step_index")
    if span.start_step_index > span.end_step_index:
        _add(issues, "invalid_step_span", path, "start_step_index exceeds end_step_index")


def _validate_evidence_refs(
    issues: list[ValidationIssue], values: tuple[str, ...], known: set[str], path: str
) -> None:
    for index, evidence_id in enumerate(values):
        if evidence_id not in known:
            _add(issues, "unknown_evidence", f"{path}[{index}]", evidence_id)


def _validate_opaque_reference(
    issues: list[ValidationIssue], value: str, path: str
) -> None:
    if not _OPAQUE_REFERENCE.fullmatch(value.strip()):
        _add(
            issues,
            "non_opaque_reference",
            path,
            "expected namespace:opaque-id without a path, URL, query, or credential",
        )


def _find_cycle(
    node_ids: set[str], edges: set[tuple[str, str]]
) -> tuple[str, ...]:
    adjacency = {node_id: [] for node_id in node_ids}
    for source, target in edges:
        if source in adjacency and target in adjacency:
            adjacency[source].append(target)
    for targets in adjacency.values():
        targets.sort()

    state: dict[str, int] = {node_id: 0 for node_id in node_ids}
    stack: list[str] = []

    def visit(node_id: str) -> tuple[str, ...]:
        state[node_id] = 1
        stack.append(node_id)
        for target in adjacency[node_id]:
            if state[target] == 0:
                cycle = visit(target)
                if cycle:
                    return cycle
            elif state[target] == 1:
                start = stack.index(target)
                return tuple(stack[start:] + [target])
        stack.pop()
        state[node_id] = 2
        return ()

    for node_id in sorted(node_ids):
        if state[node_id] == 0:
            cycle = visit(node_id)
            if cycle:
                return cycle
    return ()


def _load_json_mapping(payload: str, path: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        _raise("invalid_json", path, str(exc))
    return _as_mapping(value, path)


def _mapping_field(data: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    return _as_mapping(data[key], f"{path}.{key}")


def _mapping_items(value: Any, path: str) -> tuple[tuple[Mapping[str, Any], str], ...]:
    if not isinstance(value, list):
        _raise("invalid_type", path, "expected array")
    return tuple((_as_mapping(item, f"{path}[{index}]"), f"{path}[{index}]") for index, item in enumerate(value))


def _as_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise("invalid_type", path, "expected object")
    return value


def _check_keys(
    data: Mapping[str, Any],
    required: set[str],
    optional: set[str],
    path: str,
) -> None:
    missing = sorted(required - set(data))
    unknown = sorted(set(data) - required - optional)
    issues = [ValidationIssue("missing_field", f"{path}.{key}", "field is required") for key in missing]
    issues.extend(
        ValidationIssue("unknown_field", f"{path}.{key}", "field is not part of the schema")
        for key in unknown
    )
    if issues:
        raise TaskGraphSchemaError(tuple(issues))


def _string(data: Mapping[str, Any], key: str, path: str) -> str:
    if key not in data:
        _raise("missing_field", f"{path}.{key}", "field is required")
    value = data[key]
    if not isinstance(value, str):
        _raise("invalid_type", f"{path}.{key}", "expected string")
    return value.strip()


def _optional_string(data: Mapping[str, Any], key: str, path: str, default: str) -> str:
    if key not in data:
        return default
    return _string(data, key, path)


def _string_tuple(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        _raise("invalid_type", path, "expected array")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            _raise("invalid_type", f"{path}[{index}]", "expected string")
        result.append(item.strip())
    return tuple(result)


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _raise("invalid_type", path, "expected boolean")
    return value


def _int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _raise("invalid_type", path, "expected integer")
    return value


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s，。！？、,.;；:：]+", "", value).lower()


def _add(
    issues: list[ValidationIssue], code: str, path: str, message: str
) -> None:
    issues.append(ValidationIssue(code, path, message))


def _raise(code: str, path: str, message: str) -> None:
    raise TaskGraphSchemaError((ValidationIssue(code, path, message),))


def _raise_if_invalid(issues: tuple[ValidationIssue, ...]) -> None:
    if issues:
        raise TaskGraphSchemaError(issues)
