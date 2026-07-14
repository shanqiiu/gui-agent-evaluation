"""
State boundary detection.

Identifies where state transitions occur in the AlignedStep sequence
using actionPurpose classifications as boundary hints, verified by
visual (pHash) and structural (OCR fingerprint) checks.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from .models import AlignedStep, OCRNode


# ── pHash computation (mock for MVP; real impl uses imagehash lib) ─

def compute_phash(screenshot_path: str) -> str:
    """
    Compute perceptual hash of a screenshot.
    
    Mock implementation for MVP — returns a deterministic hash
    based on the screenshot path. In production, this would use
    the imagehash library (phash + dhash).
    """
    if not screenshot_path:
        return ""
    # Mock: use SHA-256 of path as pHash (real impl uses image content)
    return hashlib.sha256(screenshot_path.encode()).hexdigest()[:16]


def hamming_distance(phash1: str, phash2: str) -> int:
    """
    Compute Hamming distance between two pHash hex strings.
    
    For the mock pHash (SHA-based), we use the hex character differences
    as an approximation of visual similarity.
    """
    if not phash1 or not phash2:
        return 64  # max distance if missing
    # Mock: count differing hex characters
    return sum(1 for a, b in zip(phash1, phash2) if a != b) + abs(len(phash1) - len(phash2))


# ── OCR tree fingerprint ──────────────────────────────────────────

def compute_ocr_fingerprint(ocr_root: Optional[OCRNode]) -> str:
    """
    Compute a structural fingerprint of the OCR tree.
    
    Collects all visible text nodes with their types and normalized
    positions, then generates a SHA-256 hash.
    """
    if not ocr_root:
        return ""
    texts = ocr_root.collect_all_texts()

    # Normalize and sort for deterministic hashing
    features = []
    for t in texts:
        bounds = t.get("bounds", [])
        normalized_pos = ""
        if len(bounds) >= 4:
            # Normalize by screen dimensions (mock: 1280x2832)
            normalized_pos = (
                f"{(bounds[0] + bounds[2]) / 2560:.2f}_"
                f"{(bounds[1] + bounds[3]) / 5664:.2f}"
            )
        features.append(
            f"{t.get('type', '')}_{normalized_pos}_{hash(t.get('text', ''))}"
        )
    features.sort()
    return hashlib.sha256("|".join(features).encode()).hexdigest()[:16]


def ocr_fingerprint_changed(fp1: str, fp2: str) -> bool:
    """Check if two OCR fingerprints differ."""
    return fp1 != fp2


# ── State boundary detection ──────────────────────────────────────

def is_state_boundary(
    prev: AlignedStep,
    curr: AlignedStep,
    *,
    phash_threshold: int = 3,
) -> tuple[bool, list[str]]:
    """
    Determine if prev → curr represents a state boundary.
    
    Returns:
        (is_boundary: bool, evidence: list[str])
    """
    evidence: list[str] = []

    # Check 1: purpose-based hint
    if curr.purpose_classification == "state_transition":
        evidence.append(f"actionPurpose '{curr.action_purpose[:40]}' 标注为状态切换")

    if curr.purpose_classification == "terminal":
        evidence.append(f"actionPurpose 标注为终端状态")
        return True, evidence

    if curr.purpose_classification == "unknown":
        return False, []

    # Check 2: visual change (pHash)
    if prev.screenshot_phash and curr.screenshot_phash:
        hd = hamming_distance(prev.screenshot_phash, curr.screenshot_phash)
        if hd > phash_threshold:
            evidence.append(f"pHash 海明距离 {hd}，视觉显著变化")

    # Check 3: structural change (OCR fingerprint)
    fp_prev = compute_ocr_fingerprint(prev.ocr_tree_root)
    fp_curr = compute_ocr_fingerprint(curr.ocr_tree_root)
    if ocr_fingerprint_changed(fp_prev, fp_curr):
        evidence.append(f"OCR 指纹从 {fp_prev} 变为 {fp_curr}")

    # Decision logic
    if curr.purpose_classification == "state_transition" and len(evidence) >= 2:
        return True, evidence
    if not prev.action_target and curr.action_target:
        evidence.append("控件名称从不可解析变为可解析，可能进入新页面")

    return len(evidence) >= 2, evidence


def detect_boundaries(steps: list[AlignedStep]) -> list[int]:
    """
    Detect all state boundary step indices.
    
    Returns a list of step indices where state transitions occur.
    Includes index 0 as the implicit first state, and the last index
    as the terminal state.
    """
    if not steps:
        return []

    # Ensure pHash is computed
    for step in steps:
        if not step.screenshot_phash:
            step.screenshot_phash = compute_phash(step.screenshot_path)

    boundaries = [0]  # Always start with step 0

    for i in range(1, len(steps)):
        is_boundary, evidence = is_state_boundary(steps[i - 1], steps[i])
        if is_boundary:
            boundaries.append(i)

    # Ensure last step is always a boundary
    if boundaries[-1] != len(steps) - 1:
        boundaries.append(len(steps) - 1)

    return sorted(set(boundaries))
