"""Dataset persistence helpers for grandma-watcher.

Phase 1 scope: save frame JPEGs and append DatasetEntry JSONL rows.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from config import AppConfig
from models import DatasetEntry


def build_image_filename(timestamp: str) -> str:
    """Convert an ISO 8601 UTC timestamp into the dataset JPEG filename."""
    try:
        parsed = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp for dataset image filename: {timestamp!r}") from exc
    return parsed.strftime("%Y-%m-%d_%H-%M-%S.jpg")


def save_frame_image(config: AppConfig, timestamp: str, frame_bytes: bytes) -> str:
    """Save one frame JPEG and return its relative dataset path."""
    filename = build_image_filename(timestamp)
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / filename).write_bytes(frame_bytes)
    return Path("images", filename).as_posix()


def append_log_entry(config: AppConfig, entry: DatasetEntry) -> None:
    """Append one DatasetEntry as a single JSON object line."""
    log_path = Path(config.dataset.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_safe(dataclasses.asdict(entry))
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


def record_dataset_entry(
    config: AppConfig,
    timestamp: str,
    frame_bytes: bytes,
    entry: DatasetEntry,
    *,
    save_image: bool = True,
) -> DatasetEntry:
    """Append the log row and optionally save the frame image.

    When save_image=False the JSONL entry is written with image_path="" so
    the assessment is always logged, but no JPEG is written to disk.
    """
    if save_image:
        image_path = save_frame_image(config=config, timestamp=timestamp, frame_bytes=frame_bytes)
        entry = dataclasses.replace(entry, image_path=image_path)
    append_log_entry(config, entry)
    return entry


def _json_safe(value: Any) -> Any:
    """Recursively convert enums and nested structures into JSON-safe values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
