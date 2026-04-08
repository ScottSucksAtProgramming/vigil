# Config Schema and Loader Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `config.yaml.example` (committed schema template), `config.py` (typed frozen-dataclass loader), `tests/test_config.py` (11-test suite), `.gitignore`, and a `setup/install.sh` config-copy step.

**Architecture:** All runtime settings live in a gitignored `config.yaml`. The committed `config.yaml.example` is the source-of-truth schema template. `load_config(path)` reads the YAML and returns a tree of nested `@dataclass(frozen=True)` objects. All other modules receive an `AppConfig` as a constructor dependency — config is never re-read mid-run and never accessed via a global.

**Optional section handling:** `_build_section(raw, section_key, cls)` always does `raw.get(section_key, {}) or {}` internally — if a section is absent from the YAML, it returns the dataclass with all default values. `load_config` calls `_build_section` for every optional section unconditionally; missing sections silently produce defaults, not errors.

**Secret validation failure:** `load_config` raises `ValueError("Missing required config keys: <comma-separated names>")` after full `AppConfig` construction if any of the three required secrets are empty strings. All missing secrets are reported in a single raise, not one at a time.

**Tech Stack:** Python 3.11+ (Raspberry Pi OS Bookworm), stdlib (`dataclasses`, `logging`, `typing.get_type_hints`), `pyyaml`, `pytest`

---

## Chunk 1: Infrastructure and Dataclasses

### Task 1: Bootstrap files

**Files:**
- Create: `.gitignore`
- Create: `setup/install.sh`
- Modify: `CLAUDE.md` (tree section)

- [ ] **Step 1: Create `.gitignore`**

```
# Real config (contains secrets — never commit)
config.yaml

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
*.egg-info/

# macOS
.DS_Store

# Dataset runtime data (large; Pi-local only)
dataset/images/
dataset/log.jsonl
dataset/checkins.jsonl
```

- [ ] **Step 2: Create `setup/install.sh`**

`setup/install.sh` does not exist yet. Create it with the config copy step as the first action, followed by a placeholder for future steps:

```bash
#!/usr/bin/env bash
# grandma-watcher full system setup for Raspberry Pi 5 (Raspberry Pi OS Lite 64-bit)
# Run as root or with sudo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# --- Config bootstrap -----------------------------------------------------------
# Copy config template if config.yaml does not exist.
# Fill in API keys in config.yaml before starting any service.
if [ ! -f config.yaml ]; then
  cp config.yaml.example config.yaml
  echo "Created config.yaml from config.yaml.example — fill in API keys before running."
fi

# --- TODO: remaining setup steps (systemd, go2rtc, apcupsd, etc.) ---------------
echo "Setup complete."
```

Make it executable:

```bash
chmod +x setup/install.sh
```

- [ ] **Step 3: Update `CLAUDE.md` tree**

In the `CLAUDE.md` tree block, add:
- `config.py` (after `config.yaml`)
- `.gitignore` (at top level)
- `tests/fixtures/` subfolder under `tests/`

- [ ] **Step 4: Commit**

```bash
git add .gitignore setup/install.sh CLAUDE.md
git commit -m "chore: add .gitignore, setup/install.sh skeleton with config copy step"
```

Expected: commit succeeds; `config.yaml` does not appear in `git status`.

---

### Task 2: `config.yaml.example`

**Files:**
- Create: `config.yaml.example`

- [ ] **Step 1: Create `config.yaml.example`**

