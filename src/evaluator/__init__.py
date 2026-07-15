"""Evaluation orchestration entry points."""

from __future__ import annotations

from typing import Any

__all__ = [
    "RepeatedBaselineConfig",
    "run_repeated_baseline",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .repeated_baseline import RepeatedBaselineConfig, run_repeated_baseline

        exports = {
            "RepeatedBaselineConfig": RepeatedBaselineConfig,
            "run_repeated_baseline": run_repeated_baseline,
        }
        return exports[name]
    raise AttributeError(name)
