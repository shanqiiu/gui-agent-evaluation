"""
Unified intermediate data structures for the preprocessing pipeline.

A single NormalizedTask, produced once by preprocessor.py and consumed
by all three writers (payload / dedup / stategraph), replaces the
current fragmented parsing across multiple scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedStep:
    """All signals for a single Agent step, aligned and enriched."""

    step_id: str
    step_index: int                     # 0-based in action sequence

    # ── Action (from directives + stepData) ──
    action_type: str                    # "click" | "scroll" | "type" | "open_app" | "clarify" | "finished"
    action_start_box: list[int]         # [x, y] from params.points or node.bounds center
    action_end_box: list[int]           # [x, y] for multi-point gestures (scroll/swipe)
    action_target: str                  # resolved control name (from rawPage fallback if directives empty)
    action_content: str                 # input text (for type actions)
    action_direction: str               # "up" | "down" | "left" | "right" | ""
    action_raw_str: str                 # original stepData.action_type string
    cost_time_ms: int
    step_type: str                      # "AAS" | ""
    thought: str                        # AI thinking marker

    # ── Intent (from clearRes) ──
    action_purpose: str                 # Agent's self-reported reasoning

    # ── Screenshot ──
    screenshot_path: str                # local path: "catchDataTurnIdN/temp_image-screenshot-origin.jpg"
    screenshot_source: str              # original REST URL for tracing

    # ── Edge data (for dedup edges output) ──
    edge_from: int | str | None = None
    edge_to: int | str | None = None
    edge_events: list[dict] = field(default_factory=list)
    edge_view_images: list[str] = field(default_factory=list)

    # ── Node data (for dedup nodes output) ──
    node_id: int | str = ""
    node_label: str = ""
    node_shape: str = ""

    # ── OCR tree (for stategraph fingerprint) ──
    ocr_page_index: int = -1            # index into NormalizedTask.ocr_pages


@dataclass
class NormalizedTask:
    """Complete parsed and aligned data for a single task."""

    task_uuid: str
    instruction: str

    # All action steps (thinking/reflection steps filtered out)
    steps: list[NormalizedStep] = field(default_factory=list)

    # OCR tree snapshots (one per page/screen state)
    ocr_pages: list[dict] = field(default_factory=list)

    # ── Metadata ──
    total_raw_steps: int = 0            # original stepData count (incl. home/end)
    total_action_steps: int = 0         # filtered action steps
    total_duration_ms: int = 0
    app_name: str = ""

    # ── Module A checkpoints (optional) ──
    checkpoints: list[dict] = field(default_factory=list)
    task_graph: dict[str, Any] = field(default_factory=dict)

    @property
    def action_purposes(self) -> list[str]:
        """Extract actionPurpose list for all steps."""
        return [s.action_purpose for s in self.steps if s.action_purpose]

    @property
    def step_ids(self) -> list[str]:
        return [s.step_id for s in self.steps]