```yaml
# grandma-watcher configuration
# Copy this file to config.yaml and fill in your API keys before running.
# config.yaml is gitignored — never commit real secrets.

# --- API Configuration ----------------------------------------------------------
api:
  # Active provider: openrouter | hyperbolic | anthropic
  provider: "openrouter"

  # Model to use for safety assessment
  model: "qwen/qwen3-vl-32b-instruct"

  # OpenRouter API key — get at https://openrouter.ai/keys
  openrouter_api_key: ""

  # Hyperbolic API key — used as fallback provider
  # Get at https://app.hyperbolic.xyz/settings
  hyperbolic_api_key: ""

  # Anthropic API key — reserved for future use
  anthropic_api_key: ""

  # HTTP connection timeout (seconds)
  timeout_connect_seconds: 10

  # HTTP read timeout (seconds)
  timeout_read_seconds: 30

  # Fallback provider when primary fails consecutively
  fallback_provider: "hyperbolic"
  fallback_model: "qwen/qwen2.5-vl-72b-instruct"

  # Switch to fallback after this many consecutive failures (~2.5 min at 30s intervals)
  consecutive_failure_threshold: 5

# --- Monitoring -----------------------------------------------------------------
monitor:
  # Seconds between safety assessments
  interval_seconds: 30

  # Camera snapshot resolution (must match go2rtc output)
  image_width: 960
  image_height: 540

  # Default alert silence duration in minutes (monitoring continues during silence)
  silence_duration_minutes: 30

# --- Healthchecks.io ------------------------------------------------------------
# Silent system health monitoring. Both URLs are separate Healthchecks.io checks.
# Leave blank to disable. See PRD §5.2 for details.
healthchecks:
  # Pinged by monitor.py each cycle — detects application-level failure
  app_ping_url: ""

  # Pinged by cron every 5 min — detects OS/Pi-level failure
  system_ping_url: ""

  # Minutes of missed app pings before Mom is alerted directly (builder is always first)
  sustained_outage_minutes: 30

  # Mom's Pushover user key for sustained outage alerts (optional)
  mom_pushover_user_key: ""

# --- Alerts ---------------------------------------------------------------------
alerts:
  # Pushover application API key — get at https://pushover.net/apps
  pushover_api_key: ""

  # Mom's Pushover user key — get at https://pushover.net (her account)
  pushover_user_key: ""

  # Builder's Pushover user key — for system health alerts (optional)
  pushover_builder_user_key: ""

  # Minutes between same-type alerts (medium confidence). High confidence: no cooldown.
  cooldown_minutes: 5

  # Sliding window size for medium/low confidence counters
  window_size: 5

  # N-of-window medium-unsafe frames that trigger a Pushover alert
  medium_unsafe_window_threshold: 2

  # N-of-window low-confidence frames that trigger a soft Pushover alert
  low_unsafe_window_threshold: 3

  # Minutes between soft low-confidence alerts
  low_confidence_cooldown_minutes: 60

  # ⚠ Alert escalation: behavior undecided — discuss with Mom before enabling.
  # See PRD §6.4 for open question.
  # escalation:
  #   enabled: false
  #   no_response_minutes: 15
  #   escalate_to_builder: true

# --- Dataset --------------------------------------------------------------------
dataset:
  # Absolute path to dataset root on the Pi
  base_dir: "/home/pi/eldercare/dataset"

  # Sub-paths are derived from base_dir if left blank
  images_dir: ""        # defaults to <base_dir>/images
  log_file: ""          # defaults to <base_dir>/log.jsonl
  checkin_log_file: ""  # defaults to <base_dir>/checkins.jsonl

  # Warn when dataset disk usage exceeds this (GB)
  max_disk_gb: 50

  retention:
    # Alert-triggering frames: keep forever (fine-tuning value)
    alert_frames: "forever"

    # Medium/low confidence frames (days)
    uncertain_frames_days: 30

    # 1-in-20 random safe frames kept as negative training examples (days)
    safe_sample_frames_days: 30

    # All other safe frames (days)
    safe_unsample_frames_days: 7

# --- Streaming (go2rtc) ---------------------------------------------------------
# Camera source and stream config live in go2rtc.yaml — not here.
stream:
  # go2rtc HTTP API port
  go2rtc_api_port: 1984

  # Snapshot URL used by monitor.py to fetch frames from go2rtc
  snapshot_url: "http://localhost:1984/api/frame.jpeg?src=grandma"

  # Stream name as defined in go2rtc.yaml
  stream_name: "grandma"

# --- Web Dashboard --------------------------------------------------------------
web:
  # Flask port for the dashboard
  port: 8080

  # Max frames shown in the gallery
  gallery_max_items: 50

# --- Cloudflare Tunnel ----------------------------------------------------------
# Auth is handled by Cloudflare Access + Google OAuth (configured in Cloudflare dashboard).
cloudflare:
  tunnel_token: ""

# --- Tailscale ------------------------------------------------------------------
tailscale:
  # Set to false if Tailscale is not installed (disables the /talk audio route)
  enabled: true

# --- Sensors (Phase 2 — all disabled by default) --------------------------------
sensors:
  load_cells:
    enabled: false
    node_url: "http://loadcells.local:5000/sensors"
    poll_interval_seconds: 5
  vitals:
    enabled: false
    node_url: "http://vitals.local:5000/sensors"
    poll_interval_seconds: 5

# --- Audio ----------------------------------------------------------------------
audio:
  # Play a chime before Mom's voice comes through (prevents startling grandma)
  chime_before_talk: true

  # Path to chime audio file, relative to project WorkingDirectory
  # WorkingDirectory is set in setup/systemd/monitor.service
  chime_file: "static/chime.mp3"
```

