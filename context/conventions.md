---
title: "vigil Conventions"
summary: "File naming, dataset schema, config patterns, and coding conventions for the eldercare monitor"
created: 2026-04-07
updated: 2026-04-07
---

# vigil Conventions

## What Belongs Here

- Python application code for the Pi 5 hub (monitoring, alerting, streaming, dashboard)
- Config and setup scripts for Pi 5 deployment
- Web dashboard templates and static assets
- Dataset images and inference logs
- Phase 2 sensor node code (when built)
- Documentation for Mom and the builder

## What Does NOT Belong Here

- Obsidian notes and non-code planning docs → `~/Documents/1_projects/`
- Sensor node code for Pi Zero 2W devices → give each node its own subfolder under `setup/` when built
- Cloud-stored video footage — all footage stays local per PRD §3.2

## File Naming

- Dataset images: `dataset/images/YYYY-MM-DD_HH-MM-SS.jpg` (UTC timestamp, matching log entry)
- Log entries: `dataset/log.jsonl` — append-only, one JSON object per line (schema in PRD §11.1)
- Config: always `config.yaml`, never `.env` for secrets (Pi is a controlled device)

## Config Patterns

- All runtime settings go in `config.yaml`. No hardcoded values in application code.
- Sensor feature flags (`sensors.load_cells.enabled`, `sensors.vitals.enabled`) default to `false`. Gate all sensor code on these flags.
- API provider switching is done via `api.provider` in config — code must support `openrouter`, `hyperbolic`, and `anthropic` as values. Together AI is not supported (no serverless VLM endpoint).

## Alert Logic

Follow the decision matrix in `PRD.md` §6.3 exactly:
- `safe: false` + `high` confidence → immediate alert
- `safe: false` + `medium` confidence → alert only after 2 consecutive frames
- `safe: false` + `low` confidence → log only
- Minimum 5-minute cooldown between same-type alerts

Do not adjust thresholds without testing against the dataset. Alert fatigue destroys trust with Mom.

## Dataset Schema

Every inference writes one line to `dataset/log.jsonl`. Required fields (see PRD §11.1):
- `timestamp` (ISO 8601, UTC)
- `image_path`
- `provider`, `model`, `prompt_version`
- `sensor_snapshot`
- `response_raw`, `safe`, `confidence`, `reason`, `sensor_notes`
- `alert_fired` (bool)
- `api_latency_ms`
- `label` (null until reviewed; values: `"correct"`, `"false_positive"`, `"false_negative"`)

## Python Conventions

- Use `pyyaml` to load `config.yaml` at startup; pass config dict through to modules — no global state.
- Camera frames are fetched via `requests.get(config.stream.snapshot_url)` — never import `picamera2` or `cv2`. go2rtc owns the camera.
- Flask routes in `web_server.py`; no business logic in route handlers — delegate to modules.
- All API calls in `monitor.py` should catch exceptions and follow the retry/failure logic in PRD §6.3.
- Config is loaded **once at startup**, optionally parsed into a typed dataclass, and passed down as a dependency — never re-read mid-run, never accessed via a global.
- Type hints on all function signatures. One-line docstrings on all public module-level functions.
- No circular imports. Module dependency direction: `monitor → alert, prompt_builder, dataset, sensors`.
- Functions do one thing. If a function needs a comment to explain what a block does, split it.

## Interface-First Design

Interfaces are the architecture of this project. Before writing any implementation, define the interface (Protocol) and the data types it exchanges. If you understand the interfaces, you understand the system — the implementation is a detail.

### The Three Extension Points

These are the stable, versioned interfaces in this codebase. New behavior is added by writing a new implementation of one of these Protocols — **not** by modifying existing code.

