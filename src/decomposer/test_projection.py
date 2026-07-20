from __future__ import annotations

from copy import deepcopy

from .projection import migrate_checkpoints_to_task_graph, project_checkpoints
from .schema import decode_task_graph, encode_task_graph
from .test_schema import _subtask, valid_task_graph_data


def test_project_linear_graph_to_enriched_checkpoints() -> None:
    graph = decode_task_graph(valid_task_graph_data())

    checkpoints = project_checkpoints(graph)

    assert [item["subtask_id"] for item in checkpoints] == [
        "st_001",
        "st_002",
        "st_003",
    ]
    assert checkpoints[1]["depends_on"] == ["st_001"]
    assert checkpoints[1]["checkpoint_id"] == "cp_st_002"
    assert checkpoints[1]["expected_state"] == (
        "The page visibly confirms Target sample page is visible"
    )


def test_projection_preserves_allowed_reorder() -> None:
    data = deepcopy(valid_task_graph_data())
    data["subtasks"][1]["allowed_reorder"] = True
    data["subtasks"][1]["depends_on"] = []
    data["edges"] = data["edges"][1:]
    graph = decode_task_graph(data)

    checkpoints = project_checkpoints(graph)

    assert checkpoints[1]["allowed_reorder"] is True
    assert checkpoints[1]["depends_on"] == []


def test_projection_keeps_alternative_members_optional_for_legacy_verifier() -> None:
    data = deepcopy(valid_task_graph_data())
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
    checkpoints = project_checkpoints(decode_task_graph(data))

    branch_checkpoints = [
        item for item in checkpoints if item["alternative_group_id"] == "alt_001"
    ]
    assert len(branch_checkpoints) == 2
    assert all(item["required"] is False for item in branch_checkpoints)


def test_migrate_single_legacy_checkpoint_without_padding() -> None:
    graph = migrate_checkpoints_to_task_graph(
        "Enable the sample feature",
        [
            {
                "name": "Sample feature is enabled",
                "required": True,
                "preconditions": "Sample settings are visible",
                "expected_state": "The sample feature visibly shows enabled",
                "checkpoint_id": "legacy_cp_01",
            }
        ],
    )

    assert graph.metadata.source == "checkpoint_migration"
    assert len(graph.subtasks) == 1
    assert graph.subtasks[0].checkpoint_ids == ("legacy_cp_01",)
    assert decode_task_graph(encode_task_graph(graph)) == graph


def test_migrate_legacy_checkpoints_builds_stable_linear_dependencies() -> None:
    graph = migrate_checkpoints_to_task_graph(
        "Complete a synthetic flow",
        [
            {"name": "Sample page is visible", "expected_state": "Title is visible"},
            {"name": "Sample state is saved", "expected_state": "Saved state is visible"},
        ],
    )

    assert graph.subtasks[1].depends_on == ("st_001",)
    assert graph.edges[0].from_subtask_id == "st_001"
    assert graph.edges[0].to_subtask_id == "st_002"
