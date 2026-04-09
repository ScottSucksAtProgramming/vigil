# Design Spec: Monitor Full-Cycle Integration Test

**Date:** 2026-04-09
**Project:** grandma-watcher
**Status:** Approved
**Scope:** Add a dedicated integration-style test file that exercises the real monitor cycle with mocked camera, provider, and alert delivery boundaries

---

## 1. Overview

This task adds the first full-cycle integration-style coverage for the monitoring path. The goal is not to re-test each adapter in isolation. That already exists in the provider and Pushover unit tests. The goal is to verify that the real `run_cycle(...)` orchestration in `monitor.py` correctly connects:

- frame input
- prompt construction
- assessment handling
- alert decision logic
- alert delivery
- dataset persistence

All tests must run on Mac without hardware or network access.

**Dependency direction under test:** `monitor.py → prompt_builder.py → alert.py → dataset.py`

---

## 2. Test File Shape

Create a new file:

`tests/test_monitor_integration.py`

This file should remain distinct from `tests/test_monitor.py`.

- `tests/test_monitor.py` stays focused on unit-level orchestration behavior and helper seams
- `tests/test_monitor_integration.py` covers multi-module end-to-end cycle behavior inside one process

Keep all production code unchanged unless the test reveals a real bug.

---

## 3. Test Boundaries

Use the real implementations of:

- `monitor.run_cycle(...)`
- `prompt_builder.build_prompt(...)`
- `alert.decide_alert_type(...)`
- `alert.SlidingWindowCounter`
- `alert.CooldownTimer`
- `alert.PatientLocationStateMachine`
- `dataset.record_dataset_entry(...)`

Mock or fake only the external boundaries:

- **camera**: inject `fetch_frame=lambda _: fixture_frame_bytes`
- **OpenRouter**: fake provider returning pre-seeded `AssessmentResult` values
- **Pushover**: fake alert channel collecting sent `Alert` objects

Use `tmp_path` dataset directories so the tests assert on real files without touching the repo dataset tree.

---

## 4. Scenarios

### Safe cycle

Assert that one safe cycle:

- sends no alert
- writes one image file
- writes one JSONL row
- passes the fixture JPEG bytes to the provider
- passes a prompt containing the expected patient-context text to the provider

### High-confidence unsafe cycle

Assert that one high-confidence unsafe cycle:

- sends exactly one `UNSAFE_HIGH` alert
- writes one dataset row with `alert_fired=true`
- preserves the assessment reason in the alert message

### Medium-confidence threshold sequence

Assert that two consecutive medium-unsafe cycles:

- do not alert on the first cycle
- alert exactly once on the second cycle

### Low-confidence threshold sequence

Assert that three consecutive low-unsafe cycles:

- do not alert before the threshold
- send exactly one `SOFT_LOW_CONFIDENCE` alert at threshold

### Auto-silence sequence

Assert that:

1. Three `out_of_bed` frames activate auto-silence
2. Subsequent medium-unsafe frames do not produce an alert while silence is active
3. Dataset rows still continue to be written during silence

This verifies the project’s core invariant that silence suppresses delivery, not monitoring.

---

## 5. Test Helpers

The file should define small local helpers:

- provider fake with queued `AssessmentResult` responses and call capture
- alert-channel fake collecting sent `Alert` instances
- config helper replacing `dataset.*` paths with `tmp_path`
- state helper returning fresh window/cooldown/location-state objects per scenario

No need to patch global network functions in this test file because `monitor.run_cycle(...)` already accepts an injected `fetch_frame` seam.

---

## 6. Assertions That Matter

Prioritize assertions on behavior that crosses module boundaries:

- files exist where the dataset module says they should
- JSONL row values match the cycle outcome
- alert types and messages match the decision path
- prompt text reaches the provider
- silence suppresses alerts but not dataset writes

Do not over-assert internal implementation details like exact timestamp values or internal deque contents.

---

## 7. What Not to Include

- No real HTTP requests
- No real `OpenRouterProvider`
- No real `PushoverChannel`
- No `run_forever(...)` loop control
- No Healthchecks or failover behavior
- No Pi-only smoke coverage

That remains outside this task.
