from __future__ import annotations

from copy import deepcopy

from src.decomposer.projection import migrate_checkpoints_to_task_graph
from src.decomposer.schema import decode_task_graph, encode_task_graph
from src.decomposer.test_schema import valid_task_graph_data

from .models import NormalizedTask
from .pipeline import _run_decomposer
from .write_payload import write_payload


class FakeDecomposer:
    graph = None
    checkpoints: list[dict] = []
    graph_calls = 0
    checkpoint_calls = 0

    def __init__(self, **_kwargs):
        self.last_error = ""
        self.last_response_head = "synthetic"
        self.last_quality_issues: list[str] = []
        self.refinement_attempted = False

    def decompose_graph(self, *_args, **_kwargs):
        type(self).graph_calls += 1
        if self.graph is None:
            self.last_error = "synthetic invalid graph"
            self.last_quality_issues = ["synthetic graph issue"]
            self.refinement_attempted = True
        return self.graph

    def decompose(self, *_args, **_kwargs):
        type(self).checkpoint_calls += 1
        return deepcopy(self.checkpoints)


def _configure(monkeypatch, *, task_graph_enabled: bool) -> None:
    monkeypatch.setenv("LLM_MODEL_URL", "http://unused")
    monkeypatch.setenv("LLM_MODEL_NAME", "synthetic-model")
    monkeypatch.setenv("TASK_GRAPH_ENABLED", "1" if task_graph_enabled else "0")
    monkeypatch.setattr("src.decomposer.decomposer.Decomposer", FakeDecomposer)
    FakeDecomposer.graph_calls = 0
    FakeDecomposer.checkpoint_calls = 0


def test_feature_flag_off_preserves_legacy_decomposition(monkeypatch) -> None:
    _configure(monkeypatch, task_graph_enabled=False)
    FakeDecomposer.graph = decode_task_graph(valid_task_graph_data())
    FakeDecomposer.checkpoints = [
        {"name": "Legacy state", "required": True, "expected_state": "Visible"}
    ]
    task = NormalizedTask(task_uuid="synthetic", instruction="Synthetic task")

    count = _run_decomposer(task)

    assert count == 1
    assert FakeDecomposer.graph_calls == 0
    assert FakeDecomposer.checkpoint_calls == 1
    assert task.task_graph == {}
    assert task.decomposer_status["graph_status"] == "disabled"


def test_feature_flag_on_projects_valid_task_graph(monkeypatch) -> None:
    _configure(monkeypatch, task_graph_enabled=True)
    FakeDecomposer.graph = decode_task_graph(valid_task_graph_data())
    FakeDecomposer.checkpoints = []
    task = NormalizedTask(task_uuid="synthetic", instruction="Synthetic task")

    count = _run_decomposer(task)

    assert count == 3
    assert FakeDecomposer.graph_calls == 1
    assert FakeDecomposer.checkpoint_calls == 0
    assert task.task_graph["schema_version"] == "task_graph.v1"
    assert task.decomposer_status["graph_status"] == "ok"
    assert task.decomposer_status["checkpoint_source"] == "graph_projection"


def test_invalid_graph_falls_back_to_legacy_and_migrates(monkeypatch) -> None:
    _configure(monkeypatch, task_graph_enabled=True)
    FakeDecomposer.graph = None
    FakeDecomposer.checkpoints = [
        {
            "name": "Fallback state",
            "required": True,
            "preconditions": "",
            "expected_state": "Fallback state is visible",
        }
    ]
    task = NormalizedTask(task_uuid="synthetic", instruction="Synthetic task")

    count = _run_decomposer(task)

    assert count == 1
    assert task.task_graph["metadata"]["source"] == "checkpoint_migration"
    assert task.decomposer_status["graph_status"] == "fallback_migrated"
    assert task.decomposer_status["graph_error"] == "synthetic invalid graph"


def test_payload_writes_dual_track_planning_output(tmp_path) -> None:
    task = NormalizedTask(task_uuid="synthetic", instruction="Synthetic task")
    graph = migrate_checkpoints_to_task_graph(
        task.instruction,
        [{"name": "Target state", "expected_state": "Target state is visible"}],
    )
    task.task_graph = encode_task_graph(graph)
    task.checkpoints = [
        {"name": "Target state", "required": True, "expected_state": "Target state is visible"}
    ]

    payload = write_payload(task, tmp_path / "payload.json")

    assert payload["_task_graph"]["schema_version"] == "task_graph.v1"
    assert payload["_task_graph_schema_version"] == "task_graph.v1"
    assert payload["_checkpoints"] == task.checkpoints
    assert payload["step_level_instruction"] == "Target state"


def test_payload_without_task_graph_keeps_existing_shape(tmp_path) -> None:
    task = NormalizedTask(task_uuid="synthetic", instruction="Synthetic task")
    task.checkpoints = [
        {"name": "Legacy state", "required": True, "expected_state": "Visible"}
    ]

    payload = write_payload(task, tmp_path / "payload.json")

    assert payload["_checkpoints"] == task.checkpoints
    assert "_task_graph" not in payload
    assert "_task_graph_schema_version" not in payload