- [ ] **Step 2: Verify gitignore behavior**

```bash
git check-ignore -v config.yaml config.yaml.example
```

Expected: `config.yaml` is ignored; `config.yaml.example` produces no output (not ignored).

- [ ] **Step 3: Commit**

```bash
git add config.yaml.example
git commit -m "feat: add config.yaml.example with full PRD §10 schema and comments"
```

---

### Task 3: Config dataclasses

**Files:**
- Create: `config.py` (dataclasses only — no loader yet)
- Create: `tests/test_config.py` (import smoke test only)

- [ ] **Step 1: Write the failing import test**

Create `tests/test_config.py` with **only the dataclass imports** — builders and `load_config` are not added until Tasks 4 and 5:

```python
"""Tests for config.py — loader and dataclasses."""

import dataclasses
import logging
from pathlib import Path

import pytest
import yaml

from config import (
    AlertsConfig,
    ApiConfig,
    AppConfig,
    AudioConfig,
    CloudflareConfig,
    DatasetConfig,
    HealthchecksConfig,
    MonitorConfig,
    RetentionConfig,
    SensorNodeConfig,
    SensorsConfig,
    StreamConfig,
    TailscaleConfig,
    WebConfig,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_FIXTURE = FIXTURES_DIR / "config_valid.yaml"
EXAMPLE_FILE = Path(__file__).parent.parent / "config.yaml.example"

# Minimal valid config dict used as a base for edge-case tests.
# Modify specific keys in tests rather than duplicating the whole dict.
_MINIMAL_RAW: dict = {
    "api": {
        "provider": "openrouter",
        "model": "qwen/qwen3-vl-32b-instruct",
        "openrouter_api_key": "test-key-openrouter",
        "fallback_provider": "hyperbolic",
        "fallback_model": "qwen/qwen2.5-vl-72b-instruct",
        "consecutive_failure_threshold": 5,
    },
    "monitor": {"interval_seconds": 30},
    "alerts": {
        "pushover_api_key": "test-key-pushover-app",
        "pushover_user_key": "test-key-pushover-mom",
    },
}


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a dict as YAML to a temp config.yaml and return the path."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return p


def test_appconfig_dataclass_fields():
    """AppConfig has exactly the expected required and optional fields."""
    required = {"api", "monitor", "alerts"}
    optional = {
        "healthchecks", "dataset", "stream", "web",
        "cloudflare", "tailscale", "sensors", "audio",
    }
    field_names = {f.name for f in dataclasses.fields(AppConfig)}
    assert field_names == required | optional
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/test_config.py::test_appconfig_dataclass_fields -v
```

Expected: `ImportError: cannot import name 'AppConfig' from 'config'`

- [ ] **Step 3: Create `config.py` with all dataclasses**

