"""Run the independent repeated-operation baseline on preprocessed payloads."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common import (
    ABValidator,
    ABValidatorConfig,
    detect_repeated_actions,
    hydrate_payload_images,
)
from src.verifier import (
    Checkpoint,
    CheckpointVerifier,
    VerifierConfig,
    align_checkpoints_to_steps,
)


@dataclass
class RepeatedBaselineConfig:
    vlm_model_url: str = ""
    vlm_model_name: str = "qwen3-vl-8b"
    vlm_api_key: str = ""
    mock_mode: bool = False
    verify_checkpoints: bool = True


def run_repeated_baseline(
    payload_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    config: RepeatedBaselineConfig | None = None,
) -> dict[str, Any]:
    """Run ImageResolver -> ABValidator -> aligner/verifier -> repeat detector."""
    config = config or RepeatedBaselineConfig()
    payload_path = Path(payload_path)
    payload = _load_json(payload_path)
    task_uuid = payload.get("task_uuid") or payload_path.parent.name
    payload["task_uuid"] = task_uuid

    hydrated, image_stats = hydrate_payload_images(payload, payload_path=payload_path)

    ab_validator = ABValidator(ABValidatorConfig(
        vlm_model_url=config.vlm_model_url,
        vlm_model_name=config.vlm_model_name,
        vlm_api_key=config.vlm_api_key,
        mock_mode=config.mock_mode,
    ))
    ab_report = ab_validator.validate_payload(
        hydrated,
        task_uuid=task_uuid,
        resolve_images=False,
    )

    checkpoints = _load_checkpoints(hydrated)
    alignments = align_checkpoints_to_steps(checkpoints, hydrated, ab_report=ab_report)

    verification_report = None
    if config.verify_checkpoints and checkpoints:
        verifier = CheckpointVerifier(VerifierConfig(
            vlm_model_url=config.vlm_model_url or "http://localhost:8000/v1/chat/completions",
            vlm_model_name=config.vlm_model_name,
            vlm_api_key=config.vlm_api_key,
            mock_mode=config.mock_mode,
        ))
        verification_report = verifier.verify_from_payload(
            checkpoints,
            hydrated,
            ab_report=ab_report,
        )

    repeated = detect_repeated_actions(hydrated, ab_report, verification_report)
    repeated_prediction = repeated.to_dict()
    repeated_prediction["task_uuid"] = task_uuid

    result = {
        "schema_version": "repeated_baseline.v1",
        "task_uuid": task_uuid,
        "input_payload": str(payload_path),
        "image_resolution": image_stats.to_dict(),
        "ab_report": ab_report.to_dict(),
        "checkpoint_alignments": [a.to_dict() for a in alignments],
        "verification_report": (
            verification_report.to_dict() if verification_report else None
        ),
        "repeated_prediction": repeated_prediction,
    }

    output_base = Path(output_dir) if output_dir else payload_path.parent / "repeated_baseline"
    output_base.mkdir(parents=True, exist_ok=True)
    _write_json(output_base / "ab_report.json", result["ab_report"])
    _write_json(output_base / "checkpoint_alignments.json", result["checkpoint_alignments"])
    if result["verification_report"] is not None:
        _write_json(output_base / "verification_report.json", result["verification_report"])
    _write_json(output_base / "repeated_prediction.json", result["repeated_prediction"])
    _write_json(output_base / "baseline_result.json", result)
    return result


def _load_checkpoints(payload: dict[str, Any]) -> list[Checkpoint]:
    raw = payload.get("_checkpoints") or []
    checkpoints: list[Checkpoint] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        checkpoint = Checkpoint.from_dict(item)
        if not checkpoint.checkpoint_id:
            checkpoint.checkpoint_id = f"cp_{i:03d}"
        checkpoints.append(checkpoint)
    return checkpoints


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_dotenv() -> None:
    """Load .env before reading os.environ.

    Uses python-dotenv when available; otherwise supports simple KEY=value lines.
    Existing environment variables are preserved.
    """
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    env_path = next((path for path in candidates if path.is_file()), None)
    if env_path is None:
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _config_from_env(args: argparse.Namespace) -> RepeatedBaselineConfig:
    _load_dotenv()
    return RepeatedBaselineConfig(
        vlm_model_url=args.vlm_model_url or os.getenv("VLM_MODEL_URL", ""),
        vlm_model_name=args.vlm_model_name or os.getenv("VLM_MODEL_NAME", "qwen3-vl-8b"),
        vlm_api_key=args.vlm_api_key or os.getenv("VLM_API_KEY", ""),
        mock_mode=args.mock,
        verify_checkpoints=not args.skip_checkpoint_verify,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent repeated baseline")
    parser.add_argument("payload_path")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--vlm-model-url", default="")
    parser.add_argument("--vlm-model-name", default="")
    parser.add_argument("--vlm-api-key", default="")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--skip-checkpoint-verify", action="store_true")
    args = parser.parse_args()

    result = run_repeated_baseline(
        args.payload_path,
        args.output_dir or None,
        config=_config_from_env(args),
    )
    print(json.dumps({
        "task_uuid": result["task_uuid"],
        "label": result["repeated_prediction"]["label"],
        "output_dir": str(Path(args.output_dir) if args.output_dir else Path(args.payload_path).parent / "repeated_baseline"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
