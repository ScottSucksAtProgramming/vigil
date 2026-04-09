# Monitor Integration Test Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated integration-style test file that validates the real `run_cycle(...)` orchestration across prompt building, alert logic, and dataset persistence with mocked external boundaries.

**Architecture:** Keep production code unchanged unless the new integration tests expose a real defect. Build one focused test file with small fakes for provider and alert delivery, tmp-path dataset storage, and injected frame bytes so the cycle runs end to end without real network calls.

**Tech Stack:** Python 3.11, pytest, tmp_path, dataclasses, deque, fixture JPEG

---

## Chunk 1: Test File Skeleton and Helpers

### Task 1: Create the integration test file and helper fakes

**Files:**
- Create: `tests/test_monitor_integration.py`
- Test: `tests/test_monitor_integration.py`

- [ ] **Step 1: Write the failing test file skeleton**

Include:
- provider fake with queued `AssessmentResult` responses and call capture
- alert-channel fake collecting `Alert`s
- config helper overriding dataset paths to `tmp_path`
- state helper returning fresh counter/cooldown/location-state objects

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitor_integration.py -v`
Expected: FAIL with at least one missing test assertion or import-level red state

## Chunk 2: Safe and High-Unsafe Full Cycles

### Task 2: Add safe-cycle integration coverage

**Files:**
- Modify: `tests/test_monitor_integration.py`
- Test: `tests/test_monitor_integration.py`

- [ ] **Step 1: Write the failing safe-cycle test**

Assert:
- no alert sent
- one image file exists
- one JSONL row exists
- provider receives the fixture frame bytes
- provider receives prompt text containing `"97 years old"` and `"Parkinson's"`

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor_integration.py -k safe_cycle -v`
Expected: FAIL

- [ ] **Step 3: Add the minimum test-support code**

Only if necessary: adjust helper setup, not production code, unless the test reveals a real orchestration bug.

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor_integration.py -k safe_cycle -v`
Expected: PASS

### Task 3: Add high-confidence unsafe-cycle coverage

**Files:**
- Modify: `tests/test_monitor_integration.py`
- Test: `tests/test_monitor_integration.py`

- [ ] **Step 1: Write the failing high-unsafe test**

Assert:
- exactly one `UNSAFE_HIGH` alert is sent
- alert message equals the assessment reason
- JSONL row has `alert_fired=true`

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor_integration.py -k high_unsafe -v`
Expected: FAIL

- [ ] **Step 3: Make the minimum change required**

Prefer test-only changes unless a production defect is exposed.

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor_integration.py -k high_unsafe -v`
Expected: PASS

## Chunk 3: Threshold and Silence Sequences

### Task 4: Add medium and low threshold integration sequences

**Files:**
- Modify: `tests/test_monitor_integration.py`
- Test: `tests/test_monitor_integration.py`

- [ ] **Step 1: Write the failing medium-threshold test**

Use two medium-unsafe assessments. Assert zero alerts after first cycle and one `UNSAFE_MEDIUM` alert after second cycle.

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor_integration.py -k medium_threshold -v`
Expected: FAIL

- [ ] **Step 3: Add the failing low-threshold test**

Use three low-unsafe assessments. Assert zero alerts before threshold and one `SOFT_LOW_CONFIDENCE` alert at threshold.

- [ ] **Step 4: Run the targeted test**

Run: `pytest tests/test_monitor_integration.py -k low_threshold -v`
Expected: FAIL

- [ ] **Step 5: Make the minimum change required**

Prefer helper/test changes only unless real production behavior is wrong.

- [ ] **Step 6: Run both targeted tests again**

Run: `pytest tests/test_monitor_integration.py -k "medium_threshold or low_threshold" -v`
Expected: PASS

### Task 5: Add auto-silence integration coverage

**Files:**
- Modify: `tests/test_monitor_integration.py`
- Test: `tests/test_monitor_integration.py`

- [ ] **Step 1: Write the failing auto-silence test**

Drive:
- three `out_of_bed` frames to activate silence
- two medium-unsafe frames while silenced

Assert:
- no alert is sent during the silenced portion
- silence is active at the end
- dataset rows continue to accumulate for all cycles

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_monitor_integration.py -k auto_silence -v`
Expected: FAIL

- [ ] **Step 3: Make the minimum change required**

Prefer test-only updates unless the test exposes a real defect in `monitor.py`.

- [ ] **Step 4: Run the targeted test again**

Run: `pytest tests/test_monitor_integration.py -k auto_silence -v`
Expected: PASS

## Chunk 4: Full Verification

### Task 6: Verify the new integration coverage and repo health

**Files:**
- Modify: `tests/test_monitor_integration.py` if needed
- Test: `tests/test_monitor_integration.py`

- [ ] **Step 1: Run the full integration file**

Run: `pytest tests/test_monitor_integration.py -v`
Expected: PASS

- [ ] **Step 2: Run the full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Run lint and formatting**

Run: `ruff check .`
Expected: PASS

Run: `black --check .`
Expected: PASS