```python
"""Typed configuration dataclasses for grandma-watcher.

Loaded once at startup by load_config() and passed as a dependency.
Never re-read mid-run, never accessed via a global.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, get_type_hints

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionConfig:
    alert_frames: str = "forever"
    uncertain_frames_days: int = 30
    safe_sample_frames_days: int = 30
    safe_unsample_frames_days: int = 7


@dataclass(frozen=True)
class DatasetConfig:
    base_dir: str = "/home/pi/eldercare/dataset"
    images_dir: str = ""        # derived from base_dir by _build_dataset if empty
    log_file: str = ""          # derived from base_dir by _build_dataset if empty
    checkin_log_file: str = ""  # derived from base_dir by _build_dataset if empty
    max_disk_gb: int = 50
    retention: RetentionConfig = field(default_factory=RetentionConfig)


@dataclass(frozen=True)
class SensorNodeConfig:
    enabled: bool = False
    node_url: str = ""
    poll_interval_seconds: int = 5


@dataclass(frozen=True)
class SensorsConfig:
    load_cells: SensorNodeConfig = field(default_factory=SensorNodeConfig)
    vitals: SensorNodeConfig = field(default_factory=SensorNodeConfig)


@dataclass(frozen=True)
class ApiConfig:
    provider: str = "openrouter"
    model: str = "qwen/qwen3-vl-32b-instruct"
    openrouter_api_key: str = ""
    hyperbolic_api_key: str = ""
    anthropic_api_key: str = ""
    timeout_connect_seconds: int = 10
    timeout_read_seconds: int = 30
    fallback_provider: str = "hyperbolic"
    fallback_model: str = "qwen/qwen2.5-vl-72b-instruct"
    consecutive_failure_threshold: int = 5


@dataclass(frozen=True)
class MonitorConfig:
    interval_seconds: int = 30
    image_width: int = 960
    image_height: int = 540
    silence_duration_minutes: int = 30


@dataclass(frozen=True)
class HealthchecksConfig:
    app_ping_url: str = ""
    system_ping_url: str = ""
    sustained_outage_minutes: int = 30
    mom_pushover_user_key: str = ""


@dataclass(frozen=True)
class AlertsConfig:
    pushover_api_key: str = ""
    pushover_user_key: str = ""
    pushover_builder_user_key: str = ""
    cooldown_minutes: int = 5
    window_size: int = 5
    medium_unsafe_window_threshold: int = 2
    low_unsafe_window_threshold: int = 3
    low_confidence_cooldown_minutes: int = 60


@dataclass(frozen=True)
class StreamConfig:
    go2rtc_api_port: int = 1984
    snapshot_url: str = "http://localhost:1984/api/frame.jpeg?src=grandma"
    stream_name: str = "grandma"


@dataclass(frozen=True)
class WebConfig:
    port: int = 8080
    gallery_max_items: int = 50


@dataclass(frozen=True)
class CloudflareConfig:
    tunnel_token: str = ""


@dataclass(frozen=True)
class TailscaleConfig:
    enabled: bool = True


@dataclass(frozen=True)
class AudioConfig:
    chime_before_talk: bool = True
    chime_file: str = "static/chime.mp3"  # relative to project WorkingDirectory


@dataclass(frozen=True)
class AppConfig:
    # Required sections — must be present in config.yaml
    api: ApiConfig
    monitor: MonitorConfig
    alerts: AlertsConfig
    # Optional sections — sensible defaults if omitted
    healthchecks: HealthchecksConfig = field(default_factory=HealthchecksConfig)
    dataset: DatasetConfig = field(default_factory=DatasetConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    web: WebConfig = field(default_factory=WebConfig)
    cloudflare: CloudflareConfig = field(default_factory=CloudflareConfig)
    tailscale: TailscaleConfig = field(default_factory=TailscaleConfig)
    sensors: SensorsConfig = field(default_factory=SensorsConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_config.py::test_appconfig_dataclass_fields -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add config dataclasses and import smoke test"
```

---

## Chunk 2: Builder Functions

### Task 4: `_build_section`, `_build_dataset`, `_build_sensors` (TDD)

**Files:**
- Create: `tests/fixtures/` (directory)
- Create: `tests/fixtures/config_valid.yaml`
- Modify: `tests/test_config.py` (add 4 builder tests)
- Modify: `config.py` (add 3 builder functions)

- [ ] **Step 1: Extend imports in `tests/test_config.py` for builder helpers**

Add the builder imports to the existing `from config import (...)` block:

