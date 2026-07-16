"""Checkpoint-to-step alignment for GUI trajectories."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .models import Checkpoint


@dataclass
class CheckpointAlignment:
    checkpoint_index: int
    step_index: int
    score: float
    confidence: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_index": self.checkpoint_index,
            "step_index": self.step_index,
            "score": round(self.score, 3),
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def align_checkpoints_to_steps(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    *,
    ab_report: Any = None,
    min_score: float = 0.18,
) -> list[CheckpointAlignment]:
    """Align checkpoints to source step indexes with monotonic ordering."""
    steps = _build_step_features(payload, ab_report)
    alignments: list[CheckpointAlignment] = []
    last_pos = -1

    for cp_idx, checkpoint in enumerate(checkpoints):
        candidates: list[tuple[int, dict[str, Any], float, list[str]]] = []
        cp_text = _checkpoint_text(checkpoint)
        for pos, step in enumerate(steps):
            if pos < last_pos:
                continue
            score, evidence = _score(cp_text, checkpoint, step)
            candidates.append((pos, step, score, evidence))

        best = _select_candidate(candidates, min_score=min_score)
        if best is None or best[2] < min_score:
            alignments.append(CheckpointAlignment(
                checkpoint_index=cp_idx,
                step_index=-1,
                score=0.0 if best is None else best[2],
                confidence="unmatched",
                evidence=["no reliable monotonic candidate"],
            ))
            continue

        last_pos = best[0]
        alignments.append(CheckpointAlignment(
            checkpoint_index=cp_idx,
            step_index=int(best[1]["source_step_index"]),
            score=best[2],
            confidence=_confidence(best[2]),
            evidence=best[3],
        ))

    return alignments



def _select_candidate(
    candidates: list[tuple[int, dict[str, Any], float, list[str]]],
    *,
    min_score: float,
    near_best_margin: float = 0.03,
) -> tuple[int, dict[str, Any], float, list[str]] | None:
    if not candidates:
        return None
    best_score = max(item[2] for item in candidates)
    if best_score < min_score:
        return max(candidates, key=lambda item: item[2])

    threshold = max(min_score, best_score - near_best_margin)
    for item in candidates:
        if item[2] >= threshold:
            return item
    return max(candidates, key=lambda item: item[2])


def build_checkpoint_step_data(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    alignments: list[CheckpointAlignment],
) -> list[dict[str, Any]]:
    """Build verifier step_data in checkpoint order."""
    del checkpoints
    seq_info = payload.get("seq_info") or []
    by_source = {int(s.get("index", pos)): (pos, s) for pos, s in enumerate(seq_info)}
    step_data: list[dict[str, Any]] = []

    for alignment in alignments:
        if alignment.step_index < 0 or alignment.step_index not in by_source:
            step_data.append({
                "step_index": -1,
                "before_step_index": -1,
                "after_step_index": -1,
                "before_image_base64": "",
                "after_image_base64": "",
                "before_image_ref": "",
                "after_image_ref": "",
                "image_available": False,
                "alignment": alignment.to_dict(),
            })
            continue

        pos, step = by_source[alignment.step_index]
        next_step = seq_info[pos + 1] if pos + 1 < len(seq_info) else {}
        parsed = (step.get("planning_output") or {}).get("parsed_action") or {}
        before_img = step.get("image_relative_path", "")
        after_img = next_step.get("image_relative_path", "")
        step_data.append({
            "before_image_base64": before_img,
            "after_image_base64": after_img,
            "before_image_ref": step.get("_image_original_ref", before_img),
            "after_image_ref": next_step.get("_image_original_ref", after_img),
            "before_step_index": int(step.get("index", alignment.step_index)),
            "after_step_index": int(next_step.get("index", -1)) if next_step else -1,
            "image_available": bool(before_img or after_img),
            "action_description": _action_description(parsed),
            "step_index": alignment.step_index,
            "alignment": alignment.to_dict(),
        })
    return step_data


def _build_step_features(payload: dict[str, Any], ab_report: Any) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for pos, step in enumerate(payload.get("seq_info") or []):
        parsed = (step.get("planning_output") or {}).get("parsed_action") or {}
        action_type = str(parsed.get("action_type", "")).strip().lower()
        if action_type in {"finished", "done"}:
            continue
        source_step = int(step.get("index", pos))
        ab = _ab_result(ab_report, source_step)
        features.append({
            "source_step_index": source_step,
            "action_type": action_type,
            "action_text": _action_description(parsed),
            "page_before": str(ab.get("pagea_description") or ""),
            "page_after": str(ab.get("pageb_description") or ""),
            "ab_action": str(ab.get("action_des") or ""),
        })
    return features


def _score(cp_text: str, checkpoint: Checkpoint, step: dict[str, Any]) -> tuple[float, list[str]]:
    evidence: list[str] = []
    action_text = f"{step['action_text']} {step['ab_action']}".strip()
    page_text = f"{step['page_before']} {step['page_after']}".strip()
    all_step_text = f"{action_text} {page_text}"

    action_score = _similarity(cp_text, action_text)
    page_score = _similarity(_checkpoint_state_text(checkpoint), page_text)
    keyword_score = _keyword_overlap(cp_text, all_step_text)
    semantic_score, semantic_evidence = _semantic_score(cp_text, checkpoint, step, all_step_text)
    type_bonus = 0.0

    if step["action_type"] in {"click", "open_app", "type", "set_text"}:
        type_bonus = 0.05
    if action_score >= 0.25:
        evidence.append(f"action_similarity={action_score:.2f}")
    if page_score >= 0.20:
        evidence.append(f"page_similarity={page_score:.2f}")
    if keyword_score > 0:
        evidence.append(f"keyword_overlap={keyword_score:.2f}")
    if semantic_score > 0:
        evidence.extend(semantic_evidence)

    score = (
        0.30 * action_score
        + 0.25 * page_score
        + 0.20 * keyword_score
        + 0.20 * semantic_score
        + type_bonus
    )
    return min(score, 1.0), evidence or ["weak text candidate"]


def _ab_result(ab_report: Any, step_index: int) -> dict[str, Any]:
    if ab_report is None:
        return {}
    if isinstance(ab_report, dict):
        results = ab_report.get("results") or ab_report.get("ab_pages_result") or {}
        item = results.get(str(step_index)) or results.get(step_index) or {}
        return item if isinstance(item, dict) else {}
    if hasattr(ab_report, "get"):
        item = ab_report.get(step_index)
        if hasattr(item, "to_dict"):
            return item.to_dict()
        return item if isinstance(item, dict) else {}
    return {}


def _checkpoint_text(checkpoint: Checkpoint) -> str:
    return " ".join([
        checkpoint.name or "",
        checkpoint.expected_state or "",
        checkpoint.preconditions or "",
    ]).strip().lower()


def _checkpoint_state_text(checkpoint: Checkpoint) -> str:
    return " ".join([checkpoint.expected_state or "", checkpoint.name or ""]).strip().lower()


def _action_description(parsed: dict[str, Any]) -> str:
    parts = [str(parsed.get("action_type", "")).strip()]
    for key in ("text", "content", "direction"):
        value = str(parsed.get(key, "")).strip()
        if value:
            parts.append(value)
    return ": ".join([parts[0], " ".join(parts[1:])]) if parts[0] else " ".join(parts[1:])


def _semantic_score(
    cp_text: str,
    checkpoint: Checkpoint,
    step: dict[str, Any],
    step_text: str,
) -> tuple[float, list[str]]:
    cp_tokens = set(_tokens(cp_text))
    state_tokens = set(_tokens(_checkpoint_state_text(checkpoint)))
    step_tokens = set(_tokens(step_text))
    action_tokens = set(_tokens(step.get("action_text", "")))
    page_after_tokens = set(_tokens(step.get("page_after", "")))

    evidence: list[str] = []
    scores: list[float] = []

    coverage = _coverage(cp_tokens, step_tokens)
    if coverage > 0:
        scores.append(coverage)
        evidence.append(f"semantic_checkpoint_coverage={coverage:.2f}")

    state_coverage = _coverage(state_tokens, page_after_tokens or step_tokens)
    if state_coverage > 0:
        scores.append(state_coverage)
        evidence.append(f"semantic_state_coverage={state_coverage:.2f}")

    action_coverage = _coverage(cp_tokens, action_tokens)
    if action_coverage > 0:
        scores.append(action_coverage * 0.8)
        evidence.append(f"semantic_action_coverage={action_coverage:.2f}")

    type_score = _action_type_score(cp_text, step.get("action_type", ""))
    if type_score > 0:
        scores.append(type_score)
        evidence.append(f"semantic_action_type={type_score:.2f}")

    if not scores:
        return 0.0, []
    return min(max(scores), 1.0), evidence[:3]


def _coverage(left_tokens: set[str], right_tokens: set[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _action_type_score(cp_text: str, action_type: str) -> float:
    cp = _compact(cp_text)
    if action_type in {"type", "set_text"} and _contains_any(cp, ("input", "enter", "type", "fill", "\u8f93\u5165", "\u586b\u5199")):
        return 0.7
    if action_type == "open_app" and _contains_any(cp, ("open", "launch", "start", "\u6253\u5f00", "\u542f\u52a8")):
        return 0.7
    if action_type in {"click", "long_press"} and _contains_any(cp, ("click", "tap", "select", "press", "\u70b9\u51fb", "\u9009\u62e9", "\u786e\u8ba4")):
        return 0.6
    if action_type in {"scroll", "swipe", "drag"} and _contains_any(cp, ("scroll", "swipe", "drag", "\u6ed1\u52a8", "\u6eda\u52a8", "\u62d6\u52a8")):
        return 0.6
    if action_type == "back" and _contains_any(cp, ("back", "return", "\u8fd4\u56de")):
        return 0.6
    return 0.0


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(_compact(token) in text for token in tokens)

def _similarity(left: str, right: str) -> float:
    left = _compact(left)
    right = _compact(right)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return min(len(left), len(right)) / max(len(left), len(right))
    return SequenceMatcher(None, left, right).ratio()


def _keyword_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _tokens(value: str) -> list[str]:
    return [t for t in _compact(value).replace(":", " ").split() if len(t) >= 2]


def _compact(value: str) -> str:
    return " ".join(str(value).lower().split())


def _confidence(score: float) -> str:
    if score >= 0.55:
        return "high"
    if score >= 0.32:
        return "medium"
    return "low"
