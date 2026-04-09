# Design Spec: `monitor.py` Core Loop

**Date:** 2026-04-09
**Project:** grandma-watcher
**Status:** Approved
**Scope:** Create the Phase 1 monitor loop that fetches snapshots, assesses safety, decides alerts, and records dataset rows

---

## 1. Overview

`monitor.py` is the orchestration boundary for the Phase 1 monitoring path. It owns the cycle flow, but it does not reimplement logic already captured in the existing modules:

- `prompt_builder.py` builds prompt text
- `openrouter_provider.py` performs VLM assessment
- `alert.py` owns decision logic, window counting, cooldowns, and patient-location state
- `dataset.py` persists frame images and dataset rows

The monitor loop should stay thin and explicit. It coordinates dependencies, catches cycle-boundary failures, and moves to the next iteration.

**Dependency direction:** `monitor.py → config.py, prompt_builder.py, alert.py, dataset.py, protocols.py, models.py`

---

## 2. Module Shape

`monitor.py` should use focused functions, not a large class.

```python
def fetch_snapshot(config: AppConfig) -> bytes: ...
def build_sensor_snapshot(config: AppConfig) -> SensorSnapshot: ...
def build_alert(alert_type: AlertType, assessment: AssessmentResult) -> Alert: ...
def run_cycle(
    config: AppConfig,
    provider: VLMProvider,
    alert_channel: AlertChannel,
    *,
    window_counter: SlidingWindowCounter,
    medium_cooldown: CooldownTimer,
    low_cooldown: CooldownTimer,
    location_state: PatientLocationStateMachine,
) -> None: ...
def run_forever(config: AppConfig, provider: VLMProvider, alert_channel: AlertChannel) -> None: ...
def main() -> int: ...
```

`run_cycle(...)` is the main seam for unit and integration-style tests. `run_forever(...)` owns long-lived state and sleep timing. `main()` loads config, constructs the default provider/channel, and starts the loop.

---

## 3. Cycle Flow

Each cycle performs these steps in order:

1. Capture the current UTC timestamp as ISO 8601 with trailing `Z`
2. Fetch a JPEG frame from `config.stream.snapshot_url`
3. Build a `SensorSnapshot` from enabled flags in config
4. Build the prompt with `build_prompt(sensor_snapshot)`
5. Call `provider.assess(frame, prompt)`
6. Push the returned `AssessmentResult` into `SlidingWindowCounter`
7. Push the assessment into `PatientLocationStateMachine`
8. If the state machine returns `SilenceEvent.ACTIVATE`:
   - flush the sliding window
   - cancel medium and low cooldowns
9. Compute `silence_active` from `location_state.auto_silenced`
10. Call `decide_alert_type(...)` with current window counts and cooldown states
11. If an alert type is returned:
   - build an `Alert`
   - send it through the injected `AlertChannel`
   - start the corresponding cooldown for medium or low alerts
12. Record a `DatasetEntry` with the raw response fields captured from the validated assessment and write it via `record_dataset_entry(...)`

High-confidence unsafe alerts bypass silence and cooldown through existing `alert.py` behavior. `monitor.py` should not special-case that logic.

---

## 4. Alerts

### Alert messages

Use short, deterministic messages derived from `AlertType`:

- `UNSAFE_HIGH`: use the assessment reason directly
- `UNSAFE_MEDIUM`: use the assessment reason directly
- `SOFT_LOW_CONFIDENCE`: `"System uncertain — please check on grandma and label the frames."`
- `INFO` and `SYSTEM` are out of scope for this task

### Alert priority

- `UNSAFE_HIGH` → `AlertPriority.HIGH`
- `UNSAFE_MEDIUM` and `SOFT_LOW_CONFIDENCE` → `AlertPriority.NORMAL`

### Alert URL

Keep `url=""` in this task. Dashboard URL wiring belongs later when the web layer exists.

---

## 5. Dataset Logging

Each completed cycle writes one `DatasetEntry` using:

- `timestamp`: cycle timestamp
- `image_path`: derived by `record_dataset_entry(...)`
- `provider`: `config.api.provider`
- `model`: `config.api.model`
- `prompt_version`: `config.monitor.prompt_version`
- `sensor_snapshot`: built from config flags
- `response_raw`: canonical JSON string rebuilt from the validated assessment, not the provider’s original raw body
- `assessment`: validated `AssessmentResult`
- `alert_fired`: whether any alert was sent in this cycle
- `api_latency_ms`: `0.0` for now
- `silence_active`: current state after location-state processing

`api_latency_ms` remains `0.0` in this task because the current `VLMProvider` Protocol returns only `AssessmentResult`. Adding measured latency would require an interface change and is outside scope.

---

## 6. Error Handling

`fetch_snapshot(...)` should raise on request or HTTP failure.

`run_cycle(...)` may raise:

- `requests` exceptions from snapshot fetch
- provider exceptions from `assess(...)`
- filesystem exceptions from dataset persistence
- alert delivery exceptions from `alert_channel.send(...)`

`run_forever(...)` is the cycle boundary. It must catch exceptions, log them, and continue after sleeping the configured interval. This follows the project rule that the monitor loop must never crash from recoverable runtime failures.

No retry loop, provider failover, or Healthchecks pinging belongs in this task.

---

## 7. Testing Strategy

File: `tests/test_monitor.py`

Coverage for this task:

1. `fetch_snapshot(...)` uses `config.stream.snapshot_url` and returns response bytes
2. Safe cycle writes dataset row and sends no alert
3. High-confidence unsafe cycle sends an immediate alert and writes dataset row with `alert_fired=True`
4. Medium-confidence sequence fires only when the window threshold is met
5. Auto-silence activation flushes the window and suppresses medium/low alerts on subsequent cycles
6. `run_forever(...)` catches a cycle exception, logs it, sleeps, and continues

Use fakes/stubs instead of network calls:

- fake provider returning fixed `AssessmentResult`
- fake alert channel collecting alerts
- patched snapshot request returning fixture JPEG bytes
- temporary dataset paths via `tmp_path`
- patched `time.sleep` in `run_forever(...)`

---

## 8. What Not to Include

- Provider failover to Hyperbolic
- Healthchecks.io pinging
- builder-specific system alerts
- dashboard URLs in alert payloads
- CLI flags like `--dry-run`
- manual silence duration handling
- sensor-node polling beyond enabled/disabled flags

Those are separate tasks. This task is only the core orchestration loop.