```python
from config import (
    AlertsConfig,
    ApiConfig,
    AppConfig,
    AudioConfig,
    CloudflareConfig,
    DatasetConfig,
    HealthchecksConfig,
    MonitorConfig,
    RetentionConfig,
    SensorNodeConfig,
    SensorsConfig,
    StreamConfig,
    TailscaleConfig,
    WebConfig,
    _build_dataset,       # add
    _build_section,       # add
    _build_sensors,       # add
)
```

- [ ] **Step 2: Write 4 failing builder tests**

Append to `tests/test_config.py`:

```python
def test_example_file_structurally_valid():
    """config.yaml.example must construct each section without raising."""
    with open(EXAMPLE_FILE) as f:
        raw = yaml.safe_load(f)
    # Call builders directly — bypasses secret validation (example has blank keys by design)
    _build_section(raw, "api", ApiConfig)
    _build_section(raw, "monitor", MonitorConfig)
    _build_section(raw, "alerts", AlertsConfig)
    _build_dataset(raw)
    _build_sensors(raw)


def test_quoted_numeric_coercion():
    """A quoted integer in YAML (e.g. "45") is cast to int correctly."""
    raw = {"monitor": {"interval_seconds": "45"}}
    result = _build_section(raw, "monitor", MonitorConfig)
    assert result.interval_seconds == 45
    assert isinstance(result.interval_seconds, int)


def test_int_cast_failure_raises():
    """A non-numeric value for an int field raises ValueError naming the field."""
    raw = {"monitor": {"interval_seconds": "not_a_number"}}
    with pytest.raises(ValueError, match="monitor.interval_seconds"):
        _build_section(raw, "monitor", MonitorConfig)


def test_sensor_defaults_from_builder():
    """Calling _build_sensors with no sensors key produces disabled-by-default nodes."""
    result = _build_sensors({})
    assert result.load_cells.enabled is False
    assert result.vitals.enabled is False
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/test_config.py -k "example_file or coercion or cast_failure or sensor_defaults" -v
```

Expected: 4 failures — `ImportError` on `_build_section`, `_build_dataset`, `_build_sensors`

- [ ] **Step 4: Create the fixtures directory and `config_valid.yaml`**

```bash
mkdir -p tests/fixtures
```

Create `tests/fixtures/config_valid.yaml`:

```yaml
# Minimal valid fixture — required sections only, fake non-empty secrets.
# Optional sections are intentionally omitted to exercise defaults.
api:
  provider: "openrouter"
  model: "qwen/qwen3-vl-32b-instruct"
  openrouter_api_key: "test-key-openrouter"
  hyperbolic_api_key: ""
  anthropic_api_key: ""
  timeout_connect_seconds: 10
  timeout_read_seconds: 30
  fallback_provider: "hyperbolic"
  fallback_model: "qwen/qwen2.5-vl-72b-instruct"
  consecutive_failure_threshold: 5

monitor:
  interval_seconds: 30
  image_width: 960
  image_height: 540
  silence_duration_minutes: 30

alerts:
  pushover_api_key: "test-key-pushover-app"
  pushover_user_key: "test-key-pushover-mom"
  pushover_builder_user_key: ""
  cooldown_minutes: 5
  window_size: 5
  medium_unsafe_window_threshold: 2
  low_unsafe_window_threshold: 3
  low_confidence_cooldown_minutes: 60
```

- [ ] **Step 5: Add builder functions to `config.py`**

Add these after the `AppConfig` dataclass definition:

