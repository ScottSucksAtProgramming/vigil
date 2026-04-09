# dataset.py Phase 1 Logging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 dataset persistence primitives that save frame JPEGs and append `DatasetEntry` records to `log.jsonl`.

**Architecture:** Keep `dataset.py` as a small functional module with one helper for filenames, one function for image persistence, one for JSONL append, and one thin orchestration helper. Serialize nested dataclasses and enums into JSON-safe values without adding retention or label-update behavior.

**Tech Stack:** Python 3.11, dataclasses, pathlib, json, pytest, tmp_path

---

## Chunk 1: Tests and Module Skeleton

### Task 1: Add failing tests for dataset logging behavior

**Files:**
- Create: `tests/test_dataset.py`
- Modify: none
- Test: `tests/test_dataset.py`

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from config import AppConfig, DatasetConfig
from models import AssessmentResult, Confidence, DatasetEntry, PatientLocation, SensorSnapshot
from dataset import append_log_entry, build_image_filename, record_dataset_entry, save_frame_image
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dataset.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dataset'`

- [ ] **Step 3: Write minimal module skeleton**

Create `dataset.py` with the four public functions and minimal imports/docstrings.

- [ ] **Step 4: Run test to verify collection succeeds and assertions fail**

Run: `pytest tests/test_dataset.py -v`
Expected: FAIL in function behavior assertions, not import errors

## Chunk 2: Implement Filename and Image Persistence

### Task 2: Implement timestamp-to-filename conversion and image write path

**Files:**
- Modify: `dataset.py`
- Test: `tests/test_dataset.py`

- [ ] **Step 1: Write/confirm the targeted failing tests**

Focus on:
- ISO UTC timestamp converts to `YYYY-MM-DD_HH-MM-SS.jpg`
- malformed timestamp raises `ValueError`
- image directory is created
- exact frame bytes are written
- returned path is `images/<filename>.jpg`

- [ ] **Step 2: Run the targeted tests**

Run: `pytest tests/test_dataset.py -k "filename or image" -v`
Expected: FAIL

- [ ] **Step 3: Implement the minimal code**

Use `datetime.strptime(..., "%Y-%m-%dT%H:%M:%SZ")` and `pathlib.Path.mkdir(parents=True, exist_ok=True)`.

- [ ] **Step 4: Run the targeted tests again**

Run: `pytest tests/test_dataset.py -k "filename or image" -v`
Expected: PASS

## Chunk 3: Implement JSONL Serialization and Append

### Task 3: Serialize `DatasetEntry` and append one JSON object per line

**Files:**
- Modify: `dataset.py`
- Test: `tests/test_dataset.py`

- [ ] **Step 1: Write/confirm the targeted failing tests**

Focus on:
- parent directory for `log.jsonl` is created
- one JSON line is appended
- nested dataclasses remain nested objects
- enums serialize to string `.value`

- [ ] **Step 2: Run the targeted tests**

Run: `pytest tests/test_dataset.py -k "append or serial" -v`
Expected: FAIL

- [ ] **Step 3: Implement the minimal code**

Add a recursive helper that converts dataclass-produced structures and enums into JSON-safe primitives before `json.dumps(...)`.

- [ ] **Step 4: Run the targeted tests again**

Run: `pytest tests/test_dataset.py -k "append or serial" -v`
Expected: PASS

## Chunk 4: Implement Orchestration Helper and Full Verification

### Task 4: Save image then append a final `DatasetEntry`

**Files:**
- Modify: `dataset.py`
- Test: `tests/test_dataset.py`

- [ ] **Step 1: Write/confirm the failing orchestration test**

Assert that `record_dataset_entry(...)`:
- writes the image
- appends one log row
- returns a new `DatasetEntry` with the derived `image_path`

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_dataset.py -k record -v`
Expected: FAIL

- [ ] **Step 3: Implement the minimal code**

Use `dataclasses.replace(entry, image_path=relative_path)` so the frozen model instance remains immutable.

- [ ] **Step 4: Run the full test file**

Run: `pytest tests/test_dataset.py -v`
Expected: PASS

- [ ] **Step 5: Run the project verification**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Run formatting and lint checks**

Run: `ruff check .`
Expected: PASS

Run: `black --check .`
Expected: PASS
