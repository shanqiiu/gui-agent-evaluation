"""
State aggregator: merges raw state boundaries into meaningful KeyState objects,
handles state dedup, and detects back-tracking / loops.
"""

from __future__ import annotations

from .models import AlignedStep, KeyState
from .boundary import compute_ocr_fingerprint


def aggregate_states(steps: list[AlignedStep], boundaries: list[int]) -> list[KeyState]:
    """
    Group steps into states based on detected boundaries.
    
    boundaries[i] to boundaries[i+1] defines one state.
    """
    if not boundaries or not steps:
        return []

    states: list[KeyState] = []

    for i in range(len(boundaries)):
        start_idx = boundaries[i]
        end_idx = boundaries[i + 1] if i + 1 < len(boundaries) else len(steps)
        state_steps = steps[start_idx:end_idx]

        if not state_steps:
            continue

        # Determine state type
        last_class = state_steps[-1].purpose_classification
        if last_class == "terminal":
            state_type = "terminal"
        elif len(state_steps) == 1 and state_steps[0].purpose_classification == "state_transition":
            state_type = "transient"
        else:
            state_type = "stable"

        # Representative fingerprint
        fingerprints = [
            compute_ocr_fingerprint(s.ocr_tree_root)
            for s in state_steps
            if s.ocr_tree_root
        ]
        rep_fingerprint = _mode(fingerprints) if fingerprints else ""

        # Representative pHash (use median step's pHash)
        mid_idx = len(state_steps) // 2
        rep_phash = state_steps[mid_idx].screenshot_phash if state_steps else ""

        # Action summary
        action_summary = [
            s.action_purpose for s in state_steps if s.action_purpose
        ][:5]  # Cap at 5

        # Label
        label = _generate_state_label(state_steps)

        # Duration
        duration = sum(s.cost_time_ms for s in state_steps)

        # Confidence: based on classification consistency
        classifications = [s.purpose_classification for s in state_steps]
        consistent = all(c == classifications[0] for c in classifications)
        confidence = 0.85 if consistent else 0.65

        states.append(KeyState(
            state_id=f"s_{i}",
            state_type=state_type,
            label=label,
            ocr_fingerprint=rep_fingerprint,
            phash_fingerprint=rep_phash,
            step_indices=list(range(start_idx, end_idx)),
            step_range=(start_idx, end_idx),
            action_summary=action_summary,
            duration_ms=duration,
            first_seen_step=start_idx,
            last_seen_step=end_idx - 1,
            confidence=confidence,
            boundary_evidence=[f"边界 {i}: step {start_idx}"],
        ))

    # Merge consecutive similar states
    return merge_states(states)


def merge_states(states: list[KeyState]) -> list[KeyState]:
    """Merge consecutive states with the same OCR fingerprint."""
    if not states:
        return []

    merged: list[KeyState] = [states[0]]
    for s in states[1:]:
        prev = merged[-1]
        if prev.ocr_fingerprint == s.ocr_fingerprint and prev.ocr_fingerprint:
            # Same page — merge
            prev.step_indices.extend(s.step_indices)
            prev.step_range = (prev.step_range[0], s.step_range[1])
            prev.duration_ms += s.duration_ms
            prev.action_summary.extend(s.action_summary[:3])
            prev.last_seen_step = s.last_seen_step
            prev.confidence = (prev.confidence + s.confidence) / 2
        else:
            merged.append(s)

    # Filter transient states (single step, < 500ms) between same states
    filtered = _filter_transient_noise(merged)
    return filtered


def _filter_transient_noise(states: list[KeyState]) -> list[KeyState]:
    """Remove noise: transient states between two identical states."""
    if len(states) < 3:
        return states

    result: list[KeyState] = [states[0]]
    for i in range(1, len(states) - 1):
        prev = result[-1]
        curr = states[i]
        nxt = states[i + 1]
        if (curr.state_type == "transient"
                and curr.duration_ms < 500
                and prev.ocr_fingerprint == nxt.ocr_fingerprint):
            # Skip this transient noise
            continue
        result.append(curr)
    result.append(states[-1])
    return result


def _mode(values: list[str]) -> str:
    """Return the most common value in a list."""
    if not values:
        return ""
    from collections import Counter
    return Counter(values).most_common(1)[0][0]


def _generate_state_label(steps: list[AlignedStep]) -> str:
    """Generate a human-readable label for a state."""
    if not steps:
        return "未知状态"

    # Try to extract from transition purpose
    for s in steps:
        if s.purpose_classification == "state_transition" and s.action_purpose:
            # Extract target: "点击隐私和安全进入隐私设置页面" → "隐私设置页"
            import re
            m = re.search(r"(进入|打开)(.+?)(页面|应用|设置|功能|界面)?", s.action_purpose)
            if m:
                target = m.group(2).strip()
                suffix = m.group(3) or ""
                if suffix:
                    return target + suffix
                return target + "页面"

    # Use first step's action target
    for s in steps:
        if s.action_target:
            return s.action_target

    # Use classification as fallback
    first_class = steps[0].purpose_classification
    labels = {
        "state_transition": "过渡状态",
        "in_state_exploration": "浏览状态",
        "in_state_interaction": "交互状态",
        "terminal": "终端状态",
    }
    return labels.get(first_class, "未知状态")
