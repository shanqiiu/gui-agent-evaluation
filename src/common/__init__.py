"""Common detection pipeline — independent of Darwin oracle.

Provides:
    ABValidator              — VLM-based AB page transition validator
    RepeatedActionDetector   — Rule-based repeated action detector
    PlanningFailureDetector  — Rule-based planning failure detector

These modules consume payload.json + Module B (VerificationReport) outputs
and produce structured detection results for Module E (comprehensive evaluator).
"""

from .ab_validator import ABValidator, ABValidatorConfig
from .image_resolver import (
    ImageResolutionStats,
    hydrate_payload_images,
    resolve_image_reference,
)
from .models import (
    ABValidationReport,
    MissingCheckpoint,
    PlanningFailureEvent,
    PlanningFailureResult,
    RepeatedActionRange,
    RepeatedActionResult,
    StepABResult,
)
from .planning_failure_detector import (
    PlanningFailureConfig,
    PlanningFailureDetector,
    detect_planning_failures,
)
from .repeated_action_detector import (
    RepeatedActionConfig,
    RepeatedActionDetector,
    detect_repeated_actions,
)

__all__ = [
    "ABValidator",
    "ABValidatorConfig",
    "ABValidationReport",
    "ImageResolutionStats",
    "MissingCheckpoint",
    "PlanningFailureConfig",
    "PlanningFailureDetector",
    "PlanningFailureEvent",
    "PlanningFailureResult",
    "RepeatedActionConfig",
    "RepeatedActionDetector",
    "RepeatedActionRange",
    "RepeatedActionResult",
    "StepABResult",
    "detect_planning_failures",
    "detect_repeated_actions",
    "hydrate_payload_images",
    "resolve_image_reference",
]
