# Design: Alert Sliding Window + Cooldown Logic

**File:** `docs/superpowers/specs/2026-04-09-alert-sliding-window-cooldown-design.md`
**Task:** Milestone 1 — "Implement alert sliding window + cooldown logic in alert.py"
**Date:** 2026-04-09

---

## Context

`decide_alert_type()` (already implemented) is a pure function that accepts pre-computed state:
`medium_unsafe_in_window`, `low_unsafe_in_window`, `medium_cooldown_active`, `low_cooldown_active`.

This task implements the two stateful components that produce those values:

1. **`SlidingWindowCounter`** — tracks medium/low unsafe frame counts in a rolling N-frame window.
2. **`CooldownTimer`** — tracks whether a cooldown is active for a given alert type.

The **patient_location state machine** (next task) handles silence state and will call `flush()` when silence activates. Silence is not in scope here.

---

## PRD Rules (§6.3, §6.4)

- Window size: 5 frames (`config.alerts.window_size`).
- `safe: true` does NOT reset the window — it adds a "safe" frame that naturally ages out.
- Window flush on silence activation (called externally by patient_location state machine).
- Counters are in-memory only; reset on process restart or flush.
- **Medium cooldown:** 5 minutes after an `UNSAFE_MEDIUM` alert fires (`config.alerts.cooldown_minutes`).
- **Low cooldown:** 60 minutes after a `SOFT_LOW_CONFIDENCE` alert fires (`config.alerts.low_confidence_cooldown_minutes`).
- HIGH confidence: no cooldown (always fires immediately, bypass is already in `decide_alert_type()`).

---

## Design

### `SlidingWindowCounter`

```
SlidingWindowCounter(window_size: int)
  push(assessment: AssessmentResult) -> None
  medium_count() -> int
  low_count() -> int
  flush() -> None
```

Internally uses `collections.deque(maxlen=window_size)`. Each call to `push()` appends the
assessment's `Confidence` value if unsafe, or `None` if safe. `medium_count()` and `low_count()`
sum matching entries. `flush()` clears the deque.

- Safe frames → `None` appended. Contributes to window aging but not to either counter.
- HIGH unsafe → `Confidence.HIGH` appended. Ages normally; not counted by medium/low counters.
- MEDIUM unsafe → `Confidence.MEDIUM` appended.
- LOW unsafe → `Confidence.LOW` appended.

A `deque(maxlen=N)` automatically evicts the oldest entry on each push — no manual rotation needed.

`push()` branches on `assessment.safe` first, before checking confidence. A `safe=True` assessment
always appends `None` regardless of its `Confidence` value (the VLM always emits a confidence field
even for safe assessments). This mirrors Rule 1 in `decide_alert_type()`: safe short-circuits before
any confidence check.

### `CooldownTimer`

```
CooldownTimer(duration_seconds: float, *, clock: Callable[[], float] = time.monotonic)
  active: bool   (property)
  start() -> None
  cancel() -> None
```

`_expires_at: float | None` — `None` means no cooldown is running. `active` returns
`True` if `clock() < _expires_at`; `clock()` is called fresh on every access (not cached).
`start()` is idempotent: if `_expires_at is not None` (cooldown already running), it does
nothing — it does NOT extend the expiry. Extending would allow repeated unsafe frames to keep
pushing the cooldown forward indefinitely, preventing any further alert from firing.
`cancel()` sets `_expires_at = None` (abandons the active cooldown; used on silence activation).

The `clock` parameter is injected for testability (tests pass a fake clock; production
uses the default `time.monotonic`). This avoids `time.sleep()` in tests entirely.

`cancel()` is named for intent: it communicates that the cooldown is being deliberately abandoned,
not restarted. Used exclusively by the patient_location state machine on silence activation.

---

## Module Placement

Both classes added to `alert.py` below `decide_alert_type()`. No new files needed.

Public surface of `alert.py` after this task:
- `decide_alert_type(...)` — pure function (existing)
- `SlidingWindowCounter` — stateful, in-memory
- `CooldownTimer` — stateful, clock-injectable

---

## Usage Pattern (for monitor.py)

```python
window = SlidingWindowCounter(config.alerts.window_size)
medium_cd = CooldownTimer(config.alerts.cooldown_minutes * 60)
low_cd = CooldownTimer(config.alerts.low_confidence_cooldown_minutes * 60)

# Per-frame loop:
window.push(assessment)
alert_type = decide_alert_type(
    assessment,
    medium_unsafe_in_window=window.medium_count(),
    low_unsafe_in_window=window.low_count(),
    silence_active=silence_manager.active,      # from patient_location state machine
    medium_cooldown_active=medium_cd.active,
    low_cooldown_active=low_cd.active,
    config=config.alerts,
)
if alert_type == AlertType.UNSAFE_MEDIUM:
    medium_cd.start()
elif alert_type == AlertType.SOFT_LOW_CONFIDENCE:
    low_cd.start()

# On silence activation (called by patient_location state machine):
window.flush()
medium_cd.cancel()
low_cd.cancel()
```

No `AlertStateManager` wrapper is introduced — the composition is simple enough that
`monitor.py` can hold the three objects directly. The patient_location state machine
(next task) will call `flush()`/`cancel()` via its own interface.

---

## Testing Strategy

Test file: `tests/test_alert_window_cooldown.py`

**`SlidingWindowCounter` tests:**
- `push()` with safe assessment (any confidence) → low/medium counts both 0
- `push()` with safe=True, confidence=HIGH → low/medium counts both 0 (safe wins over confidence)
- `push()` with MEDIUM unsafe → medium_count() == 1
- `push()` with LOW unsafe → low_count() == 1
- `push()` with HIGH unsafe → medium/low counts both 0 (HIGH doesn't affect them)
- Window not full (fewer pushes than maxlen): counts are correct
- Window exactly at capacity (exactly `window_size` pushes): counts are correct
- Window eviction: push `window_size + 1` frames — oldest entry drops off, count reflects eviction
- Mixed frames: verify exact counts for a known sequence
- `flush()` on non-empty window → both counts 0, push after flush works normally
- `flush()` on empty window → no-op (no error, counts remain 0)
- `medium_count()` ignores LOW entries; `low_count()` ignores MEDIUM entries

**`CooldownTimer` tests:**
- `active` returns False before any `start()` call
- `active` returns True immediately after `start()` (fake clock not advanced)
- `active` returns False after fake clock advances past expiry
- `active` returns False after `cancel()`
- `cancel()` before any `start()` is a no-op (no error)
- `start()` called twice while active: second call does NOT extend the expiry
- `start()` after expiry (clock advanced past expiry, then `start()` again): starts a new cooldown
- Duration of 0 seconds: `active` is False immediately (boundary)

---

## Error Handling

No error handling needed. Both classes operate on valid domain types already validated
upstream (`AssessmentResult` from `parse_vlm_response`, `config` from `load_config`).
Malformed input is a programming error, not a runtime condition.

---

## Out of Scope

- Silence state (`silence_active`) — owned by patient_location state machine (next task).
- Persisting window/cooldown state across restarts — PRD explicitly accepts in-memory only.
- Thread safety — the monitor loop is single-threaded in Phase 1.
- Alert escalation — open question noted in PRD §6.3; not implemented.
- How the patient_location state machine receives references to `window`, `medium_cd`, and
  `low_cd` — the next spec must decide this (three constructor arguments, or a containing object).
