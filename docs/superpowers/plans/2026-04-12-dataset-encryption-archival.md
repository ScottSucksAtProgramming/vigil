# Dataset Encryption and Archival Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encrypt labeled JPEG frames older than 24 hours with `age`, sync them to a TrueNAS NAS nightly, and show an "Archived" badge in the gallery UI.

**Architecture:** An hourly `archiver.py` reads `log.jsonl` to find labeled frames, encrypts eligible files, and batch-patches the log. A nightly `nas_sync.py` rsyncs the encrypted archive to NAS then deletes synced files on success. All log rewrites go through a shared `rewrite_log()` primitive protected by `fcntl.flock`.

**Tech Stack:** Python 3.11+, `age` CLI binary, `rsync`, `fcntl`, Flask, systemd timers

**Design spec:** `docs/superpowers/specs/2026-04-12-dataset-encryption-archival-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `config.py` | Add 4 SecurityConfig fields, `archive_dir` to DatasetConfig, fix `image_interval_minutes` passthrough, cross-field validation |
| Modify | `models.py` | Add `image_archived: bool = False` to `DatasetEntry` |
| Modify | `dataset.py` | Add `read_log()`, `rewrite_log()`, `patch_log_entry()`; add `flock` to `append_log_entry` |
| Modify | `web_server.py` | Refactor `/label` to use `patch_log_entry`; update `/images` to serve archived placeholder |
| Create | `archiver.py` | `run_archive_cycle(config)` — encrypt labeled frames older than threshold |
| Create | `nas_sync.py` | `run_nas_sync(config)` — two-phase rsync to NAS |
| Modify | `static/dashboard.js` | Archived badge on thumbnail and modal |
| Modify | `templates/dashboard.html` | Add `modal-archived-notice` element |
| Create | `static/archived_placeholder.jpg` | Placeholder image for archived frames |
| Create | `setup/systemd/archiver.service` | One-shot service for archiver |
| Create | `setup/systemd/archiver.timer` | Hourly timer |
| Create | `setup/systemd/nas_sync.service` | One-shot service for NAS sync |
| Create | `setup/systemd/nas_sync.timer` | Nightly 03:00 timer |
| Modify | `setup/install.sh` | Install `age`, add `install_timer` helper, enable both timers |
| Modify | `docs/INSTALL_GUIDE.md` | New section: Dataset Encryption and NAS Sync Setup |
| Create | `tests/test_config.py` | Config field and validation tests |
| Modify | `tests/test_models.py` | Test `image_archived` default |
| Modify | `tests/test_dataset.py` | Tests for `rewrite_log`, `patch_log_entry`, flock in `append_log_entry` |
| Modify | `tests/test_web_server.py` | Tests for archived placeholder route, label route refactor |
| Create | `tests/test_archiver.py` | Full coverage of `run_archive_cycle` |
| Create | `tests/test_nas_sync.py` | Full coverage of `run_nas_sync` |

---

## Task 1: Config layer — SecurityConfig + DatasetConfig + validation

**Files:**
- Modify: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
"""Tests for config.py — Milestone 5 additions."""

import pytest
import yaml


def test_security_config_archival_fields_have_correct_defaults():
    from config import SecurityConfig

    cfg = SecurityConfig()
    assert cfg.archive_after_hours == 24.0
    assert cfg.age_public_key == ""
    assert cfg.nas_sync_enabled is False
    assert cfg.nas_rsync_target == ""


def test_dataset_config_archive_dir_derived_from_base_dir(tmp_path):
    from config import _build_dataset

    raw = {"dataset": {"base_dir": str(tmp_path / "ds")}}
    cfg = _build_dataset(raw)
    assert cfg.archive_dir == str(tmp_path / "ds" / "archive")


def test_dataset_config_archive_dir_explicit_overrides_default(tmp_path):
    from config import _build_dataset

    raw = {"dataset": {"base_dir": str(tmp_path), "archive_dir": "/custom/archive"}}
    cfg = _build_dataset(raw)
    assert cfg.archive_dir == "/custom/archive"


def test_image_interval_minutes_yaml_override_is_respected(tmp_path):
    from config import _build_dataset

    raw = {"dataset": {"base_dir": str(tmp_path), "image_interval_minutes": 10}}
    cfg = _build_dataset(raw)
    assert cfg.image_interval_minutes == 10


def test_load_config_rejects_nas_sync_enabled_without_target(tmp_path):
    from config import load_config

    cfg_dict = {
        "api": {"provider": "nanogpt", "nanogpt_api_key": "x"},
        "monitor": {"interval_seconds": 30},
        "alerts": {"pushover_api_key": "x", "pushover_user_key": "x"},
        "security": {"nas_sync_enabled": True, "nas_rsync_target": ""},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg_dict))
    with pytest.raises(ValueError, match="nas_rsync_target"):
        load_config(str(path))


def test_load_config_accepts_nas_sync_enabled_with_target(tmp_path):
    from config import load_config

    cfg_dict = {
        "api": {"provider": "nanogpt", "nanogpt_api_key": "x"},
        "monitor": {"interval_seconds": 30},
        "alerts": {"pushover_api_key": "x", "pushover_user_key": "x"},
        "security": {
            "nas_sync_enabled": True,
            "nas_rsync_target": "vigil-sync@100.1.2.3:/mnt/pool",
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg_dict))
    config = load_config(str(path))
    assert config.security.nas_sync_enabled is True
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/scottkostolni/programming_projects/vigil
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `SecurityConfig` missing fields, `_build_dataset` missing `archive_dir`.

- [ ] **Step 3: Add fields to `SecurityConfig` in `config.py`**

In `config.py`, find the `SecurityConfig` dataclass and add four fields:

```python
@dataclass(frozen=True)
class SecurityConfig:
    stream_pause_auto_resume_hours: float = 4.0
    access_notification_window_minutes: int = 15
    access_notification_ip_whitelist: list[str] = field(default_factory=list)
    archive_after_hours: float = 24.0
    age_public_key: str = ""
    nas_sync_enabled: bool = False
    nas_rsync_target: str = ""
```

- [ ] **Step 4: Add `archive_dir` to `DatasetConfig` in `config.py`**

Find the `DatasetConfig` dataclass and add one field:

```python
@dataclass(frozen=True)
class DatasetConfig:
    base_dir: str = "/home/pi/eldercare/dataset"
    images_dir: str = ""
    log_file: str = ""
    checkin_log_file: str = ""
    archive_dir: str = ""  # derived as {base_dir}/archive in _build_dataset if empty
    max_disk_gb: int = 50
    image_interval_minutes: int = 5
    retention: RetentionConfig = field(default_factory=RetentionConfig)
