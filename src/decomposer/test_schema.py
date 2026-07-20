from __future__ import annotations

from copy import deepcopy

import pytest

from .schema import (
    TaskGraphSchemaError,
    decode_task_annotation,
    decode_task_graph,
    dumps_task_annotation,
    dumps_task_graph,
    encode_task_annotation,
    encode_task_graph,
    loads_task_annotation,
    loads_task_graph,
)


def _criterion(criterion_id: str, description: str) -> dict:
    return {
        "criterion_id": criterion_id,
        "description": description,
        "evidence_types": ["screenshot", "ocr"],
        "required": True,
    }


def _subtask(
    subtask_id: str,
    name: str,
    *,
    depends_on: list[str] | None = None,
    alternative_group_id: str = "",
) -> dict:
    return {
        "subtask_id": subtask_id,
        "name": name,
        "description": f"Observable outcome for {name}",
        "required": True,
        "depends_on": depends_on or [],
        "preconditions": [],
        "success_criteria": [
            _criterion(f"vc_{subtask_id}_01", f"The page visibly confirms {name}")
        ],
        "forbidden_states": [],
        "risk_level": "low",
        "reversible": True,
        "allowed_reorder": False,
        "alternative_group_id": alternative_group_id,
        "checkpoint_ids": [f"cp_{subtask_id}"],
    }


def valid_task_graph_data() -> dict:
    return {
        "schema_version": "task_graph.v1",
        "goal": {
            "description": "Enable the requested sample feature",
            "success_criteria": [
                _criterion("vc_goal_01", "The sample feature visibly shows enabled")
            ],
        },
        "constraints": [
            {
                "constraint_id": "constraint_001",
                "type": "must_not",
                "description": "Do not change unrelated sample settings",
                "observable_condition": "Unrelated sample settings keep their prior values",
            }
        ],
        "subtasks": [
            _subtask("st_001", "Sample application is ready"),
            _subtask(
                "st_002",
                "Target sample page is visible",
                depends_on=["st_001"],
            ),
            _subtask(
                "st_003",
                "Requested sample feature is enabled",
                depends_on=["st_002"],
            ),
        ],
        "edges": [
            {
                "from": "st_001",
                "to": "st_002",
                "type": "requires",
                "condition": "The sample application is ready",
            },
            {
                "from": "st_002",
                "to": "st_003",
                "type": "requires",
                "condition": "The target sample page is visible",
            },
        ],
        "alternative_groups": [],
        "metadata": {
            "source": "synthetic_fixture",
            "model": "",
            "rag_hits": [],
            "quality_status": "ok",
        },
    }


def valid_annotation_data() -> dict:
    return {
        "schema_version": "task_annotation.v1",
        "annotation_id": "annotation_synthetic_001",
        "task_id": "task_synthetic_001",
        "app": {
            "app_name": "Sample App",
            "package_name": "example.invalid.sample",
            "app_version": "1.0",
            "platform": "synthetic",
            "language": "en",
        },
        "instruction": "Enable the requested sample feature",
        "source": {
            "source_ref": "remote-dataset:task_synthetic_001",
            "step_count": 6,
            "artifact_types": [
                "utg",
                "clear_res",
                "screenshot",
                "ui_tree",
                "ocr",
                "action_purpose",
            ],
        },
        "task_graph": valid_task_graph_data(),
        "subtask_annotations": [
            {
                "subtask_id": "st_001",
                "status": "achieved",
                "attempt_spans": [{"start_step_index": 0, "end_step_index": 1}],
                "evidence_ids": ["ev_001"],
                "notes": "",
            },
            {
                "subtask_id": "st_002",
                "status": "achieved",
                "attempt_spans": [{"start_step_index": 2, "end_step_index": 3}],
                "evidence_ids": ["ev_002"],
                "notes": "",
            },
            {
                "subtask_id": "st_003",
                "status": "achieved",
                "attempt_spans": [{"start_step_index": 4, "end_step_index": 5}],
                "evidence_ids": ["ev_003"],
                "notes": "",
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev_001",
                "evidence_type": "screenshot",
                "step_index": 1,
                "source_step_id": "synthetic_step_1",
                "artifact_ref": "artifact:screenshot:1",
                "description": "Sample application home is visible",
            },
            {
                "evidence_id": "ev_002",
                "evidence_type": "ui_tree",
                "step_index": 3,
                "source_step_id": "synthetic_step_3",
                "artifact_ref": "artifact:ui-tree:3",
                "description": "Target sample page node is present",
            },
            {
                "evidence_id": "ev_003",
                "evidence_type": "ocr",
                "step_index": 5,
                "source_step_id": "synthetic_step_5",
                "artifact_ref": "artifact:ocr:5",
                "description": "Enabled state text is visible",
            },
        ],
        "first_error": None,
        "recovery": {
            "attempted": False,
            "outcome": "none",
            "start_step_index": -1,
            "end_step_index": -1,
            "evidence_ids": [],
        },
        "metadata": {
            "annotator": "synthetic_test",
            "revision": 1,
            "notes": "No real trajectory data is embedded",
        },
    }


