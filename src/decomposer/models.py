"""Domain models for TaskGraph decomposition and human annotations.

These models are intentionally independent from raw UTG/clearRes storage. Raw
trajectory data is normalized by the preprocessor; annotations only keep typed
labels and opaque references to remote evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerificationCriterion:
    criterion_id: str
    description: str
    evidence_types: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class Goal:
    description: str
    success_criteria: tuple[VerificationCriterion, ...]


@dataclass(frozen=True)
class Constraint:
    constraint_id: str
    type: str
    description: str
    observable_condition: str


@dataclass(frozen=True)
class Subtask:
    subtask_id: str
    name: str
    description: str
    required: bool
    depends_on: tuple[str, ...]
    preconditions: tuple[str, ...]
    success_criteria: tuple[VerificationCriterion, ...]
    forbidden_states: tuple[str, ...] = ()
    risk_level: str = "low"
    reversible: bool = True
    allowed_reorder: bool = False
    alternative_group_id: str = ""
    checkpoint_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dependency:
    from_subtask_id: str
    to_subtask_id: str
    type: str = "requires"
    condition: str = ""


@dataclass(frozen=True)
class AlternativeGroup:
    group_id: str
    member_subtask_ids: tuple[str, ...]
    required_count: int = 1


@dataclass(frozen=True)
class TaskGraphMetadata:
    source: str = ""
    model: str = ""
    rag_hits: tuple[str, ...] = ()
    quality_status: str = ""


@dataclass(frozen=True)
class TaskGraph:
    schema_version: str
    goal: Goal
    constraints: tuple[Constraint, ...]
    subtasks: tuple[Subtask, ...]
    edges: tuple[Dependency, ...]
    alternative_groups: tuple[AlternativeGroup, ...] = ()
    metadata: TaskGraphMetadata = field(default_factory=TaskGraphMetadata)


@dataclass(frozen=True)
class AppDescriptor:
    app_name: str
    package_name: str = ""
    app_version: str = ""
    platform: str = ""
    language: str = ""


@dataclass(frozen=True)
class TrajectorySource:
    """Privacy-safe pointer to trajectory data stored outside this repository."""

    source_ref: str
    step_count: int
    artifact_types: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    evidence_type: str
    step_index: int
    source_step_id: str = ""
    artifact_ref: str = ""
    description: str = ""


@dataclass(frozen=True)
class StepSpan:
    start_step_index: int
    end_step_index: int


@dataclass(frozen=True)
class SubtaskAnnotation:
    subtask_id: str
    status: str
    attempt_spans: tuple[StepSpan, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class FirstErrorAnnotation:
    error_type: str
    step_index: int
    subtask_id: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryAnnotation:
    attempted: bool
    outcome: str
    start_step_index: int = -1
    end_step_index: int = -1
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnnotationMetadata:
    annotator: str = ""
    revision: int = 1
    notes: str = ""


@dataclass(frozen=True)
class TaskAnnotation:
    schema_version: str
    annotation_id: str
    task_id: str
    app: AppDescriptor
    instruction: str
    source: TrajectorySource
    task_graph: TaskGraph
    subtask_annotations: tuple[SubtaskAnnotation, ...]
    evidence: tuple[EvidenceReference, ...]
    first_error: FirstErrorAnnotation | None = None
    recovery: RecoveryAnnotation | None = None
    metadata: AnnotationMetadata = field(default_factory=AnnotationMetadata)
