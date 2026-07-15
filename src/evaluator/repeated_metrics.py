"""Metrics for repeated-operation predictions against JSONL annotations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_repeated_predictions(
    annotation_jsonl: str | Path,
    prediction_dir: str | Path,
) -> dict[str, Any]:
    annotations = {a["task_uuid"]: a for a in _read_jsonl(Path(annotation_jsonl))}
    prediction_dir = Path(prediction_dir)
    predictions: dict[str, dict[str, Any]] = {}
    for path in prediction_dir.rglob("repeated_prediction.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        task_uuid = data.get("task_uuid") or path.parent.parent.name
        predictions[task_uuid] = data

    tp = fp = fn = tn = 0
    ious: list[float] = []
    reasonable_fp = 0
    reasonable_total = 0

    for task_uuid, ann in annotations.items():
        pred = predictions.get(task_uuid, {})
        pred_label = pred.get("label", "normal")
        gold_label = ann.get("label", "normal")
        gold_abnormal = gold_label == "abnormal"
        pred_abnormal = pred_label == "abnormal"

        if gold_abnormal and pred_abnormal:
            tp += 1
            ious.append(_best_iou(ann.get("ranges", []), pred.get("ranges", [])))
        elif gold_abnormal:
            fn += 1
        elif pred_abnormal:
            fp += 1
        else:
            tn += 1

        if ann.get("scenario_type") in {"reasonable_scroll", "reasonable_retry"}:
            reasonable_total += 1
            if pred_abnormal:
                reasonable_fp += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "cases": len(annotations),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mean_interval_iou": round(sum(ious) / len(ious), 4) if ious else 0.0,
        "reasonable_repeat_false_positive_rate": (
            round(reasonable_fp / reasonable_total, 4) if reasonable_total else 0.0
        ),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _best_iou(gold_ranges: list[dict[str, Any]], pred_ranges: list[dict[str, Any]]) -> float:
    best = 0.0
    for gold in gold_ranges:
        for pred in pred_ranges:
            best = max(best, _range_iou(gold, pred))
    return best


def _range_iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    l0, l1 = int(left.get("start_step", -1)), int(left.get("end_step", -1))
    r0, r1 = int(right.get("start_step", -1)), int(right.get("end_step", -1))
    if l0 < 0 or r0 < 0:
        return 0.0
    inter = max(0, min(l1, r1) - max(l0, r0) + 1)
    union = max(l1, r1) - min(l0, r0) + 1
    return inter / union if union else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate repeated predictions")
    parser.add_argument("annotation_jsonl")
    parser.add_argument("prediction_dir")
    args = parser.parse_args()
    print(json.dumps(
        evaluate_repeated_predictions(args.annotation_jsonl, args.prediction_dir),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
