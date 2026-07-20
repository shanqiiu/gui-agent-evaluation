"""Compatibility projection between TaskGraph and legacy checkpoints."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .models import (
    AlternativeGroup,
    Dependency,
    Goal,
    Subtask,
    TaskGraph,
    TaskGraphMetadata,
    VerificationCriterion,
)
from .schema import TASK_GRAPH_SCHEMA_VERSION, TaskGraphSchemaError, validate_task_graph


def project_checkpoints(task_graph: TaskGraph) -> list[dict[str, Any]]:
    """Project semantic Subtasks into the current flat checkpoint interface."""

    issues = validate_task_graph(task_graph)
    if issues:
        raise TaskGraphSchemaError(issues)

    checkpoints: list[dict[str, Any]] = []
    for index, subtask in enumerate(task_graph.subtasks, start=1):
        criteria = [item.description for item in subtask.success_criteria]
        checkpoint_id = (
            subtask.checkpoint_ids[0]
            if subtask.checkpoint_ids
            else f"cp_{index:03d}"
        )
        checkpoints.append(
            {
                "name": subtask.name,
                # A flat verifier cannot express "one of N". Keep branch members
                # optional there; the TaskGraph remains authoritative.
                "required": subtask.required and not subtask.alternative_group_id,
                "preconditions": "；".join(subtask.preconditions),
                "expected_state": "；".join(criteria),
                "checkpoint_id": checkpoint_id,
                "subtask_id": subtask.subtask_id,
                "depends_on": list(subtask.depends_on),
                "success_criteria": criteria,
                "forbidden_states": list(subtask.forbidden_states),
                "risk_level": subtask.risk_level,
                "reversible": subtask.reversible,
                "allowed_reorder": subtask.allowed_reorder,
                "alternative_group_id": subtask.alternative_group_id,
            }
        )
    return checkpoints


def migrate_checkpoints_to_task_graph(
    instruction: str,
    checkpoints: Sequence[Mapping[str, Any]],
) -> TaskGraph:
    """Convert a legacy checkpoint list into a deterministic compatibility graph."""

    if not checkpoints:
        raise ValueError("at least one checkpoint is required for migration")
    if len(checkpoints) > 8:
        raise ValueError("at most eight checkpoints can be migrated")

    subtask_ids = _stable_subtask_ids(checkpoints)
    subtasks: list[Subtask] = []
    edges: list[Dependency] = []
    group_members: dict[str, list[str]] = defaultdict(list)
    raw_group_counts: dict[str, int] = defaultdict(int)
    for raw in checkpoints:
        group_id = _text(raw.get("alternative_group_id"))
        if group_id:
            raw_group_counts[group_id] += 1

    for index, (raw, subtask_id) in enumerate(zip(checkpoints, subtask_ids)):
        name = _text(raw.get("name")) or f"Checkpoint {index + 1}"
        criteria = _criteria(raw, index)
        explicit_dependencies = _string_list(raw.get("depends_on"))
        if explicit_dependencies:
            depends_on = tuple(explicit_dependencies)
        elif index and not _as_bool(raw.get("allowed_reorder", False)):
            depends_on = (subtask_ids[index - 1],)
        else:
            depends_on = ()

        candidate_group_id = _text(raw.get("alternative_group_id"))
        alternative_group_id = (
            candidate_group_id if raw_group_counts[candidate_group_id] >= 2 else ""
        )
        if alternative_group_id:
            group_members[alternative_group_id].append(subtask_id)

        checkpoint_id = _text(raw.get("checkpoint_id")) or f"cp_{index + 1:03d}"
        risk_level = _text(raw.get("risk_level")) or "low"
        if risk_level not in {"low", "medium", "high", "critical"}:
            risk_level = "low"
        subtask = Subtask(
            subtask_id=subtask_id,
            name=name,
            description=_text(raw.get("expected_state")) or name,
            required=_as_bool(raw.get("required", True)),
            depends_on=depends_on,
            preconditions=tuple(_preconditions(raw.get("preconditions"))),
            success_criteria=criteria,
            forbidden_states=tuple(_string_list(raw.get("forbidden_states"))),
            risk_level=risk_level,
            reversible=_as_bool(raw.get("reversible", True)),
            allowed_reorder=_as_bool(raw.get("allowed_reorder", False)),
            alternative_group_id=alternative_group_id,
            checkpoint_ids=(checkpoint_id,),
        )
        subtasks.append(subtask)
        edges.extend(
            Dependency(
                from_subtask_id=dependency_id,
                to_subtask_id=subtask_id,
                type="requires",
                condition=(
                    "；".join(subtask.preconditions)
                    or f"{dependency_id} is complete"
                ),
            )
            for dependency_id in depends_on
        )

    terminal_criteria = subtasks[-1].success_criteria
    graph = TaskGraph(
        schema_version=TASK_GRAPH_SCHEMA_VERSION,
        goal=Goal(
            description=_text(instruction) or "Complete the requested GUI task",
            success_criteria=tuple(
                VerificationCriterion(
                    criterion_id=f"vc_goal_{index:03d}",
                    description=criterion.description,
                    evidence_types=criterion.evidence_types,
                    required=criterion.required,
                )
                for index, criterion in enumerate(terminal_criteria, start=1)
            ),
        ),
        constraints=(),
        subtasks=tuple(subtasks),
        edges=tuple(edges),
        alternative_groups=tuple(
            AlternativeGroup(
                group_id=group_id,
                member_subtask_ids=tuple(members),
                required_count=1,
            )
            for group_id, members in sorted(group_members.items())
            if len(members) >= 2
        ),
        metadata=TaskGraphMetadata(
            source="checkpoint_migration",
            quality_status="compatibility_projection",
        ),
    )
    issues = validate_task_graph(graph)
    if issues:
        raise TaskGraphSchemaError(issues)
    return graph


def _stable_subtask_ids(checkpoints: Sequence[Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    used: set[str] = set()
    for index, checkpoint in enumerate(checkpoints, start=1):
        candidate = _text(checkpoint.get("subtask_id")) or f"st_{index:03d}"
        if candidate in used:
            candidate = f"st_{index:03d}"
        while candidate in used:
            candidate = f"{candidate}_{index}"
        used.add(candidate)
        result.append(candidate)
    return result


def _criteria(
    checkpoint: Mapping[str, Any],
    index: int,
) -> tuple[VerificationCriterion, ...]:
    descriptions = _string_list(checkpoint.get("success_criteria"))
    if not descriptions:
        descriptions = [
            _text(checkpoint.get("expected_state"))
            or _text(checkpoint.get("name"))
            or f"Checkpoint {index + 1} is visibly complete"
        ]
    return tuple(
        VerificationCriterion(
            criterion_id=f"vc_st_{index + 1:03d}_{criterion_index:02d}",
            description=description,
            evidence_types=("screenshot", "ocr"),
            required=True,
        )
        for criterion_index, description in enumerate(descriptions, start=1)
    )


def _preconditions(value: Any) -> list[str]:
    if isinstance(value, str):
        text = _text(value)
        return [text] if text else []
    return _string_list(value)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = _text(value)
        return [text] if text else []
    if not isinstance(value, Sequence):
        return []
    return [text for item in value if (text := _text(item))]


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "否", "非必需"}
    return bool(value)
