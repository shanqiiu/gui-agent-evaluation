"""Screenshot and rawPage evidence for evaluator state boundaries."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any


try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised only on minimal runtimes
    Image = None  # type: ignore[assignment]


@dataclass
class RegionChange:
    region: str
    diff_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "diff_ratio": round(self.diff_ratio, 4),
        }


@dataclass
class StepVisualEvidence:
    source_step_index: int
    next_step_index: int
    has_before_image: bool = False
    has_after_image: bool = False
    phash_before: str = ""
    phash_after: str = ""
    phash_distance: int | None = None
    ssim: float | None = None
    pixel_diff_ratio: float | None = None
    changed_regions: list[RegionChange] = field(default_factory=list)
    ocr_fingerprint_before: str = ""
    ocr_fingerprint_after: str = ""
    ocr_text_similarity: float | None = None
    rawpage_changed: bool | None = None
    boundary_confidence: float = 0.0
    evidence_quality: str = "missing"
    evidence: list[str] = field(default_factory=list)

    @property
    def visual_changed(self) -> bool:
        if self.pixel_diff_ratio is not None and self.pixel_diff_ratio >= 0.08:
            return True
        if self.ssim is not None and self.ssim <= 0.88:
            return True
        if self.phash_distance is not None and self.phash_distance >= 10:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_step_index": self.source_step_index,
            "next_step_index": self.next_step_index,
            "has_before_image": self.has_before_image,
            "has_after_image": self.has_after_image,
            "phash_before": self.phash_before,
            "phash_after": self.phash_after,
            "phash_distance": self.phash_distance,
            "ssim": _round_or_none(self.ssim),
            "pixel_diff_ratio": _round_or_none(self.pixel_diff_ratio),
            "changed_regions": [r.to_dict() for r in self.changed_regions],
            "ocr_fingerprint_before": self.ocr_fingerprint_before,
            "ocr_fingerprint_after": self.ocr_fingerprint_after,
            "ocr_text_similarity": _round_or_none(self.ocr_text_similarity),
            "rawpage_changed": self.rawpage_changed,
            "boundary_confidence": round(self.boundary_confidence, 3),
            "evidence_quality": self.evidence_quality,
            "evidence": self.evidence,
        }


def build_visual_evidence(payload: dict[str, Any]) -> dict[int, StepVisualEvidence]:
    """Build visual/rawPage evidence for each adjacent step transition."""
    seq_info = payload.get("seq_info") or []
    evidence_by_step: dict[int, StepVisualEvidence] = {}
    for pos in range(len(seq_info) - 1):
        current = seq_info[pos]
        next_step = seq_info[pos + 1]
        source_index = int(current.get("index", pos))
        next_index = int(next_step.get("index", pos + 1))
        evidence_by_step[source_index] = compare_steps(
            current,
            next_step,
            payload=payload,
            source_step_index=source_index,
            next_step_index=next_index,
        )
    return evidence_by_step


def compare_steps(
    before_step: dict[str, Any],
    after_step: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    source_step_index: int = -1,
    next_step_index: int = -1,
) -> StepVisualEvidence:
    result = StepVisualEvidence(
        source_step_index=source_step_index,
        next_step_index=next_step_index,
    )

    before_img = _decode_image(before_step.get("image_relative_path", ""))
    after_img = _decode_image(after_step.get("image_relative_path", ""))
    result.has_before_image = before_img is not None
    result.has_after_image = after_img is not None

    if before_img is not None and after_img is not None:
        _fill_image_metrics(result, before_img, after_img)
    elif before_step.get("image_relative_path") or after_step.get("image_relative_path"):
        result.evidence.append("screenshot decode failed")
    else:
        result.evidence.append("screenshot missing")

    before_ocr = _ocr_snapshot(before_step, payload)
    after_ocr = _ocr_snapshot(after_step, payload)
    _fill_ocr_metrics(result, before_ocr, after_ocr)
    _score_boundary(result)
    return result


def _fill_image_metrics(
    result: StepVisualEvidence,
    before_img: Any,
    after_img: Any,
) -> None:
    before_small = _resize_gray(before_img, (32, 32))
    after_small = _resize_gray(after_img, (32, 32))
    before_gray = _resize_gray(before_img)
    after_gray = _resize_gray(after_img)
    result.phash_before = _perceptual_hash(before_small)
    result.phash_after = _perceptual_hash(after_small)
    result.phash_distance = _hamming(result.phash_before, result.phash_after)
    result.ssim = _global_ssim(before_gray, after_gray)
    result.pixel_diff_ratio = _pixel_diff_ratio(before_gray, after_gray)
    result.changed_regions = _region_changes(before_gray, after_gray)

    result.evidence.append(f"pHash distance={result.phash_distance}")
    result.evidence.append(f"ssim={result.ssim:.3f}")
    result.evidence.append(f"pixel_diff_ratio={result.pixel_diff_ratio:.3f}")
    if result.changed_regions:
        regions = ", ".join(r.region for r in result.changed_regions[:3])
        result.evidence.append(f"changed_regions={regions}")


def _fill_ocr_metrics(
    result: StepVisualEvidence,
    before_ocr: Any,
    after_ocr: Any,
) -> None:
    before_texts = _extract_ocr_tokens(before_ocr)
    after_texts = _extract_ocr_tokens(after_ocr)
    result.ocr_fingerprint_before = _ocr_fingerprint(before_texts)
    result.ocr_fingerprint_after = _ocr_fingerprint(after_texts)

    if not before_texts and not after_texts:
        result.rawpage_changed = None
        result.evidence.append("rawPage/OCR missing")
        return

    result.rawpage_changed = result.ocr_fingerprint_before != result.ocr_fingerprint_after
    result.ocr_text_similarity = _token_similarity(
        [item[0] for item in before_texts],
        [item[0] for item in after_texts],
    )
    result.evidence.append(
        f"ocr_text_similarity={result.ocr_text_similarity:.3f}"
    )
    result.evidence.append(f"rawpage_changed={result.rawpage_changed}")


def _score_boundary(result: StepVisualEvidence) -> None:
    score = 0.0
    if result.phash_distance is not None:
        score += min(result.phash_distance / 32.0, 1.0) * 0.25
    if result.ssim is not None:
        score += max(0.0, 1.0 - result.ssim) * 0.35
    if result.pixel_diff_ratio is not None:
        score += min(result.pixel_diff_ratio / 0.30, 1.0) * 0.25
    if result.rawpage_changed is True:
        if result.ocr_text_similarity is None:
            score += 0.10
        else:
            score += max(0.0, 1.0 - result.ocr_text_similarity) * 0.15

    result.boundary_confidence = max(0.0, min(score, 1.0))
    if result.has_before_image and result.has_after_image and result.rawpage_changed is not None:
        result.evidence_quality = "strong"
    elif result.has_before_image and result.has_after_image:
        result.evidence_quality = "visual"
    elif result.rawpage_changed is not None:
        result.evidence_quality = "structural"
    else:
        result.evidence_quality = "missing"


def _decode_image(value: Any) -> Any | None:
    if Image is None or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("data:image/") and ";base64," in text:
        text = text.split(";base64,", 1)[1]
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        return img.convert("RGB")
    except Exception:
        return None


def _resize_gray(img: Any, size: tuple[int, int] = (64, 64)) -> list[int]:
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    gray = img.convert("L").resize(size, resampling)
    return list(gray.getdata())


def _perceptual_hash(pixels: list[int], size: int = 32, hash_size: int = 8) -> str:
    if len(pixels) != size * size:
        pixels = _resize_flat_pixels(pixels, size, size)
    coeffs: list[float] = []
    for u in range(hash_size):
        for v in range(hash_size):
            total = 0.0
            for y in range(size):
                for x in range(size):
                    total += (
                        pixels[y * size + x]
                        * math.cos(((2 * x + 1) * u * math.pi) / (2 * size))
                        * math.cos(((2 * y + 1) * v * math.pi) / (2 * size))
                    )
            cu = 1 / math.sqrt(2) if u == 0 else 1.0
            cv = 1 / math.sqrt(2) if v == 0 else 1.0
            coeffs.append(0.25 * cu * cv * total)
    low_freq = coeffs[1:]
    median = sorted(low_freq)[len(low_freq) // 2]
    bits = ["1" if value >= median else "0" for value in low_freq]
    bits.append("0")
    return f"{int(''.join(bits), 2):016x}"


def _resize_flat_pixels(pixels: list[int], width: int, height: int) -> list[int]:
    if not pixels:
        return [0] * width * height
    step = max(1, len(pixels) // (width * height))
    sampled = pixels[::step][: width * height]
    return sampled + [sampled[-1]] * (width * height - len(sampled))


def _hamming(left_hex: str, right_hex: str) -> int:
    if not left_hex or not right_hex:
        return 64
    left = int(left_hex, 16)
    right = int(right_hex, 16)
    return (left ^ right).bit_count()


def _global_ssim(left: list[int], right: list[int]) -> float:
    if not left or not right:
        return 0.0
    n = min(len(left), len(right))
    left = left[:n]
    right = right[:n]
    mean_left = sum(left) / n
    mean_right = sum(right) / n
    var_left = sum((x - mean_left) ** 2 for x in left) / max(n - 1, 1)
    var_right = sum((y - mean_right) ** 2 for y in right) / max(n - 1, 1)
    cov = sum((left[i] - mean_left) * (right[i] - mean_right) for i in range(n))
    cov /= max(n - 1, 1)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    numerator = (2 * mean_left * mean_right + c1) * (2 * cov + c2)
    denominator = (mean_left**2 + mean_right**2 + c1) * (var_left + var_right + c2)
    if denominator == 0:
        return 1.0 if left == right else 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def _pixel_diff_ratio(left: list[int], right: list[int], threshold: int = 24) -> float:
    n = min(len(left), len(right))
    if n == 0:
        return 0.0
    changed = sum(1 for i in range(n) if abs(left[i] - right[i]) >= threshold)
    return changed / n


def _region_changes(left: list[int], right: list[int], width: int = 64) -> list[RegionChange]:
    n = min(len(left), len(right))
    if n == 0:
        return []
    height = n // width
    regions = [
        ("top", 0, height // 3),
        ("middle", height // 3, (height * 2) // 3),
        ("bottom", (height * 2) // 3, height),
    ]
    changed: list[RegionChange] = []
    for name, y0, y1 in regions:
        indexes = [y * width + x for y in range(y0, y1) for x in range(width)]
        if not indexes:
            continue
        ratio = sum(1 for i in indexes if abs(left[i] - right[i]) >= 24) / len(indexes)
        if ratio >= 0.08:
            changed.append(RegionChange(name, ratio))
    return changed


def _ocr_snapshot(step: dict[str, Any], payload: dict[str, Any] | None) -> Any:
    for key in ("rawPage", "raw_page", "ocr_page", "_ocr_page"):
        if step.get(key):
            return step[key]

    if not payload:
        return None
    pages = payload.get("_ocr_pages") or payload.get("ocr_pages") or []
    page_index = step.get("_ocr_page_index", step.get("ocr_page_index", -1))
    if isinstance(page_index, int) and 0 <= page_index < len(pages):
        return pages[page_index]
    return None


def _extract_ocr_tokens(raw: Any) -> list[tuple[str, str, str]]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [(t, "", "") for t in _split_text(raw)]
    tokens: list[tuple[str, str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        text = _node_text(node)
        if text:
            tokens.append((text, str(node.get("type") or node.get("class") or ""), _bounds_bucket(node)))
        for key in ("children", "sub_nodes", "subNodes", "nodes"):
            walk(node.get(key))

    walk(raw)
    return sorted(set(tokens))


def _node_text(node: dict[str, Any]) -> str:
    for key in ("text", "content", "label", "name", "desc", "description"):
        value = str(node.get(key) or "").strip()
        if value:
            return re.sub(r"\s+", " ", value)[:80]
    return ""


def _bounds_bucket(node: dict[str, Any]) -> str:
    bounds = node.get("bounds") or node.get("rect") or node.get("bbox") or []
    if isinstance(bounds, dict):
        values = [bounds.get(k, 0) for k in ("left", "top", "right", "bottom")]
    else:
        values = bounds if isinstance(bounds, list) else []
    if len(values) < 4:
        return ""
    try:
        x = (float(values[0]) + float(values[2])) / 2.0
        y = (float(values[1]) + float(values[3])) / 2.0
    except (TypeError, ValueError):
        return ""
    return f"{math.floor(x / 100)}:{math.floor(y / 100)}"


def _split_text(value: str) -> list[str]:
    return [t for t in re.split(r"\s+", value.strip()) if t]


def _ocr_fingerprint(tokens: list[tuple[str, str, str]]) -> str:
    if not tokens:
        return ""
    data = "|".join(f"{text}:{kind}:{bucket}" for text, kind, bucket in tokens)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def _token_similarity(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
