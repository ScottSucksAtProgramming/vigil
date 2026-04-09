# Monitor Core Loop Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `monitor.py` so one monitoring cycle can fetch a snapshot, assess it, decide alerts, and persist a dataset row, then run continuously without crashing on cycle failures.

**Architecture:** Use a one-cycle orchestration function plus a thin forever-loop wrapper. Keep existing logic in existing modules: `alert.py` owns decisions/state, `prompt_builder.py` builds the prompt, `dataset.py` persists rows, and `monitor.py` only coordinates them.

**Tech Stack:** Python 3.11, requests, pytest, unittest.mock, dataclasses

---

## Chunk 1: Snapshot Fetch and Test Scaffolding

### Task 1: Add failing monitor tests and basic fakes

**Files:**
- Create: `tests/test_monitor.py`
- Modify: none
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- `fetch_snapshot(...)` returns response bytes from `config.stream.snapshot_url`
- safe cycle sends no alert and writes one dataset row
- high-confidence unsafe cycle sends an alert and writes one dataset row
- medium-confidence sequence only fires when threshold is met
- auto-silence flushes the window and suppresses later medium alert
- `run_forever(...)` catches a cycle exception and continues

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor'`

## Chunk 2: Implement Snapshot Fetch and Helpers

### Task 2: Create `monitor.py` skeleton and fetch helper

**Files:**
- Create: `monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write or confirm the targeted failing test**

Focus on `fetch_snapshot(...)` using `config.stream.snapshot_url` and returning `response.content`.

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor.py -k fetch_snapshot -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add:
- module logger
- `fetch_snapshot(config)` using `requests.get(..., timeout=(connect, read))`
- `build_sensor_snapshot(config)`
- `build_alert(...)`

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor.py -k fetch_snapshot -v`
Expected: PASS

## Chunk 3: Implement `run_cycle(...)`

### Task 3: Wire a safe cycle end to end

**Files:**
- Modify: `monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the safe-cycle failing test**

Assert:
- no alert is sent
- dataset `log.jsonl` gets one row
- row has `alert_fired=False`
- row has expected provider/model/prompt version values

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor.py -k safe_cycle -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement `run_cycle(...)` with:
- timestamp creation
- snapshot fetch
- prompt build
- provider assess
- sliding-window push
- patient-location push
- `decide_alert_type(...)`
- dataset entry creation via `record_dataset_entry(...)`

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor.py -k safe_cycle -v`
Expected: PASS

### Task 4: Wire alert-firing paths

**Files:**
- Modify: `monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the high-unsafe failing test**

Assert a high-confidence unsafe assessment:
- sends exactly one alert
- uses `AlertType.UNSAFE_HIGH`
- writes a dataset row with `alert_fired=True`

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor.py -k high_unsafe -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Call `alert_channel.send(...)` when `decide_alert_type(...)` returns an alert type and map the alert to the correct priority/message.

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor.py -k high_unsafe -v`
Expected: PASS

### Task 5: Honor medium threshold and auto-silence behavior

**Files:**
- Modify: `monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the medium-threshold failing test**

Use a provider fake returning two medium-unsafe assessments. Assert no alert on first cycle and one `UNSAFE_MEDIUM` alert on second cycle.

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor.py -k medium_threshold -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Make sure `run_cycle(...)` uses the live window counter counts and starts the medium cooldown after sending.

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor.py -k medium_threshold -v`
Expected: PASS

- [ ] **Step 5: Write the auto-silence flush failing test**

Drive three `out_of_bed` safe assessments to activate silence, then two medium-unsafe assessments. Assert no medium alert fires because silence is active and the window was flushed.

- [ ] **Step 6: Run the targeted test**

Run: `pytest tests/test_monitor.py -k auto_silence -v`
Expected: FAIL

- [ ] **Step 7: Write minimal implementation**

On `SilenceEvent.ACTIVATE`, flush the window and cancel medium/low cooldowns before deciding alerts.

- [ ] **Step 8: Run the targeted test again**

Run: `pytest tests/test_monitor.py -k auto_silence -v`
Expected: PASS

## Chunk 4: Implement `run_forever(...)` and Verify

### Task 6: Add cycle-boundary resilience

**Files:**
- Modify: `monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the failing forever-loop test**

Patch `run_cycle(...)` to raise once, then stop the loop on the next iteration via a sentinel exception. Assert:
- the first exception is logged
- `time.sleep(config.monitor.interval_seconds)` is called
- the loop continues past the failure

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor.py -k run_forever -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement `run_forever(...)` with:
- long-lived `SlidingWindowCounter`, `CooldownTimer`, and `PatientLocationStateMachine`
- `while True`
- cycle-boundary `except Exception` with `logger.exception(...)`
- sleep at the end of every iteration

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor.py -k run_forever -v`
Expected: PASS

- [ ] **Step 5: Run the full monitor test file**

Run: `pytest tests/test_monitor.py -v`
Expected: PASS

- [ ] **Step 6: Run full project verification**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 7: Run lint and formatting**

Run: `ruff check .`
Expected: PASS

Run: `black --check .`
Expected: PASS