def issue_codes(exc: TaskGraphSchemaError) -> set[str]:
    return {issue.code for issue in exc.issues}


def test_task_graph_round_trip() -> None:
    graph = decode_task_graph(valid_task_graph_data())

    assert encode_task_graph(graph) == valid_task_graph_data()
    assert loads_task_graph(dumps_task_graph(graph)) == graph


def test_task_annotation_round_trip() -> None:
    annotation = decode_task_annotation(valid_annotation_data())

    assert encode_task_annotation(annotation) == valid_annotation_data()
    assert loads_task_annotation(dumps_task_annotation(annotation)) == annotation


def test_schema_rejects_unknown_raw_data_fields() -> None:
    data = valid_annotation_data()
    data["raw_utg"] = {"nodes": []}

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_annotation(data)

    assert issue_codes(error.value) == {"unknown_field"}


def test_annotation_rejects_paths_and_urls_as_remote_references() -> None:
    data = valid_annotation_data()
    data["source"]["source_ref"] = "D:\\private\\task_synthetic_001"
    data["evidence"][0]["artifact_ref"] = "https://example.invalid/signed-image"

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_annotation(data)

    assert issue_codes(error.value) == {"non_opaque_reference"}


def test_schema_rejects_unsupported_version() -> None:
    data = valid_task_graph_data()
    data["schema_version"] = "task_graph.v2"

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_graph(data)

    assert "unsupported_schema_version" in issue_codes(error.value)


def test_schema_enforces_semantic_subtask_count() -> None:
    data = valid_task_graph_data()
    data["subtasks"] = data["subtasks"][:2]
    data["edges"] = data["edges"][:1]

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_graph(data)

    assert "invalid_subtask_count" in issue_codes(error.value)


def test_schema_detects_dependency_cycle() -> None:
    data = valid_task_graph_data()
    data["subtasks"][0]["depends_on"] = ["st_003"]
    data["edges"].append(
        {
            "from": "st_003",
            "to": "st_001",
            "type": "requires",
            "condition": "Synthetic cycle",
        }
    )

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_graph(data)

    assert "dependency_cycle" in issue_codes(error.value)


def test_schema_detects_unknown_dependency_and_edge_mismatch() -> None:
    data = valid_task_graph_data()
    data["subtasks"][2]["depends_on"] = ["st_missing"]

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_graph(data)

    assert {"unknown_dependency", "missing_requires_edge", "missing_depends_on"} <= issue_codes(
        error.value
    )


def test_schema_rejects_action_level_and_unobservable_subtask() -> None:
    data = valid_task_graph_data()
    data["subtasks"][0]["name"] = "Click sample button"
    data["subtasks"][0]["success_criteria"][0]["evidence_types"] = []

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_graph(data)

    assert {"action_level_subtask", "missing_evidence_type"} <= issue_codes(error.value)


def test_schema_validates_alternative_group_membership() -> None:
    data = valid_task_graph_data()
    data["subtasks"].append(
        _subtask(
            "st_004",
            "Alternate sample page is visible",
            depends_on=["st_001"],
            alternative_group_id="alt_001",
        )
    )
    data["subtasks"][1]["alternative_group_id"] = "alt_001"
    data["edges"].append(
        {
            "from": "st_001",
            "to": "st_004",
            "type": "requires",
            "condition": "The sample application is ready",
        }
    )
    data["alternative_groups"] = [
        {
            "group_id": "alt_001",
            "member_subtask_ids": ["st_002", "st_004"],
            "required_count": 1,
        }
    ]

    graph = decode_task_graph(data)

    assert graph.alternative_groups[0].member_subtask_ids == ("st_002", "st_004")


def test_annotation_requires_one_label_per_subtask() -> None:
    data = valid_annotation_data()
    data["subtask_annotations"] = data["subtask_annotations"][:-1]

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_annotation(data)

    assert "missing_subtask_annotation" in issue_codes(error.value)


def test_annotation_validates_spans_and_evidence_references() -> None:
    data = valid_annotation_data()
    data["subtask_annotations"][0]["attempt_spans"] = [
        {"start_step_index": 4, "end_step_index": 2}
    ]
    data["subtask_annotations"][0]["evidence_ids"] = ["ev_missing"]

    with pytest.raises(TaskGraphSchemaError) as error:
        decode_task_annotation(data)

    assert {"invalid_step_span", "unknown_evidence"} <= issue_codes(error.value)


def test_annotation_validates_first_error_and_recovery() -> None:
    data = deepcopy(valid_annotation_data())
    data["first_error"] = {
        "error_type": "execution_blocked",
        "step_index": 2,
        "subtask_id": "st_002",
        "evidence_ids": ["ev_002"],
    }
    data["recovery"] = {
        "attempted": True,
        "outcome": "successful",
        "start_step_index": 3,
        "end_step_index": 5,
        "evidence_ids": ["ev_003"],
    }

    annotation = decode_task_annotation(data)

    assert annotation.first_error is not None
    assert annotation.first_error.error_type == "execution_blocked"
    assert annotation.recovery is not None
    assert annotation.recovery.outcome == "successful"