```python
# ---------------------------------------------------------------------------
# Private builder helpers
# ---------------------------------------------------------------------------

_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "api", "monitor", "alerts", "healthchecks", "dataset",
    "stream", "web", "cloudflare", "tailscale", "sensors", "audio",
})


def _build_section(raw: dict[str, Any], section_key: str, cls: type) -> Any:
    """Construct a frozen dataclass from a YAML section dict.

    Introspects field type hints to cast int/float values.
    Silently ignores unrecognized keys within the section (forward compatibility).
    Raises ValueError on bad type casts, naming the offending field.
    """
    section_raw = raw.get(section_key, {}) or {}
    hints = get_type_hints(cls)
    field_names = {f.name for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}

    for key, val in section_raw.items():
        if key not in field_names:
            continue  # silently ignore unrecognized keys
        hint = hints.get(key)
        if hint in (int, float):
            try:
                kwargs[key] = hint(val)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Config key {section_key}.{key} must be {hint.__name__}, got: {val!r}"
                )
        else:
            kwargs[key] = val

    return cls(**kwargs)


def _build_dataset(raw: dict[str, Any]) -> DatasetConfig:
    """Build DatasetConfig, deriving sub-paths from base_dir when not specified."""
    section = raw.get("dataset", {}) or {}
    base_dir = str(section.get("base_dir") or "/home/pi/eldercare/dataset")
    images_dir = str(section.get("images_dir") or f"{base_dir}/images")
    log_file = str(section.get("log_file") or f"{base_dir}/log.jsonl")
    checkin_log_file = str(section.get("checkin_log_file") or f"{base_dir}/checkins.jsonl")
    max_disk_gb = int(section.get("max_disk_gb", 50))
    retention_raw = section.get("retention", {}) or {}
    retention = _build_section({"retention": retention_raw}, "retention", RetentionConfig)
    return DatasetConfig(
        base_dir=base_dir,
        images_dir=images_dir,
        log_file=log_file,
        checkin_log_file=checkin_log_file,
        max_disk_gb=max_disk_gb,
        retention=retention,
    )


def _build_sensors(raw: dict[str, Any]) -> SensorsConfig:
    """Build SensorsConfig with nested SensorNodeConfig instances."""
    section = raw.get("sensors", {}) or {}
    load_cells_raw = section.get("load_cells", {}) or {}
    vitals_raw = section.get("vitals", {}) or {}
    return SensorsConfig(
        load_cells=_build_section({"load_cells": load_cells_raw}, "load_cells", SensorNodeConfig),
        vitals=_build_section({"vitals": vitals_raw}, "vitals", SensorNodeConfig),
    )
```

- [ ] **Step 6: Run the 4 builder tests to verify they pass**

```bash
pytest tests/test_config.py -k "example_file or coercion or cast_failure or sensor_defaults" -v
```

Expected: 4 PASS

- [ ] **Step 7: Run all tests so far**

```bash
pytest tests/test_config.py -v
```

Expected: 5 tests pass. Remaining tests fail with `ImportError` on `load_config` — that is expected.

- [ ] **Step 8: Commit**

```bash
git add config.py tests/test_config.py tests/fixtures/config_valid.yaml
git commit -m "feat: add config builder helpers with tests"
```

---

## Chunk 3: `load_config()` and Remaining Tests

### Task 5: `load_config()` (TDD)

**Files:**
- Modify: `config.py` (add `load_config` and `_REQUIRED_SECRETS`)
- Modify: `tests/test_config.py` (add 7 `load_config` tests)

- [ ] **Step 1: Extend imports in `tests/test_config.py` for `load_config`**

Add `load_config` to the existing `from config import (...)` block:

```python
from config import (
    AlertsConfig,
    ApiConfig,
    AppConfig,
    AudioConfig,
    CloudflareConfig,
    DatasetConfig,
    HealthchecksConfig,
    MonitorConfig,
    RetentionConfig,
    SensorNodeConfig,
    SensorsConfig,
    StreamConfig,
    TailscaleConfig,
    WebConfig,
    _build_dataset,
    _build_section,
    _build_sensors,
    load_config,   # add
)
```

- [ ] **Step 2: Write 7 failing `load_config` tests**

Append to `tests/test_config.py`:

