"""
clearRes.gzip / clearRes.json parser.

Extracts:
- rawPage OCR trees (per Response)
- actionPurpose per step
- Optional: modelOutput, formal_instruction, difficulty, exeStatus

Based on: tmp/clearRes_structure.md
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any


def _load_auto(path: Path) -> dict:
    """Auto-detect format and load JSON data."""
    if path.suffix in ('.gzip', '.gz'):
        return _load_gzip(path)
    if path.suffix == '.zip':
        return _load_zip(path)
    return _load_json(path)


def parse_clearres(path: str | Path) -> dict[str, Any]:
    """
    Parse a clearRes file (json, gzip, or zip) and extract key fields.
    
    Returns:
        {
            "ocr_pages": list[dict],          # rawPage OCR trees (one per action response)
            "action_purposes": list[str],     # Agent reasoning per step
            "action_types": list[str],        # open/click/scroll/drag/back/do_nothing
            "model_outputs": list[str],       # <think>...</think> chain (optional)
            "difficulties": list[str],        # easy/medium/hard
            "exe_statuses": list[int],        # 0=success, 301=scroll, 315=manual
        }
    """
    path = Path(path)
    data = _load_auto(path)

    responses = data.get("responses", [])
    
    ocr_pages: list[dict] = []
    action_purposes: list[str] = []
    action_types: list[str] = []
    model_outputs: list[str] = []
    difficulties: list[str] = []
    exe_statuses: list[int] = []

    for resp in responses:
        debug = resp.get("debugInfo", {})
        app_debug = debug.get("appOperationDebugInfo")
        
        if not app_debug:
            continue

        # rawPage — double-escaped JSON string containing OCR tree
        raw_page_str = app_debug.get("rawPage", "")
        if raw_page_str:
            try:
                raw_page = json.loads(raw_page_str)
                if isinstance(raw_page, list) and raw_page:
                    ocr_pages.append(raw_page[0])  # first element is page root
            except (json.JSONDecodeError, TypeError):
                pass

        # actionPurpose
        purp = app_debug.get("actionPurpose", "")
        if purp:
            action_purposes.append(purp.strip())

        # action
        act = app_debug.get("action", "")
        if act:
            action_types.append(act.strip())

        # modelOutput (LLM reasoning)
        mo = app_debug.get("modelOutput", "")
        if mo:
            model_outputs.append(mo.strip())

        # difficulty
        diff = app_debug.get("difficulty", "")
        if diff:
            difficulties.append(diff.strip())

        # exeStatus
        try:
            exe = int(app_debug.get("exeStatus", 0))
        except (ValueError, TypeError):
            exe = -1
        exe_statuses.append(exe)

    return {
        "ocr_pages": ocr_pages,
        "action_purposes": action_purposes,
        "action_types": action_types,
        "model_outputs": model_outputs,
        "difficulties": difficulties,
        "exe_statuses": exe_statuses,
    }


def parse_clearres_light(path: str | Path) -> dict[str, Any]:
    """
    Lightweight parser: only extracts actionPurposes and rawPage OCR trees.
    For use when modelOutput/difficulty are not needed.
    """
    path = Path(path)
    data = _load_auto(path)

    responses = data.get("responses", [])
    
    ocr_pages: list[dict] = []
    action_purposes: list[str] = []

    for resp in responses:
        debug = resp.get("debugInfo", {})
        app_debug = debug.get("appOperationDebugInfo")
        if not app_debug:
            continue

        raw_page_str = app_debug.get("rawPage", "")
        if raw_page_str:
            try:
                raw_page = json.loads(raw_page_str)
                if isinstance(raw_page, list) and raw_page:
                    ocr_pages.append(raw_page[0])
            except (json.JSONDecodeError, TypeError):
                pass

        purp = app_debug.get("actionPurpose", "")
        if purp:
            action_purposes.append(purp.strip())

    return {
        "ocr_pages": ocr_pages,
        "action_purposes": action_purposes,
    }


def _load_gzip(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _load_zip(path: Path) -> dict:
    import zipfile
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        target = next((n for n in names if "clearRes" in n), names[0] if names else "")
        if not target:
            raise FileNotFoundError("No JSON file found in zip")
        with zf.open(target) as f:
            return json.load(f)


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
