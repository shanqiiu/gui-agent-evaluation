"""Image reference resolution for evaluation payloads.

Preprocessor payloads may carry screenshot paths, raw base64 strings, or
data-image URLs. Downstream VLM modules should receive only base64 payloads.
"""

from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_DATA_IMAGE_PREFIX = "data:image/"


@dataclass
class ImageResolutionStats:
    total: int = 0
    resolved: int = 0
    already_base64: int = 0
    data_url: int = 0
    missing: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "resolved": self.resolved,
            "already_base64": self.already_base64,
            "data_url": self.data_url,
            "missing": self.missing,
            "failed": self.failed,
        }


def hydrate_payload_images(
    payload: dict[str, Any],
    *,
    payload_path: str | Path | None = None,
    image_base_dir: str | Path | None = None,
    image_field: str = "image_relative_path",
) -> tuple[dict[str, Any], ImageResolutionStats]:
    """Return a copied payload whose image references are base64 strings."""
    hydrated = deepcopy(payload)
    stats = ImageResolutionStats()

    base_dir = _resolve_base_dir(hydrated, payload_path, image_base_dir)
    for step in hydrated.get("seq_info") or []:
        raw_ref = step.get(image_field, "")
        stats.total += 1
        resolved, kind = resolve_image_reference(raw_ref, base_dir=base_dir)
        if kind == "empty":
            stats.missing += 1
            continue
        if kind == "path":
            stats.resolved += 1
        elif kind == "base64":
            stats.already_base64 += 1
        elif kind == "data_url":
            stats.data_url += 1
        else:
            stats.failed += 1
            continue

        step["_image_original_ref"] = raw_ref
        step[image_field] = resolved

    hydrated["_image_mode"] = "base64"
    hydrated["_image_resolution"] = stats.to_dict()
    if base_dir:
        hydrated["_image_base_dir_resolved"] = str(base_dir)
    return hydrated, stats


def resolve_image_reference(ref: Any, *, base_dir: Path | None = None) -> tuple[str, str]:
    """Resolve one image reference.

    Returns:
        (base64_string, kind), where kind is one of:
        empty | path | base64 | data_url | failed
    """
    if ref is None:
        return "", "empty"
    value = str(ref).strip()
    if not value:
        return "", "empty"

    if value.startswith(_DATA_IMAGE_PREFIX):
        marker = ";base64,"
        if marker not in value:
            return "", "failed"
        data = value.split(marker, 1)[1].strip()
        return (data, "data_url") if _looks_like_base64(data) else ("", "failed")

    path = _candidate_path(value, base_dir)
    if path is not None:
        try:
            return base64.b64encode(path.read_bytes()).decode("ascii"), "path"
        except OSError:
            return "", "failed"

    if _looks_like_base64(value):
        return value, "base64"
    return "", "failed"


def _resolve_base_dir(
    payload: dict[str, Any],
    payload_path: str | Path | None,
    image_base_dir: str | Path | None,
) -> Path | None:
    if image_base_dir:
        return Path(image_base_dir).expanduser().resolve()

    payload_base = str(payload.get("_image_base_dir") or "").strip()
    if payload_base:
        base = Path(payload_base).expanduser()
        if base.is_absolute():
            return base.resolve()
        if payload_path:
            return (Path(payload_path).parent / base).resolve()
        return base.resolve()

    if payload_path:
        return Path(payload_path).parent.resolve()
    return None


def _candidate_path(value: str, base_dir: Path | None) -> Path | None:
    path = Path(value)
    candidates = [path] if path.is_absolute() else []
    if base_dir and not path.is_absolute():
        candidates.append(base_dir / path)
    if not candidates and path.suffix.lower() in _IMAGE_EXTS:
        candidates.append(path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _looks_like_base64(value: str) -> bool:
    if len(value) < 16:
        return False
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return True
