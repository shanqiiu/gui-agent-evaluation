"""Module B — Checkpoint Verifier.

VLM-based checkpoint verification engine for GUI Agent trajectory evaluation.

Consumes checkpoint descriptions (from Module A decomposer) and before/after
screenshots to determine whether each checkpoint's expected state has been achieved.

Main entry points:
    CheckpointVerifier  — Core verification engine.
    verify_checkpoints  — Convenience function for batch verification.
"""

from .models import (
    Checkpoint,
    CheckpointResult,
    VerificationReport,
    VerifierConfig,
)
from .alignment import (
    CheckpointAlignment,
    align_checkpoints_to_steps,
    build_checkpoint_step_data,
)
from .verifier import CheckpointVerifier


def verify_checkpoints(
    checkpoints: list[Checkpoint],
    step_data: list[dict],
    *,
    task_uuid: str = "",
    instruction: str = "",
    config: VerifierConfig | None = None,
) -> VerificationReport:
    """Convenience function: verify all checkpoints with default configuration.

    Args:
        checkpoints: List of checkpoints from Module A decomposer.
        step_data: Per-checkpoint data dicts with before/after images and actions.
        task_uuid: Task identifier.
        instruction: Original task instruction.
        config: Optional VerifierConfig; uses defaults if None.

    Returns:
        VerificationReport.
    """
    verifier = CheckpointVerifier(config)
    return verifier.verify_checkpoints(
        checkpoints=checkpoints,
        step_data=step_data,
        task_uuid=task_uuid,
        instruction=instruction,
    )


__all__ = [
    "Checkpoint",
    "CheckpointAlignment",
    "CheckpointResult",
    "CheckpointVerifier",
    "VerificationReport",
    "VerifierConfig",
    "align_checkpoints_to_steps",
    "build_checkpoint_step_data",
    "verify_checkpoints",
]
