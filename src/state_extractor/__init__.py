"""src/state_extractor — 轨迹状态提取引擎（v2.0 MVP）

Based on: docs/新增方案2.0.md

Pipeline:
    utg.json + clearRes → parse → resolve → detect → aggregate → build → StateGraph
"""

from .pipeline import extract_states, run_pipeline
from .models import (
    AlignedStep,
    KeyState,
    OCRNode,
    PipelineContext,
    StateGraph,
    StateTransition,
    UTGEdge,
    UTGNode,
    UTGStep,
)
from .mock_data import generate_mock_task

__all__ = [
    "extract_states",
    "run_pipeline",
    "generate_mock_task",
    "AlignedStep",
    "KeyState",
    "OCRNode",
    "PipelineContext",
    "StateGraph",
    "StateTransition",
    "UTGEdge",
    "UTGNode",
    "UTGStep",
]