```python
# A VLM provider that can assess a camera frame
class VLMProvider(Protocol):
    def assess(self, frame: bytes, prompt: str) -> AssessmentResult: ...

# A channel that can deliver an alert to a caregiver
class AlertChannel(Protocol):
    def send(self, alert: Alert) -> None: ...

# A sensor node that can return a reading snapshot
class SensorNode(Protocol):
    def read(self) -> SensorSnapshot: ...
```

Current implementations: `OpenRouterProvider`, `PushoverChannel`. Phase 2 will add `SensorNode` implementations.

### Interface-First Workflow

1. Define the Protocol and the data types it uses (e.g., `AssessmentResult`, `Alert`)
2. Write tests against the Protocol using a stub/fake implementation
3. Write the concrete implementation
4. Tests pass → implementation is correct by definition

### Tests Target Interfaces, Not Internals

Tests call public Protocol methods only. If you completely rewrite a provider's internals, existing tests must still pass unchanged. A test that reaches into private methods or implementation details is a design smell — refactor the design instead.

### Stop-and-Flag Rule

If you find yourself **modifying an existing Protocol, an existing function signature, or existing tested behavior**, stop. Do not proceed silently. Surface this as a design question before making the change:

- Is the existing interface wrong, or is the new feature being designed incorrectly?
- Can the new behavior be added via a new implementation rather than a change to the existing interface?
- What existing tests will break, and is that acceptable?

Modifying an interface is an architectural decision, not a coding task. Flag it.

## Error Handling

- The monitor loop must **never crash from API or network errors** — catch at the cycle boundary, log at `WARNING`, skip the cycle, continue.
- Fail-safe on parse error: treat a malformed or unparseable VLM response as `{safe: true, confidence: "low"}`. Never alert on garbage output.
- Retry transient failures (timeouts, 5xx) up to the limit in `config.yaml`; after exhausting retries, log at `ERROR` and continue to the next cycle.
- Do not use bare `except Exception` — catch specific exception types where possible; use `except Exception as e` only at top-level cycle boundaries with full `logging.exception()` output.

## Logging

- Use Python's built-in `logging` module with **per-module named loggers**: `logger = logging.getLogger(__name__)`.
- Four levels in use:
  - `DEBUG` — detailed trace, frame-by-frame output, API payloads (verbose, off by default)
  - `INFO` — normal operation milestones (cycle complete, alert fired, stream started)
  - `WARNING` — degraded but continuing (API retry, parse warning, sensor unavailable)
  - `ERROR` — failure requiring attention (exhausted retries, config invalid, hardware error)
- Application logs go to **systemd journal** (`journald`) — no separate log file on Pi. `systemd-cat` captures stdout/stderr automatically via the service file.
- `dataset/log.jsonl` is the inference/dataset log — separate from application logs, never mixed.

## Testing

- Test runner: **pytest**. All tests live in `tests/`, with filenames mirroring source: `tests/test_monitor.py`, `tests/test_alert.py`, etc.
- **All tests must pass without Pi hardware.** Mock the camera HTTP endpoint (`requests`), OpenRouter API, and Pushover — never require a live camera or network in unit/integration tests.
- Test categories:
  - **Unit tests** — pure logic: response parser, alert decision matrix, prompt builder, config loader. Fast, no I/O.
  - **Integration tests** — module wiring with mocked external services (e.g., full monitor cycle with mocked API).
  - **Smoke test** (`smoke_test.py`) — hardware-in-loop only, run manually on the Pi.
- Alert decision logic (`alert.py`) requires **100% branch coverage** — this is the safety-critical path.
- Write the test first (TDD). If you can't write a test for it, the design is wrong.

## Code Quality

- Formatter: **black** (line length 100). Run before every commit.
- Linter: **ruff**. Zero warnings policy.
- Pre-merge gate: `ruff check . && black --check . && pytest` must all pass clean.
- Do not add code that can't be tested. If a function requires live hardware to test, extract the hardware boundary into a thin adapter and test the logic separately.

## Lessons Learned

<!-- Append dated one-liners below. -->