```python
def test_load_valid_config():
    config = load_config(str(VALID_FIXTURE))
    assert isinstance(config, AppConfig)
    assert config.api.provider == "openrouter"
    assert config.monitor.interval_seconds == 30
    assert config.alerts.pushover_api_key == "test-key-pushover-app"


def test_missing_required_secret_raises(tmp_path):
    data = {**_MINIMAL_RAW, "api": {**_MINIMAL_RAW["api"], "openrouter_api_key": ""}}
    p = _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="api.openrouter_api_key"):
        load_config(str(p))


def test_missing_multiple_secrets_reports_all(tmp_path):
    data = {
        **_MINIMAL_RAW,
        "api": {**_MINIMAL_RAW["api"], "openrouter_api_key": ""},
        "alerts": {"pushover_api_key": "", "pushover_user_key": ""},
    }
    p = _write_config(tmp_path, data)
    with pytest.raises(ValueError) as exc_info:
        load_config(str(p))
    msg = str(exc_info.value)
    assert "api.openrouter_api_key" in msg
    assert "alerts.pushover_api_key" in msg
    assert "alerts.pushover_user_key" in msg


def test_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_invalid_yaml_raises(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("key: [\nbroken yaml")
    with pytest.raises(yaml.YAMLError):
        load_config(str(p))


def test_unknown_keys_warn(tmp_path, caplog):
    data = {**_MINIMAL_RAW, "unknown_section": {"foo": "bar"}}
    p = _write_config(tmp_path, data)
    with caplog.at_level(logging.WARNING, logger="config"):
        load_config(str(p))
    assert any("unknown_section" in record.message for record in caplog.records)


def test_missing_required_section_raises(tmp_path):
    data = {k: v for k, v in _MINIMAL_RAW.items() if k != "alerts"}
    p = _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="alerts"):
        load_config(str(p))
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/test_config.py -k "load_valid or missing_required or file_not or invalid_yaml or unknown_keys or required_section" -v
```

Expected: 7 failures — `ImportError` on `load_config`

- [ ] **Step 4: Add `load_config()` to `config.py`**

Append after the builder helpers:

```python
# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = ("api", "monitor", "alerts")

_REQUIRED_SECRETS: list[tuple[str, Any]] = [
    ("api.openrouter_api_key", lambda c: c.api.openrouter_api_key),
    ("alerts.pushover_api_key", lambda c: c.alerts.pushover_api_key),
    ("alerts.pushover_user_key", lambda c: c.alerts.pushover_user_key),
]


def load_config(path: str = "config.yaml") -> AppConfig:
    """Load and validate configuration from a YAML file.

    Raises FileNotFoundError if path does not exist.
    Raises yaml.YAMLError if the file is not valid YAML.
    Raises ValueError if required sections, secrets, or field types are invalid.
    """
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    for key in raw:
        if key not in _KNOWN_TOP_LEVEL_KEYS:
            logger.warning("Unknown config key: %s", key)

    for section in _REQUIRED_SECTIONS:
        if section not in raw:
            raise ValueError(f"Missing required config section: {section}")

    config = AppConfig(
        api=_build_section(raw, "api", ApiConfig),
        monitor=_build_section(raw, "monitor", MonitorConfig),
        alerts=_build_section(raw, "alerts", AlertsConfig),
        healthchecks=_build_section(raw, "healthchecks", HealthchecksConfig),
        dataset=_build_dataset(raw),
        stream=_build_section(raw, "stream", StreamConfig),
        web=_build_section(raw, "web", WebConfig),
        cloudflare=_build_section(raw, "cloudflare", CloudflareConfig),
        tailscale=_build_section(raw, "tailscale", TailscaleConfig),
        sensors=_build_sensors(raw),
        audio=_build_section(raw, "audio", AudioConfig),
    )

    missing = [name for name, getter in _REQUIRED_SECRETS if not getter(config)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    return config
```

- [ ] **Step 5: Run the 7 new tests to verify they pass**

```bash
pytest tests/test_config.py -k "load_valid or missing_required or file_not or invalid_yaml or unknown_keys or required_section" -v
```

Expected: 7 PASS

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/test_config.py -v
```

Expected: all 12 tests pass (1 import smoke test + 4 builder tests + 7 loader tests)

- [ ] **Step 7: Run ruff and black**

```bash
ruff check config.py tests/test_config.py && black --check config.py tests/test_config.py
```

Fix any issues before committing. Common ruff fixes: add type annotations to lambdas in `_REQUIRED_SECRETS`, ensure `Any` is imported. Common black fixes: line length.

- [ ] **Step 8: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add load_config() with full 12-test suite"
```

- [ ] **Step 9: Final gate — full test suite**

```bash
pytest -v
```

Expected: all tests green (including `tests/test_models.py` and `tests/test_protocols.py` from prior work).

```bash
ruff check . && black --check .
```

Expected: no issues.