```

- [ ] **Step 5: Update `_build_dataset` to pass `archive_dir` and `image_interval_minutes`**

Find `_build_dataset` and replace its return statement:

```python
def _build_dataset(raw: dict[str, Any]) -> DatasetConfig:
    """Build DatasetConfig, deriving sub-paths from base_dir when not specified."""
    section = raw.get("dataset", {}) or {}
    base_dir = str(section.get("base_dir") or "/home/pi/eldercare/dataset")
    images_dir = str(section.get("images_dir") or f"{base_dir}/images")
    log_file = str(section.get("log_file") or f"{base_dir}/log.jsonl")
    checkin_log_file = str(section.get("checkin_log_file") or f"{base_dir}/checkins.jsonl")
    archive_dir = str(section.get("archive_dir") or f"{base_dir}/archive")
    max_disk_gb = int(section.get("max_disk_gb", 50))
    image_interval_minutes = int(section.get("image_interval_minutes", 5))
    retention_raw = section.get("retention", {}) or {}
    retention = _build_section({"retention": retention_raw}, "retention", RetentionConfig)
    return DatasetConfig(
        base_dir=base_dir,
        images_dir=images_dir,
        log_file=log_file,
        checkin_log_file=checkin_log_file,
        archive_dir=archive_dir,
        max_disk_gb=max_disk_gb,
        image_interval_minutes=image_interval_minutes,
        retention=retention,
    )
```

- [ ] **Step 6: Add cross-field validation to `load_config`**

In `load_config`, after the existing missing-secrets check, add:

```python
    if config.security.nas_sync_enabled and not config.security.nas_rsync_target:
        raise ValueError(
            "Config: security.nas_sync_enabled is True but security.nas_rsync_target is empty"
        )
```

- [ ] **Step 7: Run tests — verify they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 8: Run full test suite — no regressions**

```bash
python -m pytest -x -q
```

Expected: all existing tests PASS.

- [ ] **Step 9: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add Milestone 5 config fields — archive_dir, age_public_key, nas_sync settings"
```

---

## Task 2: DatasetEntry — `image_archived` field

**Files:**
- Modify: `models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_models.py`, add at the bottom:

```python
def test_dataset_entry_image_archived_defaults_to_false():
    entry = DatasetEntry(
        timestamp="2026-04-09T03:00:00Z",
        image_path="images/test.jpg",
        provider="nanogpt",
        model="Qwen3 VL 235B A22B Instruct",
        prompt_version="1.0",
        sensor_snapshot=SensorSnapshot(load_cells_enabled=False, vitals_enabled=False),
        response_raw="{}",
        assessment=AssessmentResult(
            safe=True,
            confidence=Confidence.HIGH,
            reason="ok",
            patient_location=PatientLocation.IN_BED,
        ),
        alert_fired=False,
        api_latency_ms=100.0,
    )
    assert entry.image_archived is False


def test_dataset_entry_image_archived_can_be_set_true():
    from dataclasses import replace

    entry = DatasetEntry(
        timestamp="2026-04-09T03:00:00Z",
        image_path="images/test.jpg",
        provider="nanogpt",
        model="Qwen3 VL 235B A22B Instruct",
        prompt_version="1.0",
        sensor_snapshot=SensorSnapshot(load_cells_enabled=False, vitals_enabled=False),
        response_raw="{}",
        assessment=AssessmentResult(
            safe=True,
            confidence=Confidence.HIGH,
            reason="ok",
            patient_location=PatientLocation.IN_BED,
        ),
        alert_fired=False,
        api_latency_ms=100.0,
    )
    archived = replace(entry, image_archived=True)
    assert archived.image_archived is True
```

- [ ] **Step 2: Run test — verify it fails**

```bash
python -m pytest tests/test_models.py::test_dataset_entry_image_archived_defaults_to_false -v
```

Expected: FAIL — `DatasetEntry` has no `image_archived` field.

- [ ] **Step 3: Add `image_archived` to `DatasetEntry` in `models.py`**

Find `DatasetEntry` and add `image_archived` after `image_pruned`:

```python
@dataclass(frozen=True)
class DatasetEntry:
    timestamp: str
    image_path: str
    provider: str
    model: str
    prompt_version: str
    sensor_snapshot: SensorSnapshot
    response_raw: str
    assessment: AssessmentResult
    alert_fired: bool
    api_latency_ms: float
    silence_active: bool = False
    image_pruned: bool = False
    image_archived: bool = False
    label: str = ""
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_models.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite — no regressions**

```bash
python -m pytest -x -q
```

Expected: all PASS. (Existing `_ENTRY_TEMPLATE` in `test_web_server.py` doesn't include `image_archived` — that's fine since the field has a default.)

- [ ] **Step 6: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add image_archived field to DatasetEntry"
```

---

## Task 3: `dataset.py` — `rewrite_log`, `patch_log_entry`, flock in `append_log_entry`

**Files:**
- Modify: `dataset.py`
- Modify: `tests/test_dataset.py`

- [ ] **Step 1: Write the failing tests**

Add the following to the bottom of `tests/test_dataset.py`. The `_dataset_config` and `_app_config` helpers already exist in that file — use them.

```python
# ── read_log ───────────────────────────────────────────────


def test_read_log_returns_all_rows(sample_config, tmp_path):
    from dataset import append_log_entry, read_log

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry(
        image_path="images/2026-04-09_03-00-00.jpg",
        timestamp="2026-04-09T03:00:00Z",
    )
    append_log_entry(config, entry)

    rows = read_log(config)
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-04-09T03:00:00Z"


def test_read_log_returns_empty_list_for_missing_file(sample_config, tmp_path):
    from dataset import read_log

    config = _app_config(sample_config, tmp_path)
    assert read_log(config) == []


# ── rewrite_log ────────────────────────────────────────────


def test_rewrite_log_applies_transform_and_rewrites_file(sample_config, tmp_path):
    from dataset import append_log_entry, rewrite_log

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry(
        image_path="images/2026-04-09_03-00-00.jpg",
        timestamp="2026-04-09T03:00:00Z",
    )
    append_log_entry(config, entry)

    def _mark_all_archived(rows):
        for row in rows:
            row["image_archived"] = True
        return rows

    rewrite_log(config, _mark_all_archived)

    log_path = tmp_path / "dataset" / "log.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["image_archived"] is True


def test_rewrite_log_handles_missing_log_file(sample_config, tmp_path):
    from dataset import rewrite_log

    config = _app_config(sample_config, tmp_path)
    # log.jsonl does not exist yet — must not raise
    rewrite_log(config, lambda rows: rows)


def test_rewrite_log_handles_empty_log_file(sample_config, tmp_path):
    from dataset import rewrite_log

    config = _app_config(sample_config, tmp_path)
    log_path = tmp_path / "dataset" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    # Must not raise on empty file
    rewrite_log(config, lambda rows: rows)


# ── patch_log_entry ────────────────────────────────────────


def test_patch_log_entry_updates_matching_row_by_timestamp(sample_config, tmp_path):
    from dataset import append_log_entry, patch_log_entry

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry(
        image_path="images/2026-04-09_03-00-00.jpg",
        timestamp="2026-04-09T03:00:00Z",
    )
    append_log_entry(config, entry)

    patch_log_entry(config, "2026-04-09T03:00:00Z", {"image_archived": True})

    log_path = tmp_path / "dataset" / "log.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["image_archived"] is True


def test_patch_log_entry_no_op_when_timestamp_not_found(sample_config, tmp_path):
    from dataset import append_log_entry, patch_log_entry

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry(
        image_path="images/2026-04-09_03-00-00.jpg",
        timestamp="2026-04-09T03:00:00Z",
    )
    append_log_entry(config, entry)

    # Should not raise; logs a warning internally
    patch_log_entry(config, "1999-01-01T00:00:00Z", {"image_archived": True})

    log_path = tmp_path / "dataset" / "log.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload.get("image_archived", False) is False


def test_patch_log_entry_preserves_other_rows(sample_config, tmp_path):
    from dataset import append_log_entry, patch_log_entry

    config = _app_config(sample_config, tmp_path)
    entry1 = _dataset_entry(
        image_path="images/2026-04-09_03-00-00.jpg",
        timestamp="2026-04-09T03:00:00Z",
    )
    entry2 = _dataset_entry(
        image_path="images/2026-04-09_03-00-30.jpg",
        timestamp="2026-04-09T03:00:30Z",
    )
    append_log_entry(config, entry1)
    append_log_entry(config, entry2)

    patch_log_entry(config, "2026-04-09T03:00:00Z", {"image_archived": True})

    log_path = tmp_path / "dataset" / "log.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row2 = json.loads(lines[1])
    assert row2.get("image_archived", False) is False
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_dataset.py::test_rewrite_log_applies_transform_and_rewrites_file tests/test_dataset.py::test_patch_log_entry_updates_matching_row_by_timestamp -v
```

