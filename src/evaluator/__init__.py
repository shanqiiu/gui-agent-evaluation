"""Evaluation orchestration entry points."""

from __future__ import annotations

from typing import Any

__all__ = [
    "RepeatedBaselineConfig",
    "run_repeated_baseline",
    "run_repeated_baseline_batch",
    "StateSegment",
    "StateSequence",
    "StateTransition",
    "build_state_sequence",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .repeated_baseline import (
            RepeatedBaselineConfig,
            run_repeated_baseline,
            run_repeated_baseline_batch,
        )
        from .state_evidence import (
            StateSegment,
            StateSequence,
            StateTransition,
            build_state_sequence,
        )

        exports = {
            "RepeatedBaselineConfig": RepeatedBaselineConfig,
            "run_repeated_baseline": run_repeated_baseline,
            "run_repeated_baseline_batch": run_repeated_baseline_batch,
            "StateSegment": StateSegment,
            "StateSequence": StateSequence,
            "StateTransition": StateTransition,
            "build_state_sequence": build_state_sequence,
        }
        return exports[name]
    raise AttributeError(name)