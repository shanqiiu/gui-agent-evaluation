"""Checkpoint intent matching and execution-step alignment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .models import Checkpoint


@dataclass
class IntentMatcherConfig:
    llm_model_url: str = ""
    llm_model_name: str = ""
    llm_api_key: str = ""
    mock_mode: bool = False
    request_timeout: int = 60
    max_candidates: int = 4
    prefer_purpose_matching: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentCandidate:
    source_kind: str
    step_index: int
    score: float
    evidence: list[str] = field(default_factory=list)
    state_id: str = ""
    step_range: list[int] = field(default_factory=list)
    purpose_index: int = -1
    purpose_text: str = ""
    start_step_index: int = -1
    end_step_index: int = -1
    start_purpose_index: int = -1
    end_purpose_index: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "step_index": self.step_index,
            "start_step_index": self.start_step_index,
            "end_step_index": self.end_step_index,
            "score": round(self.score, 3),
            "evidence": self.evidence,
            "state_id": self.state_id,
            "step_range": self.step_range,
            "purpose_index": self.purpose_index,
            "purpose_text": self.purpose_text,
            "start_purpose_index": self.start_purpose_index,
            "end_purpose_index": self.end_purpose_index,
        }


@dataclass
class CheckpointIntentMatch:
    checkpoint_index: int
    matched: bool
    score: float
    confidence: str
    candidate_steps: list[int] = field(default_factory=list)
    candidate_states: list[str] = field(default_factory=list)
    candidates: list[IntentCandidate] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    llm_used: bool = False
    llm_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_index": self.checkpoint_index,
            "matched": self.matched,
            "score": round(self.score, 3),
            "confidence": self.confidence,
            "candidate_steps": self.candidate_steps,
            "candidate_states": self.candidate_states,
            "candidates": [c.to_dict() for c in self.candidates],
            "evidence": self.evidence,
            "llm_used": self.llm_used,
            "llm_reason": self.llm_reason,
        }


@dataclass
class CheckpointAlignment:
    checkpoint_index: int
    step_index: int
    score: float
    confidence: str
    start_step_index: int = -1
    end_step_index: int = -1
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_index": self.checkpoint_index,
            "step_index": self.step_index,
            "start_step_index": self.start_step_index,
            "end_step_index": self.end_step_index,
            "score": round(self.score, 3),
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def match_checkpoint_intents(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    *,
    ab_report: Any = None,
    state_sequence: Any = None,
    config: IntentMatcherConfig | None = None,
    min_score: float = 0.18,
) -> list[CheckpointIntentMatch]:
    """Recall likely actual steps/states for each checkpoint at intent level."""
    config = config or IntentMatcherConfig()
    purpose_features = _build_purpose_features(payload)
    if config.prefer_purpose_matching and not purpose_features:
        config.diagnostics["purpose_llm"] = {
            "llm_configured": bool(config.llm_model_url and config.llm_model_name),
            "llm_attempted": False,
            "mock_mode": config.mock_mode,
            "model_url_set": bool(config.llm_model_url),
            "model_name": config.llm_model_name,
            "api_key_set": bool(config.llm_api_key),
            "purpose_feature_count": 0,
            "checkpoint_count": len(checkpoints),
            "returned_match_count": 0,
            "status": "skipped_no_purpose_features",
            "error": "payload has no action_purpose/_action_purposes/agent_purposes",
            "response_head": "",
        }
    if config.prefer_purpose_matching and purpose_features:
        matches = _match_checkpoint_purposes(
            checkpoints,
            payload,
            purpose_features,
            config,
            min_score=min_score,
        )
        if (
            any(match.llm_used for match in matches)
            or any(match.matched for match in matches)
            or not _build_alignment_features(payload, ab_report, state_sequence)
        ):
            return matches

    return _match_checkpoint_features(
        checkpoints,
        payload,
        ab_report=ab_report,
        state_sequence=state_sequence,
        config=config,
        min_score=min_score,
    )


def _match_checkpoint_purposes(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    purpose_features: list[dict[str, Any]],
    config: IntentMatcherConfig,
    *,
    min_score: float,
) -> list[CheckpointIntentMatch]:
    llm_matches = _llm_match_plan_to_purposes(checkpoints, payload, purpose_features, config)
    matches: list[CheckpointIntentMatch] = []
    last_purpose_pos = -1

    for cp_idx, checkpoint in enumerate(checkpoints):
        llm_item = llm_matches.get(cp_idx, {})
        if llm_item:
            match = _match_from_llm_item(
                cp_idx,
                llm_item,
                purpose_features,
                min_score=min_score,
                min_purpose_index=last_purpose_pos,
            )
            if match is not None:
                if match.matched and match.candidates:
                    last_purpose_pos = max(last_purpose_pos, match.candidates[0].end_purpose_index)
                matches.append(match)
                continue

        scored: list[tuple[int, dict[str, Any], float, list[str]]] = []
        cp_text = _checkpoint_text(checkpoint)
        for pos, feature in enumerate(purpose_features):
            if pos < last_purpose_pos:
                continue
            score, evidence = _score(cp_text, checkpoint, feature)
            scored.append((pos, feature, score, ["purpose_local_match"] + evidence))
        top = sorted(scored, key=lambda item: item[2], reverse=True)[: max(1, config.max_candidates)]
        best = _select_candidate(top, min_score=min_score)
        if best is None or best[2] < min_score:
            matches.append(CheckpointIntentMatch(
                checkpoint_index=cp_idx,
                matched=False,
                score=0.0 if best is None else best[2],
                confidence="unmatched_intent",
                candidates=[_to_intent_candidate(item) for item in top],
                evidence=["purpose intent match found no reliable candidate"],
                llm_used=False,
            ))
            continue
        last_purpose_pos = best[0]
        candidate = _to_intent_candidate(best)
        matches.append(CheckpointIntentMatch(
            checkpoint_index=cp_idx,
            matched=True,
            score=best[2],
            confidence=_confidence(best[2]),
            candidate_steps=[candidate.step_index] if candidate.step_index >= 0 else [],
            candidates=[candidate],
            evidence=best[3],
            llm_used=False,
        ))
    return matches


def _match_checkpoint_features(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    *,
    ab_report: Any = None,
    state_sequence: Any = None,
    config: IntentMatcherConfig,
    min_score: float = 0.18,
) -> list[CheckpointIntentMatch]:
    features = _build_alignment_features(payload, ab_report, state_sequence)
    matches: list[CheckpointIntentMatch] = []
    last_pos = -1

    for cp_idx, checkpoint in enumerate(checkpoints):
        cp_text = _checkpoint_text(checkpoint)
        scored: list[tuple[int, dict[str, Any], float, list[str]]] = []
        for pos, feature in enumerate(features):
            if pos < last_pos:
                continue
            score, evidence = _score(cp_text, checkpoint, feature)
            scored.append((pos, feature, score, evidence))

        ranked = sorted(scored, key=lambda item: item[2], reverse=True)
        top = ranked[: max(1, config.max_candidates)]
        best = _select_candidate(top, min_score=min_score)
        if best is None or best[2] < min_score:
            matches.append(CheckpointIntentMatch(
                checkpoint_index=cp_idx,
                matched=False,
                score=0.0 if best is None else best[2],
                confidence="unmatched_intent",
                candidates=[_to_intent_candidate(item) for item in top],
                evidence=["fallback state/AB intent recall found no reliable candidate"],
                llm_used=False,
            ))
            continue

        last_pos = best[0]
        candidates = [_to_intent_candidate(item) for item in top if item[2] >= min_score]
        if not candidates:
            candidates = [_to_intent_candidate(best)]
        matches.append(CheckpointIntentMatch(
            checkpoint_index=cp_idx,
            matched=True,
            score=best[2],
            confidence=_confidence(best[2]),
            candidate_steps=sorted({c.step_index for c in candidates if c.step_index >= 0}),
            candidate_states=[c.state_id for c in candidates if c.state_id],
            candidates=candidates,
            evidence=best[3],
            llm_used=False,
        ))
    return matches


def align_checkpoints_to_steps(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    *,
    ab_report: Any = None,
    state_sequence: Any = None,
    intent_matches: list[CheckpointIntentMatch] | None = None,
    intent_config: IntentMatcherConfig | None = None,
    min_score: float = 0.18,
) -> list[CheckpointAlignment]:
    """Align checkpoints to source step indexes after intent-level recall."""
    matches = intent_matches or match_checkpoint_intents(
        checkpoints,
        payload,
        ab_report=ab_report,
        state_sequence=state_sequence,
        config=intent_config,
        min_score=min_score,
    )
    alignments: list[CheckpointAlignment] = []

    for cp_idx, match in enumerate(matches):
        if not match.matched or not match.candidates:
            alignments.append(CheckpointAlignment(
                checkpoint_index=cp_idx,
                step_index=-1,
                score=match.score,
                start_step_index=-1,
                end_step_index=-1,
                confidence="unmatched_intent",
                evidence=match.evidence or ["intent recall failed; execution verification skipped"],
            ))
            continue
        best = max(match.candidates, key=lambda item: item.score)
        alignments.append(CheckpointAlignment(
            checkpoint_index=cp_idx,
            step_index=best.step_index,
            score=best.score,
            start_step_index=best.start_step_index if best.start_step_index >= 0 else best.step_index,
            end_step_index=best.end_step_index if best.end_step_index >= 0 else best.step_index,
            confidence=match.confidence,
            evidence=["intent recall matched candidate"] + best.evidence,
        ))
    return alignments


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
        start_step_index = alignment.start_step_index if alignment.start_step_index >= 0 else alignment.step_index
        end_step_index = alignment.end_step_index if alignment.end_step_index >= 0 else alignment.step_index
        if (
            alignment.step_index < 0
            or start_step_index not in by_source
            or end_step_index not in by_source
        ):
            step_data.append({
                "step_index": -1,
                "before_step_index": -1,
                "after_step_index": -1,
                "start_step_index": -1,
                "end_step_index": -1,
                "before_image_base64": "",
                "after_image_base64": "",
                "before_image_ref": "",
                "after_image_ref": "",
                "image_available": False,
                "alignment": alignment.to_dict(),
            })
            continue

        start_pos, start_step = by_source[start_step_index]
        end_pos, end_step = by_source[end_step_index]
        if end_pos < start_pos:
            start_pos, end_pos = end_pos, start_pos
            start_step, end_step = end_step, start_step
        after_step = seq_info[end_pos + 1] if end_pos + 1 < len(seq_info) else end_step
        before_img = start_step.get("image_relative_path", "")
        after_img = after_step.get("image_relative_path", "") or end_step.get("image_relative_path", "")
        step_data.append({
            "before_image_base64": before_img,
            "after_image_base64": after_img,
            "before_image_ref": start_step.get("_image_original_ref", before_img),
            "after_image_ref": after_step.get("_image_original_ref", after_img) or end_step.get("_image_original_ref", after_img),
            "before_step_index": int(start_step.get("index", start_step_index)),
            "after_step_index": int(after_step.get("index", end_step_index)) if after_step else end_step_index,
            "start_step_index": start_step_index,
            "end_step_index": end_step_index,
            "image_available": bool(before_img or after_img),
            "action_description": _span_action_description(seq_info[start_pos:end_pos + 1]),
            "step_index": alignment.step_index,
            "alignment": alignment.to_dict(),
        })
    return step_data


def _span_action_description(steps: list[dict[str, Any]]) -> str:
    actions: list[str] = []
    for step in steps:
        parsed = (step.get("planning_output") or {}).get("parsed_action") or {}
        desc = _action_description(parsed)
        if desc:
            actions.append(desc)
    return " -> ".join(actions)


def _to_intent_candidate(item: tuple[int, dict[str, Any], float, list[str]]) -> IntentCandidate:
    _, feature, score, evidence = item
    purpose_index = int(feature.get("purpose_index", -1))
    source_step = int(feature.get("source_step_index", -1))
    candidate_evidence = list(evidence)
    if purpose_index >= 0 and not any(item.startswith("purpose_index=") for item in candidate_evidence):
        candidate_evidence.append(f"purpose_index={purpose_index}")
    return IntentCandidate(
        source_kind=str(feature.get("source_kind", "step")),
        step_index=source_step,
        score=score,
        evidence=candidate_evidence,
        state_id=str(feature.get("state_id", "")),
        step_range=list(feature.get("state_range", [])),
        purpose_index=purpose_index,
        purpose_text=str(feature.get("purpose_text", "")),
        start_step_index=source_step,
        end_step_index=source_step,
        start_purpose_index=purpose_index,
        end_purpose_index=purpose_index,
    )


def _build_purpose_features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    seq_info = payload.get("seq_info") or []
    features: list[dict[str, Any]] = []
    for pos, step in enumerate(seq_info):
        parsed = (step.get("planning_output") or {}).get("parsed_action") or {}
        action_type = str(parsed.get("action_type", "")).strip().lower()
        if action_type in {"finished", "done"}:
            continue
        purpose = str(step.get("action_purpose") or step.get("purpose") or "").strip()
        if not purpose:
            continue
        source_step = int(step.get("index", pos))
        action_text = _action_description(parsed)
        features.append({
            "source_kind": "purpose",
            "source_step_index": source_step,
            "purpose_index": len(features),
            "purpose_text": purpose,
            "action_type": action_type,
            "action_text": " ".join(part for part in (purpose, action_text) if part),
            "page_before": "",
            "page_after": "",
            "ab_action": "",
        })
    if features:
        return features

    purposes = _payload_purposes(payload)
    if not purposes:
        return []
    non_terminal_steps = []
    for pos, step in enumerate(seq_info):
        parsed = (step.get("planning_output") or {}).get("parsed_action") or {}
        action_type = str(parsed.get("action_type", "")).strip().lower()
        if action_type in {"finished", "done"}:
            continue
        non_terminal_steps.append((pos, step, parsed))

    for purpose_idx, purpose in enumerate(purposes):
        step_pos, step, parsed = non_terminal_steps[purpose_idx] if purpose_idx < len(non_terminal_steps) else (-1, {}, {})
        source_step = int(step.get("index", step_pos if step_pos >= 0 else purpose_idx))
        action_type = str(parsed.get("action_type", "")).strip().lower()
        action_text = _action_description(parsed)
        features.append({
            "source_kind": "purpose",
            "source_step_index": source_step,
            "purpose_index": purpose_idx,
            "purpose_text": purpose,
            "action_type": action_type,
            "action_text": " ".join(part for part in (purpose, action_text) if part),
            "page_before": "",
            "page_after": "",
            "ab_action": "",
        })
    return features


def _payload_purposes(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("_action_purposes")
    if isinstance(raw, list):
        purposes = [str(item).strip() for item in raw if str(item).strip()]
        if purposes:
            return purposes
    text = str(payload.get("agent_purposes") or "").strip()
    if not text:
        return []
    parts = re.split(r"\s*(?:->|=>|,|，|;|；|\n)\s*", text)
    return [part.strip() for part in parts if part.strip()]


def _llm_match_plan_to_purposes(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    purpose_features: list[dict[str, Any]],
    config: IntentMatcherConfig,
) -> dict[int, dict[str, Any]]:
    diag = {
        "llm_configured": bool(config.llm_model_url and config.llm_model_name),
        "llm_attempted": False,
        "mock_mode": config.mock_mode,
        "model_url_set": bool(config.llm_model_url),
        "model_name": config.llm_model_name,
        "api_key_set": bool(config.llm_api_key),
        "purpose_feature_count": len(purpose_features),
        "checkpoint_count": len(checkpoints),
        "returned_match_count": 0,
        "status": "not_started",
        "error": "",
        "response_head": "",
    }
    config.diagnostics["purpose_llm"] = diag
    if config.mock_mode:
        diag["status"] = "skipped_mock_mode"
        return {}
    if not config.llm_model_url or not config.llm_model_name:
        diag["status"] = "skipped_missing_config"
        diag["error"] = "LLM model url/name not set"
        return {}
    prompt = _plan_purpose_match_prompt(checkpoints, payload, purpose_features)
    diag["llm_attempted"] = True
    try:
        content = _call_llm(config, prompt)
        diag["response_head"] = content[:300]
        parsed = _parse_json_object(content)
    except Exception as exc:
        diag["status"] = "exception"
        diag["error"] = str(exc)[:500]
        return {}
    items = parsed.get("matches", []) if isinstance(parsed, dict) else []
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(items, list):
        diag["status"] = "invalid_response"
        diag["error"] = "LLM JSON does not contain a list field: matches"
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            cp_idx = int(item.get("checkpoint_index", -1))
        except (TypeError, ValueError):
            continue
        if 0 <= cp_idx < len(checkpoints):
            result[cp_idx] = item
    diag["returned_match_count"] = len(result)
    diag["status"] = "ok" if result else "empty_matches"
    if not result:
        diag["error"] = "LLM returned no valid checkpoint matches"
    return result


def _plan_purpose_match_prompt(
    checkpoints: list[Checkpoint],
    payload: dict[str, Any],
    purpose_features: list[dict[str, Any]],
) -> str:
    checkpoint_items = []
    for idx, checkpoint in enumerate(checkpoints):
        item = checkpoint.to_dict()
        item["checkpoint_index"] = idx
        checkpoint_items.append(item)
    purpose_items = [
        {
            "agent_purpose_index": feature["purpose_index"],
            "step_index": feature["source_step_index"],
            "purpose": feature["purpose_text"],
            "action_type": feature.get("action_type", ""),
            "action_text": feature.get("action_text", ""),
        }
        for feature in purpose_features
    ]
    payload_summary = {
        "instruction": payload.get("instruction", ""),
        "step_level_instruction": payload.get("step_level_instruction", ""),
        "checkpoints": checkpoint_items,
        "agent_purposes": purpose_items,
    }
    return (
        "你是 GUI Agent 评测中的意图对齐器，需要判断任务检查点是否被 Agent 的实际操作意图覆盖。\n"
        "请只比较 checkpoint 与 agent_purpose 的语义意图，不要根据页面截图或执行结果猜测。\n"
        "如果某个 checkpoint 需要多个连续 purpose 才能完成，请返回覆盖这些 purpose 的 start_purpose_index 和 end_purpose_index；"
        "agent_purpose_index 保持兼容，可填写 end_purpose_index。\n"
        "如果某个 checkpoint 没有对应 purpose，status 设为 missing；如果 purpose 隐含满足 checkpoint，status 设为 implicit；"
        "如果只能由更早顺序的 purpose 满足但会破坏检查点顺序，status 设为 order_violation。\n"
        "只输出 JSON，格式为：{\"matches\":[{\"checkpoint_index\":0,\"start_purpose_index\":0,\"end_purpose_index\":1,\"agent_purpose_index\":1,\"status\":\"matched|implicit|missing|order_violation\",\"confidence\":0.0,\"reason\":\"...\"}]}。\n"
        f"输入：{json.dumps(payload_summary, ensure_ascii=False)}"
    )


def _match_from_llm_item(
    cp_idx: int,
    item: dict[str, Any],
    purpose_features: list[dict[str, Any]],
    *,
    min_score: float,
    min_purpose_index: int = -1,
) -> CheckpointIntentMatch | None:
    status = str(item.get("status", "")).strip().lower()
    purpose_idx = _safe_int(item.get("agent_purpose_index", -1), -1)
    start_purpose_idx = _safe_int(item.get("start_purpose_index", purpose_idx), purpose_idx)
    end_purpose_idx = _safe_int(item.get("end_purpose_index", purpose_idx), purpose_idx)
    score = max(0.0, min(_safe_float(item.get("confidence", 0.0), 0.0), 1.0))
    reason = str(item.get("reason", "")).strip()
    matched_status = status in {"matched", "implicit"} and start_purpose_idx >= 0 and end_purpose_idx >= 0

    if matched_status and start_purpose_idx < min_purpose_index:
        return CheckpointIntentMatch(
            checkpoint_index=cp_idx,
            matched=False,
            score=score,
            confidence="unmatched_intent",
            evidence=[
                "purpose_llm_status=order_violation",
                f"purpose_span={start_purpose_idx}-{end_purpose_idx}",
                f"min_purpose_index={min_purpose_index}",
            ],
            llm_used=True,
            llm_reason=reason or "LLM purpose span moves backward",
        )
    if matched_status and end_purpose_idx < start_purpose_idx:
        return CheckpointIntentMatch(
            checkpoint_index=cp_idx,
            matched=False,
            score=score,
            confidence="unmatched_intent",
            evidence=[
                "purpose_llm_status=order_violation",
                f"purpose_span={start_purpose_idx}-{end_purpose_idx}",
            ],
            llm_used=True,
            llm_reason=reason or "LLM purpose span end is before start",
        )
    if not matched_status:
        return CheckpointIntentMatch(
            checkpoint_index=cp_idx,
            matched=False,
            score=score,
            confidence="unmatched_intent",
            evidence=[f"purpose_llm_status={status or 'missing'}"],
            llm_used=True,
            llm_reason=reason,
        )

    start_feature = next((f for f in purpose_features if int(f.get("purpose_index", -1)) == start_purpose_idx), None)
    end_feature = next((f for f in purpose_features if int(f.get("purpose_index", -1)) == end_purpose_idx), None)
    if start_feature is None or end_feature is None:
        return None
    if score < min_score:
        return CheckpointIntentMatch(
            checkpoint_index=cp_idx,
            matched=False,
            score=score,
            confidence="unmatched_intent",
            evidence=[f"purpose_llm_status={status}", "llm confidence below threshold"],
            llm_used=True,
            llm_reason=reason,
        )

    start_step = int(start_feature.get("source_step_index", -1))
    end_step = int(end_feature.get("source_step_index", -1))
    candidate = IntentCandidate(
        source_kind="purpose",
        step_index=end_step,
        score=score,
        evidence=[
            f"purpose_llm_status={status}",
            f"purpose_span={start_purpose_idx}-{end_purpose_idx}",
            f"purpose_index={end_purpose_idx}",
        ],
        purpose_index=end_purpose_idx,
        purpose_text=str(end_feature.get("purpose_text", "")),
        start_step_index=start_step,
        end_step_index=end_step,
        start_purpose_index=start_purpose_idx,
        end_purpose_index=end_purpose_idx,
    )
    return CheckpointIntentMatch(
        checkpoint_index=cp_idx,
        matched=True,
        score=score,
        confidence=_confidence(score),
        candidate_steps=[step for step in (start_step, end_step) if step >= 0],
        candidates=[candidate],
        evidence=candidate.evidence,
        llm_used=True,
        llm_reason=reason,
    )


def _build_alignment_features(
    payload: dict[str, Any],
    ab_report: Any,
    state_sequence: Any = None,
) -> list[dict[str, Any]]:
    features = _build_step_features(payload, ab_report)
    features.extend(_build_state_features(state_sequence))
    return sorted(
        features,
        key=lambda item: (
            int(item.get("source_step_index", -1)),
            0 if item.get("source_kind") == "step" else 1,
        ),
    )


def _build_step_features(payload: dict[str, Any], ab_report: Any) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    purpose_by_pos = _purpose_by_position(payload)
    for pos, step in enumerate(payload.get("seq_info") or []):
        parsed = (step.get("planning_output") or {}).get("parsed_action") or {}
        action_type = str(parsed.get("action_type", "")).strip().lower()
        if action_type in {"finished", "done"}:
            continue
        source_step = int(step.get("index", pos))
        ab = _ab_result(ab_report, source_step)
        action_text = _action_description(parsed)
        purpose = (
            str(step.get("action_purpose") or step.get("purpose") or "").strip()
            or purpose_by_pos.get(pos, "")
            or purpose_by_pos.get(source_step, "")
        )
        features.append({
            "source_kind": "step",
            "source_step_index": source_step,
            "action_type": action_type,
            "action_text": " ".join(part for part in (action_text, purpose) if part),
            "page_before": str(ab.get("pagea_description") or ""),
            "page_after": str(ab.get("pageb_description") or ""),
            "ab_action": str(ab.get("action_des") or ""),
        })
    return features


def _build_state_features(state_sequence: Any) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    states = _state_items(state_sequence)
    for state in states:
        source_steps = _as_int_list(_value(state, "source_step_indices", []))
        if not source_steps:
            step_range = _value(state, "step_range", [])
            source_steps = _as_int_list(step_range)
        if not source_steps:
            continue
        action_purposes = _as_str_list(_value(state, "action_purposes", []))
        action_types = _as_str_list(_value(state, "action_types", []))
        page_description = str(_value(state, "page_description", "") or "")
        label = str(_value(state, "label", "") or "")
        visual_summary = _value(state, "visual_change_summary", {}) or {}
        features.append({
            "source_kind": "state",
            "source_step_index": max(source_steps),
            "source_step_indices": source_steps,
            "state_id": str(_value(state, "state_id", "")),
            "state_range": [min(source_steps), max(source_steps)],
            "action_type": " ".join(action_types),
            "action_text": " ".join(action_purposes + action_types),
            "page_before": label,
            "page_after": page_description or label,
            "ab_action": "",
            "evidence_quality": str(_value(state, "evidence_quality", "") or ""),
            "visual_change_summary": visual_summary,
        })
    return features


def _state_items(state_sequence: Any) -> list[Any]:
    if state_sequence is None:
        return []
    if isinstance(state_sequence, dict):
        states = state_sequence.get("states") or []
        return states if isinstance(states, list) else []
    states = getattr(state_sequence, "states", [])
    return states if isinstance(states, list) else []


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _as_int_list(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _score(cp_text: str, checkpoint: Checkpoint, step: dict[str, Any]) -> tuple[float, list[str]]:
    evidence: list[str] = []
    action_text = f"{step['action_text']} {step['ab_action']}".strip()
    page_text = f"{step['page_before']} {step['page_after']}".strip()
    all_step_text = f"{action_text} {page_text}"

    action_score = _similarity(cp_text, action_text)
    page_score = _similarity(_checkpoint_state_text(checkpoint), page_text)
    keyword_score = _keyword_overlap(cp_text, all_step_text)
    semantic_score, semantic_evidence = _semantic_score(cp_text, checkpoint, step, all_step_text)
    state_score, state_evidence = _state_candidate_score(step, page_score, keyword_score, semantic_score)
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
    if state_evidence:
        evidence.extend(state_evidence)

    score = (
        0.30 * action_score
        + 0.25 * page_score
        + 0.20 * keyword_score
        + 0.20 * semantic_score
        + state_score
        + type_bonus
    )
    return min(score, 1.0), evidence or ["weak intent candidate"]


def _state_candidate_score(
    step: dict[str, Any],
    page_score: float,
    keyword_score: float,
    semantic_score: float,
) -> tuple[float, list[str]]:
    if step.get("source_kind") != "state":
        return 0.0, []
    evidence = [
        f"state_candidate={step.get('state_id') or 'unknown'}",
        f"state_range={step.get('state_range', [])}",
    ]
    quality = step.get("evidence_quality", "")
    if quality:
        evidence.append(f"state_evidence_quality={quality}")
    summary = step.get("visual_change_summary") or {}
    if isinstance(summary, dict) and summary.get("usable_count", 0):
        evidence.append(
            "state_visual_boundary="
            f"{float(summary.get('max_boundary_confidence') or 0.0):.2f}"
        )

    textual_support = max(page_score, keyword_score, semantic_score)
    if textual_support < 0.12:
        return 0.0, evidence[:2]
    quality_bonus = 0.03 if quality in {"strong", "visual", "partial"} else 0.0
    return min(0.10, 0.05 + quality_bonus), evidence[:4]


def _llm_rerank_intent(
    checkpoint: Checkpoint,
    candidates: list[tuple[int, dict[str, Any], float, list[str]]],
    config: IntentMatcherConfig,
) -> dict[str, Any] | None:
    if config.mock_mode or not config.llm_model_url or not config.llm_model_name or not candidates:
        return None
    prompt = _intent_rerank_prompt(checkpoint, candidates)
    try:
        content = _call_llm(config, prompt)
        parsed = _parse_json_object(content)
    except Exception:
        return None
    if not isinstance(parsed, dict) or parsed.get("matched") is False:
        return None
    selected = parsed.get("selected_candidate")
    try:
        selected_pos = int(selected)
    except (TypeError, ValueError):
        return None
    return {
        "selected_pos": selected_pos,
        "score": float(parsed.get("confidence", 0.0)),
        "reason": str(parsed.get("reason", "")),
    }


def _intent_rerank_prompt(
    checkpoint: Checkpoint,
    candidates: list[tuple[int, dict[str, Any], float, list[str]]],
) -> str:
    candidate_items = []
    for pos, feature, score, _ in candidates:
        candidate_items.append({
            "candidate_id": pos,
            "source_kind": feature.get("source_kind", "step"),
            "step_index": feature.get("source_step_index", -1),
            "state_id": feature.get("state_id", ""),
            "action_intent": feature.get("action_text", ""),
            "page_state": " ".join([
                str(feature.get("page_before", "")),
                str(feature.get("page_after", "")),
            ]).strip(),
            "local_score": round(score, 3),
        })
    return (
        "You are an intent recall reranker for GUI Agent evaluation. "
        "Choose the actual candidate that most likely corresponds to the checkpoint. "
        "Output only a JSON object.\n"
        f"checkpoint: {json.dumps(checkpoint.to_dict(), ensure_ascii=False)}\n"
        f"candidates: {json.dumps(candidate_items, ensure_ascii=False)}\n"
        "schema: {\"matched\": true/false, \"selected_candidate\": <candidate_id or -1>, "
        "\"confidence\": 0 to 1, \"reason\": \"short reason\"}"
    )


def _call_llm(config: IntentMatcherConfig, prompt: str) -> str:
    import requests

    payload = {
        "model": config.llm_model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    if config.llm_api_key:
        headers["Authorization"] = f"Bearer {config.llm_api_key}"
    resp = requests.post(
        config.llm_model_url,
        json=payload,
        headers=headers,
        timeout=config.request_timeout,
    )
    if resp.status_code != 200:
        raise ValueError(f"LLM API returned {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("LLM returned no choices")
    return choices[0].get("message", {}).get("content", "")


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return {}
        parsed = json.loads(match.group())
        return parsed if isinstance(parsed, dict) else {}


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
    for item in sorted(candidates, key=lambda candidate: candidate[0]):
        if item[2] >= threshold:
            return item
    return max(candidates, key=lambda item: item[2])


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


def _purpose_by_position(payload: dict[str, Any]) -> dict[int, str]:
    raw = payload.get("_action_purposes") or []
    if not isinstance(raw, list):
        return {}
    return {idx: str(value).strip() for idx, value in enumerate(raw) if str(value).strip()}


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