Expected: FAIL — `rewrite_log` and `patch_log_entry` not defined.

- [ ] **Step 3: Implement `rewrite_log`, `patch_log_entry`, and update `append_log_entry` in `dataset.py`**

Add `fcntl`, `json` (already imported), and `tempfile` to the imports at the top of `dataset.py`:

```python
from __future__ import annotations

import dataclasses
import fcntl
import json
import logging
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from config import AppConfig
from models import DatasetEntry

logger = logging.getLogger(__name__)
```

Replace the existing `append_log_entry` function with this flock-aware version:

```python
def append_log_entry(config: AppConfig, entry: DatasetEntry) -> None:
    """Append one DatasetEntry as a single JSON object line.

    Acquires an exclusive flock on log.jsonl.lock so concurrent
    rewrite_log calls cannot lose this append.
    """
    log_path = Path(config.dataset.log_file)
    lock_path = Path(config.dataset.log_file + ".lock")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_safe(dataclasses.asdict(entry))
    with lock_path.open("a") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload))
                handle.write("\n")
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
```

Add these three new functions after `append_log_entry`:

```python
def read_log(config: AppConfig) -> list[dict]:
    """Read log.jsonl rows under the shared flock, returning a list of dicts.

    Uses the same lock as rewrite_log and append_log_entry so reads are
    consistent with concurrent writes. Returns [] if the file is missing or empty.
    """
    log_path = Path(config.dataset.log_file)
    lock_path = Path(config.dataset.log_file + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_SH)  # shared lock — allows concurrent reads
        try:
            rows: list[dict] = []
            if log_path.exists() and log_path.stat().st_size > 0:
                for line in log_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped:
                        try:
                            rows.append(json.loads(stripped))
                        except json.JSONDecodeError:
                            logger.warning("read_log: skipping malformed line")
            return rows
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def rewrite_log(config: AppConfig, transform) -> None:
    """Atomically rewrite log.jsonl by applying transform(rows) -> rows.

    Acquires an exclusive flock on log.jsonl.lock before reading so all
    writers (monitor, label route, archiver) participate in the same lock.
    Uses temp-file-rename for atomicity (same filesystem, POSIX rename).
    """
    log_path = Path(config.dataset.log_file)
    lock_path = Path(config.dataset.log_file + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            rows: list[dict] = []
            if log_path.exists() and log_path.stat().st_size > 0:
                for line in log_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped:
                        try:
                            rows.append(json.loads(stripped))
                        except json.JSONDecodeError:
                            logger.warning("rewrite_log: skipping malformed line")

            rows = transform(rows)

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=log_path.parent,
                    delete=False,
                    suffix=".tmp",
                ) as tmp:
                    for row in rows:
                        tmp.write(json.dumps(row))
                        tmp.write("\n")
                    tmp_path = Path(tmp.name)
                tmp_path.rename(log_path)
            except Exception:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def patch_log_entry(config: AppConfig, timestamp: str, updates: dict) -> None:
    """Update fields in the log.jsonl row matching timestamp.

    Uses rewrite_log for atomicity. Logs a warning if no matching row is found.
    """
    found = [False]

    def _transform(rows: list[dict]) -> list[dict]:
        for row in rows:
            if row.get("timestamp") == timestamp:
                row.update(updates)
                found[0] = True
        return rows

    rewrite_log(config, _transform)

    if not found[0]:
        logger.warning("patch_log_entry: no row found with timestamp %r", timestamp)
```

- [ ] **Step 4: Run the new tests — verify they pass**

```bash
python -m pytest tests/test_dataset.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite — no regressions**

```bash
python -m pytest -x -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add dataset.py tests/test_dataset.py
git commit -m "feat: add rewrite_log + patch_log_entry + flock to append_log_entry"
```

---

## Task 4: Refactor `/label` route to use `patch_log_entry`

**Files:**
- Modify: `web_server.py`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Update the existing label 404-on-miss test**

The refactored route delegates entirely to `patch_log_entry`, which is a no-op on miss (logs a warning, returns 200). The existing `test_label_returns_404_when_entry_not_found` tests the old behavior and must be updated.

In `tests/test_web_server.py`, find `test_label_returns_404_when_entry_not_found` and replace the entire function (name and body) with:

```python
def test_label_returns_200_when_entry_not_found(sample_config, tmp_path):
    """POST /label/<unknown_id> returns 200 (patch_log_entry is a no-op on miss)."""
    log_file = tmp_path / "log.jsonl"
    entry = _make_entry(timestamp="2026-04-10T12:00:00Z")
    log_file.write_text(json.dumps(entry) + "\n")

    patched_dataset = dataclasses.replace(sample_config.dataset, log_file=str(log_file))
    cfg = dataclasses.replace(sample_config, dataset=patched_dataset)
    app = create_app(cfg)
    app.config["TESTING"] = True

    with app.test_client() as c:
        response = c.post("/label/9999-01-01T00:00:00Z", json={"label": "correct"})

    assert response.status_code == 200
