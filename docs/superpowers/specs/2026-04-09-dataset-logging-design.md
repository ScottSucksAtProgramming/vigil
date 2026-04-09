# Design Spec: `dataset.py` Phase 1 Logging

**Date:** 2026-04-09
**Project:** grandma-watcher
**Status:** Approved
**Scope:** Save monitoring frame JPEGs and append `DatasetEntry` rows to `log.jsonl`

---

## 1. Overview

`dataset.py` is a small filesystem module that persists the outputs of one monitoring cycle. In Phase 1, it has exactly two responsibilities:

1. Save the JPEG bytes for a frame under `dataset/images/`
2. Append one serialized `DatasetEntry` JSON object to `dataset/log.jsonl`

This module does not decide retention policy, update labels, or mutate existing log rows. It is write-only for now.

**Dependency direction:** `monitor.py → dataset.py → models.py, config.py`

---

## 2. Module Shape

`dataset.py` should remain function-oriented, not class-based. The work is simple, stateless between calls, and easier to test as focused functions.

```python
from config import AppConfig
from models import DatasetEntry

def build_image_filename(timestamp: str) -> str: ...
def save_frame_image(config: AppConfig, timestamp: str, frame_bytes: bytes) -> str: ...
def append_log_entry(config: AppConfig, entry: DatasetEntry) -> None: ...
def record_dataset_entry(
    config: AppConfig,
    timestamp: str,
    frame_bytes: bytes,
    entry: DatasetEntry,
) -> DatasetEntry: ...
```

`record_dataset_entry(...)` is a thin orchestration helper for `monitor.py`: save image first, then append the final entry with the derived relative image path. No additional behavior belongs there.

---

## 3. Data Rules

### Image naming

- Use the existing project convention: `YYYY-MM-DD_HH-MM-SS.jpg`
- Derive the filename from the cycle timestamp, which is already ISO 8601 UTC (`2026-04-09T03:00:00Z`)
- Convert the timestamp to `2026-04-09_03-00-00.jpg`

### Image path in log rows

- Persist relative paths in `DatasetEntry.image_path`
- Format: `images/<filename>.jpg`

This follows the current typed model and tests, even though older PRD text still shows absolute paths. The implementation should match the live codebase contract, not stale prose.

### JSON serialization

- Serialize `DatasetEntry` using `dataclasses.asdict()`
- Convert enums to their `.value` strings recursively
- Preserve nested structure:
  - `sensor_snapshot` remains an object
  - `assessment` remains an object
- Do not flatten the assessment fields in this task
- Emit one compact JSON object per line with a trailing newline

---

## 4. Filesystem Behavior

- Ensure `config.dataset.images_dir` parent directory exists before saving the image
- Ensure the parent directory for `config.dataset.log_file` exists before appending
- Open image files in binary write mode
- Open the log file in text append mode with UTF-8 encoding

No file locking is needed in Phase 1 because the monitor loop is single-threaded. No pruning or overwrite protection is needed beyond deterministic filenames per cycle timestamp.

---

## 5. Error Handling

`dataset.py` should not swallow filesystem errors. If a write fails, let the specific exception propagate to `monitor.py`, where the cycle boundary handles logging and continuation.

This module may raise:

- `ValueError` for malformed timestamps that cannot produce a valid filename
- `OSError` subclasses for directory creation, image writing, or log append failures

No retry logic belongs here.

---

## 6. Testing Strategy

File: `tests/test_dataset.py`

Test the module without real hardware using `tmp_path`.

Coverage:

1. Filename builder converts ISO UTC timestamps to the configured JPEG name format
2. Saving an image creates the directory and writes exact bytes
3. Saving an image returns the relative `images/...` path used by the model
4. Appending a log row creates parent directories and writes one JSON line
5. JSON serialization converts nested enums to strings
6. `record_dataset_entry(...)` writes both files and returns a new `DatasetEntry` with the derived image path
7. Malformed timestamps raise `ValueError`

---

## 7. What Not to Include

- No retention pruning
- No random safe-frame sampling
- No label mutation
- No caregiver check-in log
- No logging module side effects
- No class wrapper
- No monitor-loop business logic

This task is only the persistence primitive that later tasks will call.
