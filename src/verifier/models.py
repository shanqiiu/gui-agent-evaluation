"""Models for checkpoint verification via VLM screenshot comparison.

Module B checks: given a checkpoint description + before/after screenshots + action info,
determine whether the checkpoint's expected state has been achieved.

Status:
    达成 (Achieved)   — After screenshot matches checkpoint expected_state.
    未达成 (Not Achieved) — After screenshot does not match expected state.
    不确定 (Uncertain) — Insufficient signal, low confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Checkpoint:
    """A single checkpoint to verify, produced by Module A decomposer."""

    name: str                                    # "点击隐私和安全"
    required: bool = True                        # is this checkpoint mandatory?
    preconditions: str = ""                      # "已进入设置首页"
    expected_state: str = ""                     # "进入隐私设置页面"
    checkpoint_id: str = ""                      # unique identifier (optional)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "preconditions": self.preconditions,
            "expected_state": self.expected_state,
            "checkpoint_id": self.checkpoint_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Checkpoint:
        return cls(
            name=d.get("name", ""),
            required=d.get("required", True),
            preconditions=d.get("preconditions", ""),
            expected_state=d.get("expected_state", ""),
            checkpoint_id=d.get("checkpoint_id", ""),
        )


@dataclass
class CheckpointResult:
    """Verification result for a single checkpoint."""

    checkpoint: Checkpoint
    status: str                                  # "达成" | "未达成" | "不确定"
    confidence: float                            # 0.0 – 1.0
    evidence: str = ""                           # VLM reasoning chain

    # Metadata about the verification
    step_index: int = -1                         # which action step was being verified
    before_image: str = ""                       # reference to the before screenshot
    after_image: str = ""                        # reference to the after screenshot
    action_description: str = ""                 # what the Agent did

    # Flag for when VLM call failed and we fell back to heuristics
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "step_index": self.step_index,
            "action_description": self.action_description,
            "fallback": self.fallback,
        }


@dataclass
class VerificationReport:
    """Aggregated verification results across all checkpoints for a task."""

    task_uuid: str
    instruction: str

    # ── Results ──
    results: list[CheckpointResult] = field(default_factory=list)

    # ── Summary ──
    total_checkpoints: int = 0
    achieved_count: int = 0
    not_achieved_count: int = 0
    uncertain_count: int = 0
    required_total: int = 0                     # mandatory checkpoints
    required_achieved: int = 0                   # mandatory checkpoints achieved

    # ── Composite scores ──
    completion_score: float = 0.0                # achieved / total (0.0-1.0)
    required_completion_score: float = 0.0       # required_achieved / required_total
    overall_status: str = "未判定"               # "优秀" | "良好" | "失败" | "未判定"

    # ── Evidence ──
    evidence: list[str] = field(default_factory=list)
    model_used: str = ""                         # which VLM model was used
    total_vlm_calls: int = 0
    fallback_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_uuid": self.task_uuid,
            "instruction": self.instruction,
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total_checkpoints": self.total_checkpoints,
                "achieved": self.achieved_count,
                "not_achieved": self.not_achieved_count,
                "uncertain": self.uncertain_count,
                "required_total": self.required_total,
                "required_achieved": self.required_achieved,
            },
            "completion_score": round(self.completion_score, 3),
            "required_completion_score": round(self.required_completion_score, 3),
            "overall_status": self.overall_status,
            "evidence": self.evidence,
            "model_used": self.model_used,
            "total_vlm_calls": self.total_vlm_calls,
            "fallback_count": self.fallback_count,
        }


@dataclass
class VerifierConfig:
    """Configuration for the checkpoint verifier."""

    # VLM endpoint (OpenAI-compatible chat/completions)
    vlm_model_url: str = "http://localhost:8000/v1/chat/completions"
    vlm_model_name: str = "qwen3-vl-8b"
    vlm_api_key: str = ""

    # Request settings
    temperature: float = 0.0
    max_tokens: int = 1024
    request_timeout: int = 120

    # Confidence thresholds
    high_confidence_threshold: float = 0.75      # above → "达成" or "未达成"
    low_confidence_threshold: float = 0.5         # below → "不确定"

    # Fallback behaviour
    max_retries: int = 2                          # VLM call retries
    enable_heuristic_fallback: bool = True         # if VLM fails, use rules?
    mock_mode: bool = False                        # for testing without VLM server