```

Do NOT change `test_label_writes_label_to_matching_log_entry` or `test_label_preserves_other_entries` — they work as-is since `patch_log_entry` only needs `config.dataset.log_file`.

- [ ] **Step 2: Run the label tests — confirm they fail (or pass for the changed one)**

```bash
python -m pytest tests/test_web_server.py -k "label" -v
```

The existing `test_label_writes_label_to_matching_log_entry` should PASS (behavior unchanged). `test_label_preserves_other_entries` should PASS. The renamed test should PASS (expects 200, and current route returns 200 on found entry).

- [ ] **Step 3: Refactor the `/label` route in `web_server.py`**

At the top of `create_app()`, the function already imports from `dataset` implicitly via config. Add the import of `patch_log_entry` at the module level or at the top of `create_app`. Add to the top-level imports in `web_server.py`:

```python
from dataset import patch_log_entry
```

Replace the entire `label` route function inside `create_app`:

```python
    @app.route("/label/<entry_id>", methods=["POST"])
    def label(entry_id: str) -> Response:
        """Write a label to the matching log.jsonl entry via patch_log_entry."""
        body = request.get_json(silent=True) or {}
        label_value = body.get("label", "")
        patch_log_entry(config, entry_id, {"label": label_value})
        return jsonify({"status": "ok", "id": entry_id})
```

Remove the `import json` and `import os` lines that were inside the old route body (they are no longer needed there).

- [ ] **Step 4: Run label tests — verify they pass**

```bash
python -m pytest tests/test_web_server.py -k "label" -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -x -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add web_server.py tests/test_web_server.py
git commit -m "refactor: label route delegates to patch_log_entry"
```

---

## Task 5: `archiver.py`

**Files:**
- Create: `archiver.py`
- Create: `tests/test_archiver.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_archiver.py`:

```python
"""Tests for archiver.py — run_archive_cycle."""

import dataclasses
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import call, patch

import pytest

from config import AppConfig, DatasetConfig, SecurityConfig


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_config(sample_config: AppConfig, tmp_path: Path, **security_overrides) -> AppConfig:
    dataset = dataclasses.replace(
        sample_config.dataset,
        base_dir=str(tmp_path / "dataset"),
        images_dir=str(tmp_path / "dataset" / "images"),
        archive_dir=str(tmp_path / "dataset" / "archive"),
        log_file=str(tmp_path / "dataset" / "log.jsonl"),
        checkin_log_file=str(tmp_path / "dataset" / "checkins.jsonl"),
    )
    security = dataclasses.replace(
        sample_config.security,
        age_public_key="age1publickey",
        archive_after_hours=24.0,
        **security_overrides,
    )
    return dataclasses.replace(sample_config, dataset=dataset, security=security)


def _write_log(log_path: Path, entries: list[dict]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )


def _old_filename() -> str:
    """Return a filename for a JPEG that is 25 hours old."""
    ts = datetime.now(tz=timezone.utc) - timedelta(hours=25)
    return ts.strftime("%Y-%m-%d_%H-%M-%S.jpg")


def _recent_filename() -> str:
    """Return a filename for a JPEG that is 1 hour old (within review window)."""
    ts = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    return ts.strftime("%Y-%m-%d_%H-%M-%S.jpg")


def _image_path_for(filename: str) -> str:
    return f"images/{filename}"


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_archive_cycle_skips_when_age_public_key_empty(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path, age_public_key="")
    fake_run = lambda *a, **kw: None  # should never be called

    run_archive_cycle(config, _run=fake_run)  # must not raise


def test_archive_cycle_skips_when_age_binary_not_found(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    with patch("archiver.shutil.which", return_value=None):
        run_archive_cycle(config)  # must not raise, must not encrypt


def test_archive_cycle_skips_files_younger_than_threshold(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _recent_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")

    _write_log(
        Path(config.dataset.log_file),
        [{"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "real_issue", "image_archived": False}],
    )

    calls = []
    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=lambda *a, **kw: calls.append(a))

    assert calls == [], "No encryption should have been attempted for a recent file"
    assert (images_dir / filename).exists(), "Recent file should not be deleted"


def test_archive_cycle_skips_unlabeled_files(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _old_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")

    _write_log(
        Path(config.dataset.log_file),
        [{"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "", "image_archived": False}],
    )

    calls = []
    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=lambda *a, **kw: calls.append(a))

    assert calls == [], "Unlabeled files must not be archived"
    assert (images_dir / filename).exists()


def test_archive_cycle_skips_log_entries_with_empty_image_path(sample_config, tmp_path):
    """Entries with image_path='' should not create a phantom '' key in the label map."""
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _old_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")

    # One entry with empty image_path (labeled), one with the real file (unlabeled)
    _write_log(
        Path(config.dataset.log_file),
        [
            {"timestamp": "2026-04-09T02:00:00Z", "image_path": "", "label": "real_issue", "image_archived": False},
            {"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "", "image_archived": False},
        ],
    )

    calls = []
    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=lambda *a, **kw: calls.append(a))

    assert calls == [], "File with empty image_path must not create phantom label match"
    assert (images_dir / filename).exists()


def test_archive_cycle_encrypts_labeled_old_file_verifies_and_deletes(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _old_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")
    archive_dir = Path(config.dataset.archive_dir)

    _write_log(
        Path(config.dataset.log_file),
        [{"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "real_issue", "image_archived": False}],
    )

    def fake_run(cmd, **kwargs):
        # Simulate age writing a .age file
        age_out = Path(cmd[cmd.index("-o") + 1])
        age_out.parent.mkdir(parents=True, exist_ok=True)
        age_out.write_bytes(b"encrypted data")
        result = subprocess.CompletedProcess(cmd, 0)
        return result

    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=fake_run)

    assert not (images_dir / filename).exists(), "Original JPEG must be deleted after encryption"
    assert (archive_dir / f"{filename}.age").exists(), ".age file must exist"

    log = json.loads(Path(config.dataset.log_file).read_text(encoding="utf-8"))
    assert log["image_archived"] is True


def test_archive_cycle_does_not_delete_original_when_age_file_missing(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _old_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")

    _write_log(
        Path(config.dataset.log_file),
        [{"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "real_issue", "image_archived": False}],
    )

    def fake_run_fails(cmd, **kwargs):
        # Simulate age failing — no .age file written
        return subprocess.CompletedProcess(cmd, 1, stderr=b"key error")

    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=fake_run_fails)

    assert (images_dir / filename).exists(), "Original must NOT be deleted when encryption fails"
    log = json.loads(Path(config.dataset.log_file).read_text(encoding="utf-8"))
    assert log["image_archived"] is False


def test_archive_cycle_does_not_delete_original_when_age_file_zero_bytes(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _old_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True)

    _write_log(
        Path(config.dataset.log_file),
        [{"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "real_issue", "image_archived": False}],
    )

    def fake_run_zero(cmd, **kwargs):
        age_out = Path(cmd[cmd.index("-o") + 1])
        age_out.write_bytes(b"")  # zero-byte output
        return subprocess.CompletedProcess(cmd, 0)

    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=fake_run_zero)

    assert (images_dir / filename).exists(), "Original must NOT be deleted when .age is zero bytes"


def test_archive_cycle_creates_archive_dir_if_missing(sample_config, tmp_path):
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    filename = _old_filename()
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)
    (images_dir / filename).write_bytes(b"fake jpeg")
    archive_dir = Path(config.dataset.archive_dir)
    assert not archive_dir.exists(), "archive_dir must not exist before the test"

    _write_log(
        Path(config.dataset.log_file),
        [{"timestamp": "2026-04-09T03:00:00Z", "image_path": _image_path_for(filename), "label": "real_issue", "image_archived": False}],
    )

    def fake_run(cmd, **kwargs):
        age_out = Path(cmd[cmd.index("-o") + 1])
        age_out.parent.mkdir(parents=True, exist_ok=True)
        age_out.write_bytes(b"encrypted")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        run_archive_cycle(config, _run=fake_run)

    assert archive_dir.exists(), "archive_dir must be created by the archiver"


def test_archive_cycle_batch_rewrites_log_once_for_multiple_files(sample_config, tmp_path):
    """The archiver calls rewrite_log once for all archived files, not once per file."""
    from archiver import run_archive_cycle

    config = _make_config(sample_config, tmp_path)
    images_dir = Path(config.dataset.images_dir)
    images_dir.mkdir(parents=True)

    filenames = [
        (datetime.now(tz=timezone.utc) - timedelta(hours=25 + i)).strftime("%Y-%m-%d_%H-%M-%S.jpg")
        for i in range(3)
    ]
    for fn in filenames:
        (images_dir / fn).write_bytes(b"fake jpeg")

    log_entries = [
        {"timestamp": f"2026-04-09T0{i}:00:00Z", "image_path": f"images/{fn}", "label": "real_issue", "image_archived": False}
        for i, fn in enumerate(filenames)
    ]
    _write_log(Path(config.dataset.log_file), log_entries)

    def fake_run(cmd, **kwargs):
        age_out = Path(cmd[cmd.index("-o") + 1])
        age_out.parent.mkdir(parents=True, exist_ok=True)
        age_out.write_bytes(b"encrypted")
        return subprocess.CompletedProcess(cmd, 0)

    rewrite_call_count = [0]
    import dataset as _dataset
    original_rewrite_log = _dataset.rewrite_log

    def counting_rewrite(config, transform):
        rewrite_call_count[0] += 1
        return original_rewrite_log(config, transform)

    with patch("archiver.shutil.which", return_value="/usr/bin/age"):
        with patch("archiver.rewrite_log", side_effect=counting_rewrite):
            run_archive_cycle(config, _run=fake_run)

    assert rewrite_call_count[0] == 1, "rewrite_log must be called exactly once per cycle"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_archiver.py -v
```

Expected: FAIL — `archiver` module does not exist.

- [ ] **Step 3: Implement `archiver.py`**

Create `archiver.py` in the project root:

```python
"""Dataset archiver for vigil.

Scans dataset/images/ for labeled JPEGs older than archive_after_hours,
encrypts each with the `age` CLI tool, verifies the output, deletes the
original, and batch-updates log.jsonl.

Entry point: run_archive_cycle(config)
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from config import AppConfig
from dataset import read_log, rewrite_log

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.jpg$")
_TIMESTAMP_FMT = "%Y-%m-%d_%H-%M-%S"


def _parse_filename_age_seconds(filename: str, now: datetime) -> float | None:
    """Return seconds since the frame was captured, or None if unparseable."""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(1), _TIMESTAMP_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (now - ts).total_seconds()


def run_archive_cycle(
    config: AppConfig,
    *,
    _run: Callable = subprocess.run,
) -> None:
    """Encrypt labeled JPEG frames older than archive_after_hours.

    Steps:
    1. Skip if age_public_key is empty.
    2. Check that the `age` binary is available.
    3. Read log.jsonl once to build a {filename: label} map.
    4. Scan dataset/images/ for old, labeled files.
    5. Encrypt each, verify, delete original.
    6. Batch-rewrite log.jsonl once for all archived files.
    """
    if not config.security.age_public_key:
        logger.warning("archiver: age_public_key not configured — skipping archive cycle")
        return

    if not shutil.which("age"):
        logger.error("archiver: 'age' binary not found — install with: sudo apt install age")
        return

    # Build filename → label map from log.jsonl (read under LOCK_SH via read_log)
    label_map: dict[str, str] = {}
    for row in read_log(config):
        image_path = row.get("image_path", "")
        if not image_path:
            continue  # skip entries with no image (save_image=False cycles)
        filename = Path(image_path).name
        label_map[filename] = row.get("label", "")

    images_dir = Path(config.dataset.images_dir)
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=timezone.utc)
    threshold_seconds = config.security.archive_after_hours * 3600

    archived_filenames: list[str] = []

    for jpg in sorted(images_dir.glob("*.jpg")):
        age_seconds = _parse_filename_age_seconds(jpg.name, now)
        if age_seconds is None:
            logger.warning("archiver: skipping file with unparseable name: %s", jpg.name)
            continue
        if age_seconds < threshold_seconds:
            continue  # still in active review window

        label = label_map.get(jpg.name, "")
        if not label:
            continue  # unlabeled — no training value, skip

        age_file = archive_dir / f"{jpg.name}.age"
        result = _run(
            [
                "age",
                "-r", config.security.age_public_key,
                "-o", str(age_file),
                str(jpg),
            ],
            capture_output=True,
        )

        if result.returncode != 0 or not age_file.exists() or age_file.stat().st_size == 0:
            logger.error(
                "archiver: encryption failed for %s (returncode=%s) — original preserved",
                jpg.name,
                result.returncode,
            )
            if age_file.exists():
                age_file.unlink(missing_ok=True)
            continue

        jpg.unlink()
        archived_filenames.append(jpg.name)
        logger.info("archiver: archived %s", jpg.name)

    if not archived_filenames:
        return

    archived_set = set(archived_filenames)

    def _mark_archived(rows: list[dict]) -> list[dict]:
        for row in rows:
            if Path(row.get("image_path", "")).name in archived_set:
                row["image_archived"] = True
        return rows

    rewrite_log(config, _mark_archived)
    logger.info("archiver: marked %d entries as archived in log.jsonl", len(archived_filenames))


if __name__ == "__main__":
    import logging as _logging
    from config import load_config as _load_config

    _logging.basicConfig(level=_logging.INFO)
    run_archive_cycle(_load_config())
```

- [ ] **Step 4: Run archiver tests — verify they pass**

```bash
python -m pytest tests/test_archiver.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -x -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add archiver.py tests/test_archiver.py
git commit -m "feat: implement archiver.py — encrypt labeled frames older than threshold"
```

---

## Task 6: `nas_sync.py`

**Files:**
- Create: `nas_sync.py`
- Create: `tests/test_nas_sync.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_nas_sync.py`:

```python
"""Tests for nas_sync.py — run_nas_sync."""

import dataclasses
import subprocess
from pathlib import Path
from unittest.mock import call

import pytest

from config import AppConfig, DatasetConfig, SecurityConfig


def _make_config(sample_config: AppConfig, tmp_path: Path, **security_overrides) -> AppConfig:
    dataset = dataclasses.replace(
        sample_config.dataset,
        base_dir=str(tmp_path / "dataset"),
        archive_dir=str(tmp_path / "dataset" / "archive"),
        log_file=str(tmp_path / "dataset" / "log.jsonl"),
        checkin_log_file=str(tmp_path / "dataset" / "checkins.jsonl"),
    )
    security = dataclasses.replace(
        sample_config.security,
        nas_sync_enabled=True,
        nas_rsync_target="vigil-sync@100.1.2.3:/mnt/pool/vigil-archive",
        **security_overrides,
    )
    return dataclasses.replace(sample_config, dataset=dataset, security=security)


def test_nas_sync_skips_when_disabled(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path, nas_sync_enabled=False)
    calls = []
    run_nas_sync(config, _run=lambda *a, **kw: calls.append(a))
    assert calls == []


def test_nas_sync_skips_when_target_empty(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path, nas_rsync_target="")
    calls = []
    run_nas_sync(config, _run=lambda *a, **kw: calls.append(a))
    assert calls == []


def test_nas_sync_calls_rsync_for_archive_dir(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path)
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True)

    results = []

    def fake_run(cmd, **kwargs):
        results.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    run_nas_sync(config, _run=fake_run)

    archive_calls = [r for r in results if "archive" in " ".join(r)]
    assert len(archive_calls) >= 1
    archive_cmd = archive_calls[0]
    assert "rsync" in archive_cmd[0]
    assert "-avz" in archive_cmd
    assert str(archive_dir) + "/" in archive_cmd
    assert "vigil-sync@100.1.2.3:/mnt/pool/vigil-archive" in archive_cmd


def test_nas_sync_deletes_age_files_after_successful_rsync(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path)
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True)
    age_file = archive_dir / "frame.jpg.age"
    age_file.write_bytes(b"encrypted")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0)

    run_nas_sync(config, _run=fake_run)

    assert not age_file.exists(), ".age files must be deleted after successful rsync"


def test_nas_sync_does_not_delete_age_files_on_rsync_failure(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path)
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True)
    age_file = archive_dir / "frame.jpg.age"
    age_file.write_bytes(b"encrypted")

    def fake_run_fails(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stderr=b"connection refused")

    run_nas_sync(config, _run=fake_run_fails)

    assert age_file.exists(), ".age files must NOT be deleted when rsync fails"


def test_nas_sync_rsyncs_log_and_checkin_files(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path)
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True)
    log_file = Path(config.dataset.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("{}\n", encoding="utf-8")
    checkin_file = Path(config.dataset.checkin_log_file)
    checkin_file.write_text("{}\n", encoding="utf-8")

    results = []

    def fake_run(cmd, **kwargs):
        results.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    run_nas_sync(config, _run=fake_run)

    all_args = " ".join(" ".join(r) for r in results)
    assert "log.jsonl" in all_args, "log.jsonl must be rsynced"
    assert "checkins.jsonl" in all_args, "checkins.jsonl must be rsynced"


def test_nas_sync_does_not_use_remove_source_files_for_logs(sample_config, tmp_path):
    from nas_sync import run_nas_sync

    config = _make_config(sample_config, tmp_path)
    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True)
    log_file = Path(config.dataset.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("{}\n", encoding="utf-8")
    checkin_file = Path(config.dataset.checkin_log_file)
    checkin_file.write_text("{}\n", encoding="utf-8")

    results = []

    def fake_run(cmd, **kwargs):
        results.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    run_nas_sync(config, _run=fake_run)

    log_and_checkin_calls = [r for r in results if "log.jsonl" in " ".join(r) or "checkins.jsonl" in " ".join(r)]
    for cmd in log_and_checkin_calls:
        assert "--remove-source-files" not in cmd, "log files must never use --remove-source-files"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_nas_sync.py -v
```

Expected: FAIL — `nas_sync` module does not exist.

- [ ] **Step 3: Implement `nas_sync.py`**

Create `nas_sync.py` in the project root:

```python
"""NAS sync module for vigil.

Rsyncs the encrypted archive and log files to TrueNAS over Tailscale.
Deletes .age files from the Pi only after a confirmed successful rsync.

Entry point: run_nas_sync(config)
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

from config import AppConfig

logger = logging.getLogger(__name__)


def run_nas_sync(
    config: AppConfig,
    *,
    _run: Callable = subprocess.run,
) -> None:
    """Sync encrypted archive and log files to NAS over Tailscale.

    Two-phase delete: rsync first, delete .age files only on exit code 0.
    """
    if not config.security.nas_sync_enabled:
        logger.warning("nas_sync: nas_sync_enabled is False — skipping")
        return
    if not config.security.nas_rsync_target:
        logger.warning("nas_sync: nas_rsync_target is empty — skipping")
        return

    archive_dir = Path(config.dataset.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = config.security.nas_rsync_target

    # Phase 1: rsync the archive directory
    result = _run(
        ["rsync", "-avz", str(archive_dir) + "/", target + "/"],
        capture_output=True,
    )
    if result.returncode != 0:
        logger.error(
            "nas_sync: rsync of archive dir failed (exit %d): %s",
            result.returncode,
            result.stderr.decode(errors="replace") if result.stderr else "",
        )
        return

    # Phase 2: delete synced .age files only after confirmed success
    deleted = 0
    for age_file in archive_dir.glob("*.age"):
        age_file.unlink()
        deleted += 1
        logger.debug("nas_sync: deleted synced %s", age_file.name)
    if deleted:
        logger.info("nas_sync: deleted %d synced .age files from Pi", deleted)

    # Sync log files (no deletion — metadata is kept on Pi)
    for log_path in [
        Path(config.dataset.log_file),
        Path(config.dataset.checkin_log_file),
    ]:
        if not log_path.exists():
            continue
        result = _run(
            ["rsync", "-avz", str(log_path), target + "/"],
            capture_output=True,
        )
        if result.returncode != 0:
            logger.error(
                "nas_sync: rsync of %s failed (exit %d)",
                log_path.name,
                result.returncode,
            )

    logger.info("nas_sync: sync complete to %s", target)


if __name__ == "__main__":
    import logging as _logging
    from config import load_config as _load_config

    _logging.basicConfig(level=_logging.INFO)
    run_nas_sync(_load_config())
```

- [ ] **Step 4: Run NAS sync tests — verify they pass**

```bash
python -m pytest tests/test_nas_sync.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -x -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add nas_sync.py tests/test_nas_sync.py
git commit -m "feat: implement nas_sync.py — two-phase rsync to NAS over Tailscale"
```

---

## Task 7: `/images` route — archived placeholder

**Files:**
- Modify: `web_server.py`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to the bottom of `tests/test_web_server.py`:

```python
@pytest.fixture
def archived_images_client(sample_config, tmp_path):
    """Client with images_dir, archive_dir, and archived_placeholder.jpg configured."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "archived_placeholder.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    patched_dataset = dataclasses.replace(
        sample_config.dataset,
        images_dir=str(images_dir),
        archive_dir=str(archive_dir),
        checkin_log_file=str(tmp_path / "checkins.jsonl"),
    )
    cfg = dataclasses.replace(sample_config, dataset=patched_dataset)
    app = create_app(cfg)
    app.static_folder = str(static_dir)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, images_dir, archive_dir


def test_images_route_serves_archived_placeholder_when_age_file_exists(archived_images_client):
    """GET /images/<filename> returns archived_placeholder.jpg when .age file exists."""
    client, images_dir, archive_dir = archived_images_client
    (archive_dir / "frame.jpg.age").write_bytes(b"encrypted content")
    # JPEG does not exist in images_dir (it was deleted after archiving)

    response = client.get("/images/frame.jpg")

    assert response.status_code == 200
    # archived_placeholder.jpg is b"\xff\xd8\xff\xd9"
    assert response.data == b"\xff\xd8\xff\xd9"


def test_images_route_returns_404_when_neither_jpeg_nor_age_exists(archived_images_client):
    """GET /images/<filename> returns 404 when neither JPEG nor .age file exists."""
    client, images_dir, archive_dir = archived_images_client

    response = client.get("/images/nonexistent.jpg")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_web_server.py::test_images_route_serves_archived_placeholder_when_age_file_exists tests/test_web_server.py::test_images_route_returns_404_when_neither_jpeg_nor_age_exists -v
```

Expected: first test FAIL (route returns 404 instead of 200 with placeholder).

- [ ] **Step 3: Update the `/images` route in `web_server.py`**

Find the `images` route (currently the last route in `create_app`) and replace it:

```python
    @app.route("/images/<path:filename>")
    def images(filename: str) -> Response:
        """Serve a saved frame JPEG from dataset.images_dir.

        If the JPEG is missing but a corresponding .age file exists in
        archive_dir, serves archived_placeholder.jpg instead (200).
        Falls through to 404 if neither exists.
        """
        from pathlib import Path as _Path
        from werkzeug.security import safe_join as _safe_join
        from flask import abort as _abort

        safe_jpeg = _safe_join(config.dataset.images_dir, filename)
        if safe_jpeg is not None and _Path(safe_jpeg).exists():
            return send_from_directory(config.dataset.images_dir, filename)

        safe_age = _safe_join(config.dataset.archive_dir, f"{filename}.age")
        if safe_age is not None and _Path(safe_age).exists():
            return send_from_directory(app.static_folder, "archived_placeholder.jpg")

        _abort(404)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_web_server.py -k "images" -v
```

Expected: all PASS (existing + new tests).

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -x -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add web_server.py tests/test_web_server.py
git commit -m "feat: serve archived_placeholder.jpg for encrypted frames in /images route"
```

---

## Task 8: Gallery UI — archived badge

**Files:**
- Modify: `static/dashboard.js`
- Modify: `templates/dashboard.html`

No automated tests for these — they are tested manually by smoke testing on the Pi. Review each change carefully.

- [ ] **Step 1: Update `buildCard` in `static/dashboard.js`**

Find the `buildCard` function and replace it:

```javascript
function buildCard(entry) {
  const archived = Boolean(entry.image_archived);
  const imgSrc = archived ? "/static/archived_placeholder.jpg" : `/${entry.image_path}`;
  const archivedBadge = archived
    ? '<span class="badge-archived">🔒 Archived</span>'
    : "";
  const safeClass = entry.assessment.safe ? "badge-safe" : "badge-alert";
  const safeText = entry.assessment.safe ? "✓ Safe" : "✗ Unsafe";
  const alertBadge = entry.alert_fired
    ? '<span class="badge-fired">🔔 Alert fired</span>'
    : "";
  return `
    <div class="gallery-card" data-id="${entry.timestamp}">
      <img src="${imgSrc}" alt="Frame ${formatTimestamp(entry.timestamp)}" loading="lazy">
      <div class="gallery-card-body">
        <div class="gallery-card-status">
          <span class="${safeClass}">${safeText}</span>
          <span class="badge-conf">${entry.assessment.confidence}</span>
          ${alertBadge}
          ${archivedBadge}
          <span class="badge-time">${formatTimestamp(entry.timestamp)}</span>
        </div>
        <p class="gallery-card-reason">${entry.assessment.reason}</p>
        ${renderLabelTag(entry.label)}
      </div>
    </div>`;
}
```

- [ ] **Step 2: Update `openModal` in `static/dashboard.js`**

Find `openModal` and replace it:

```javascript
function openModal(entry) {
  currentEntryId = entry.timestamp;
  const archived = Boolean(entry.image_archived);
  const imgSrc = archived ? "/static/archived_placeholder.jpg" : `/${entry.image_path}`;
  document.getElementById("modal-img").src = imgSrc;
  document.getElementById("modal-reason").textContent = entry.assessment.reason;
  const notice = document.getElementById("modal-archived-notice");
  if (notice) {
    if (archived) {
      notice.removeAttribute("hidden");
    } else {
      notice.setAttribute("hidden", "");
    }
  }
  document.getElementById("modal").removeAttribute("hidden");
}
```

- [ ] **Step 3: Add the archived notice element to `templates/dashboard.html`**

Find the modal `<div id="modal-sheet">` section and add the notice paragraph after `<img id="modal-img" ...>`:

```html
  <div id="modal" hidden>
    <div id="modal-sheet">
      <button id="modal-close" type="button">✕</button>
      <img id="modal-img" src="" alt="Frame from monitoring">
      <p id="modal-archived-notice" hidden>🔒 This image has been archived and encrypted.</p>
      <p id="modal-reason"></p>
      <div id="modal-actions">
        <button id="modal-real" type="button">✓ Real Issue</button>
        <button id="modal-false" type="button">✗ False Alarm</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 4: Commit**

```bash
git add static/dashboard.js templates/dashboard.html
git commit -m "feat: show Archived badge on gallery thumbnails and modal"
```

---

## Task 9: `archived_placeholder.jpg` static asset

**Files:**
- Create: `static/archived_placeholder.jpg`

- [ ] **Step 1: Create the placeholder image**

Run this Python one-liner to create a minimal valid gray JPEG (no external deps):

```bash
python3 -c "
import struct, zlib

# Minimal 100x100 gray JPEG using raw JFIF markers
# For a real placeholder, replace this with a proper image tool
# This creates a valid but simple JPEG placeholder
data = open('static/stream_paused.jpg', 'rb').read()
open('static/archived_placeholder.jpg', 'wb').write(data)
print('Created static/archived_placeholder.jpg from stream_paused.jpg')
print('Replace with a proper archived image when available')
"
```

This uses the existing `stream_paused.jpg` as an initial placeholder. The image can be updated later without changing any code.

- [ ] **Step 2: Verify the file exists**

```bash
ls -lh static/archived_placeholder.jpg
```

Expected: file exists with non-zero size.

- [ ] **Step 3: Commit**

```bash
git add static/archived_placeholder.jpg
git commit -m "feat: add archived_placeholder.jpg static asset"
```

---

## Task 10: Systemd units

**Files:**
- Create: `setup/systemd/archiver.service`
- Create: `setup/systemd/archiver.timer`
- Create: `setup/systemd/nas_sync.service`
- Create: `setup/systemd/nas_sync.timer`

- [ ] **Step 1: Create `setup/systemd/archiver.service`**

```ini
[Unit]
Description=Vigil dataset archiver — encrypts labeled frames older than threshold
After=network.target

[Service]
Type=oneshot
User=pi
Group=pi
WorkingDirectory=/home/pi/eldercare
ExecStart=/home/pi/eldercare/.venv/bin/python /home/pi/eldercare/archiver.py
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 2: Create `setup/systemd/archiver.timer`**

```ini
[Unit]
Description=Run vigil archiver hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Create `setup/systemd/nas_sync.service`**

```ini
[Unit]
Description=Vigil NAS sync — rsync encrypted archive to TrueNAS over Tailscale
After=network.target tailscaled.service

[Service]
Type=oneshot
User=pi
Group=pi
WorkingDirectory=/home/pi/eldercare
ExecStart=/home/pi/eldercare/.venv/bin/python /home/pi/eldercare/nas_sync.py
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 4: Create `setup/systemd/nas_sync.timer`**

```ini
[Unit]
Description=Run vigil NAS sync nightly at 03:00

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Commit**

```bash
git add setup/systemd/archiver.service setup/systemd/archiver.timer setup/systemd/nas_sync.service setup/systemd/nas_sync.timer
git commit -m "feat: add archiver and nas_sync systemd timer units"
```

---

## Task 11: `install.sh` + `INSTALL_GUIDE.md`

**Files:**
- Modify: `setup/install.sh`
- Modify: `docs/INSTALL_GUIDE.md`

- [ ] **Step 1: Update `setup/install.sh`**

Add an `install_timer` helper and the timer installation. Find the `install_service` function and add `install_timer` immediately after it:

```bash
# --- Helper: install a systemd timer (service + timer file) with path substitution ---
install_timer() {
  local name="$1"
  local service_src="$SCRIPT_DIR/systemd/${name}.service"
  local timer_src="$SCRIPT_DIR/systemd/${name}.timer"
  local service_dest="/etc/systemd/system/${name}.service"
  local timer_dest="/etc/systemd/system/${name}.timer"

  sed \
    -e "s|User=pi|User=${SERVICE_USER}|g" \
    -e "s|Group=pi|Group=${SERVICE_USER}|g" \
    -e "s|/home/pi/eldercare/.venv/bin/python|${VENV_PYTHON}|g" \
    -e "s|/home/pi/eldercare|${PROJECT_DIR}|g" \
    "$service_src" > "$service_dest"

  cp "$timer_src" "$timer_dest"

  systemctl daemon-reload
  systemctl enable "${name}.timer"
  systemctl start "${name}.timer"
  echo "Installed and started ${name}.timer"
}
```

Add `age` installation before the systemd services block:

```bash
# --- age encryption tool --------------------------------------------------------
if ! command -v age &>/dev/null; then
  echo "Installing age encryption tool..."
  sudo apt-get install -y age
fi
```

Add timer installation at the end of the systemd section (after the existing `install_service` calls):

```bash
install_timer archiver
install_timer nas_sync
```

- [ ] **Step 2: Append the NAS setup section to `docs/INSTALL_GUIDE.md`**

Add the following section to the end of `docs/INSTALL_GUIDE.md`:

```markdown
## Dataset Encryption and NAS Sync Setup

This section configures `age` encryption for archived frames and nightly rsync to TrueNAS.

### 1. Generate an age key pair

Run this on your **builder machine** (not the Pi):

```bash
age-keygen -o ~/vigil-key.txt
```

This writes a key file containing two lines:
```
# created: ...
# public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AGE-SECRET-KEY-1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Keep `~/vigil-key.txt` off the Pi.** Only the public key goes on the Pi.

### 2. Copy the public key to config.yaml

Copy the `public key:` line value (starts with `age1`) into `config.yaml` on the Pi:

```yaml
security:
  age_public_key: "age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 3. Create a `vigil-sync` user on TrueNAS

In TrueNAS → Credentials → Local Users, create a user named `vigil-sync` with:
- Shell: `/bin/sh`
- Home directory: `/mnt/pool/vigil-archive` (or your chosen dataset path)
- Appropriate dataset permissions (read/write on the archive dataset only)

### 4. Generate an SSH key on the Pi

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/vigil_nas
```

### 5. Authorize the Pi's key on TrueNAS

```bash
ssh-copy-id -i ~/.ssh/vigil_nas.pub vigil-sync@<tailscale-ip>
```

Replace `<tailscale-ip>` with the TrueNAS Tailscale IP (visible in the Tailscale admin console).

Test the connection:

```bash
ssh -i ~/.ssh/vigil_nas vigil-sync@<tailscale-ip> echo ok
```

Expected: `ok`

### 5b. Add an SSH config entry

This ensures rsync uses the correct key (the Pi may have multiple SSH keys; without this entry, rsync picks one arbitrarily):

```bash
cat >> ~/.ssh/config <<'EOF'

Host vigil-nas
    HostName <tailscale-ip>
    User vigil-sync
    IdentityFile ~/.ssh/vigil_nas
EOF
```

Verify the alias works:

```bash
ssh vigil-nas echo ok
```

Expected: `ok`

### 6. Configure NAS sync in config.yaml

```yaml
security:
  nas_sync_enabled: true
  nas_rsync_target: "vigil-nas:/mnt/pool/vigil-archive"
```

### 7. Test with a dry-run

```bash
rsync -avz --dry-run dataset/archive/ vigil-nas:/mnt/pool/vigil-archive/
```

Expected: rsync output showing files that would be transferred (no actual transfer).

### 8. Verify timers are running

```bash
systemctl list-timers archiver.timer nas_sync.timer
```

Expected: both timers listed with next trigger times.

### Security notes

- The `age` public key in `config.yaml` can only encrypt, not decrypt. It is safe to store there.
- A stolen Pi contains only encrypted `.age` blobs — unreadable without the private key at `~/vigil-key.txt`.
- The Pi should be kept physically secured during the 24-hour active window when frames are still unencrypted.
- All rsync traffic travels over the Tailscale encrypted tunnel — no additional firewall rules required.
```

- [ ] **Step 3: Commit**

```bash
git add setup/install.sh docs/INSTALL_GUIDE.md
git commit -m "feat: install.sh support for archiver/nas_sync timers + INSTALL_GUIDE encryption section"
```

---

## Final: Run complete test suite

- [ ] **Run all tests**

```bash
python -m pytest -v
```

Expected: all tests PASS with no warnings about missing fields or deprecated APIs.

- [ ] **Update CLAUDE.md tree** — add new files

In `vigil/CLAUDE.md`, update the Tree section to include:
- `archiver.py`
- `nas_sync.py`
- `static/archived_placeholder.jpg`
- `setup/systemd/archiver.service`
- `setup/systemd/archiver.timer`
- `setup/systemd/nas_sync.service`
- `setup/systemd/nas_sync.timer`
- `tests/test_archiver.py`
- `tests/test_nas_sync.py`
- `tests/test_config.py`
- `docs/superpowers/plans/2026-04-12-dataset-encryption-archival.md`

- [ ] **Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md tree for Milestone 5 new files"
```
