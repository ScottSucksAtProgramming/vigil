# PatientLocationStateMachine Implementation Plan

> **For agentic workers:** REQUIRED: Follow superpowers:test-driven-development strictly. Write one failing test, verify it fails, write minimal code to pass, verify green, then move to the next test. Do NOT write implementation code before the test.

**Goal:** Implement `SilenceEvent` enum and `PatientLocationStateMachine` class in `alert.py`, with full test coverage in `tests/test_patient_location_state_machine.py`.

**Architecture:** Pure state class — no I/O, no logging, no side effects. Takes `AssessmentResult`, returns `SilenceEvent | None`. The caller (`monitor.py`, wired in a later milestone) is responsible for acting on the returned event (flushing windows, sending Pushover, etc.). The class is injectable for testability (thresholds passed at construction; no global config).

**Files to modify:**
- `alert.py` — add `SilenceEvent` enum and `PatientLocationStateMachine` class (append after `CooldownTimer`)
- `tests/test_patient_location_state_machine.py` — new test file

---

## Background

PRD §6.3 and §15 define the state machine. Key rules:

| `patient_location` value | Consecutive frames | Action |
|---|---|---|
| `out_of_bed` | 3 | Return `SilenceEvent.ACTIVATE` |
| `in_bed` (while auto-silenced) | 2 | Return `SilenceEvent.RESUME` |
| `being_assisted_out` | any | No action; resets both counters |
| `unknown` | any | Treat as `in_bed` |
| All others | any | Return `None` |

`SilenceEvent.ACTIVATE` fires exactly once per silence episode (guard: not already silenced).
`SilenceEvent.RESUME` fires exactly once per resume (guard: currently silenced).
HIGH confidence unsafe alerts bypass silence entirely — that logic lives in `decide_alert_type`, not here.

---

## SilenceEvent Enum

```python
class SilenceEvent(Enum):
    """Event returned by PatientLocationStateMachine.push() when silence state changes."""
    ACTIVATE = "activate"   # caller should activate silence (flush windows, cancel cooldowns)
    RESUME = "resume"       # caller should resume alerts and send Pushover to Mom
```

---

## PatientLocationStateMachine Design

```python
class PatientLocationStateMachine:
    def __init__(
        self,
        *,
        out_of_bed_frames_to_silence: int,
        in_bed_frames_to_resume: int,
    ) -> None:
        self._out_of_bed_threshold = out_of_bed_frames_to_silence
        self._in_bed_threshold = in_bed_frames_to_resume
        self._consecutive_out_of_bed = 0
        self._consecutive_in_bed = 0
        self._auto_silenced = False

    @property
    def auto_silenced(self) -> bool:
        """True when auto-silence is currently active."""
        ...

    def push(self, assessment: AssessmentResult) -> SilenceEvent | None:
        """Process one frame. Returns a SilenceEvent if silence state changes, else None."""
        ...
```

**Counter update rules (applied on every push, before threshold check):**

| Effective location | `_consecutive_out_of_bed` | `_consecutive_in_bed` |
|---|---|---|
| `out_of_bed` | += 1 | = 0 |
| `in_bed` or `unknown` | = 0 | += 1 |
| `being_assisted_out` | = 0 | = 0 |

**Threshold check (after counter update):**

1. If `not _auto_silenced` and `_consecutive_out_of_bed >= _out_of_bed_threshold`:
   - Set `_auto_silenced = True` → return `SilenceEvent.ACTIVATE`
2. Else if `_auto_silenced` and `_consecutive_in_bed >= _in_bed_threshold`:
   - Set `_auto_silenced = False` → return `SilenceEvent.RESUME`
3. Else return `None`

The guards (`not _auto_silenced`, `_auto_silenced`) prevent double-firing: ACTIVATE won't fire again while already silenced; RESUME won't fire when not silenced.

---

## Implementation Steps (strict TDD order)

### Step 1 — SilenceEvent enum
- [ ] Write `test_silence_event_has_activate_and_resume_values` — import `SilenceEvent`, assert both values exist
- [ ] Verify RED (ImportError or AttributeError)
- [ ] Add `SilenceEvent` enum to `alert.py`
- [ ] Verify GREEN

### Step 2 — Constructor and auto_silenced property
- [ ] Write `test_psm_initial_auto_silenced_is_false` — construct with thresholds, assert `auto_silenced is False`
- [ ] Verify RED
- [ ] Add `PatientLocationStateMachine.__init__` and `auto_silenced` property (stub `push` with `return None`)
- [ ] Verify GREEN

### Step 3 — `out_of_bed` below threshold returns None
- [ ] Write `test_psm_out_of_bed_below_threshold_returns_none` — push `out_of_bed` twice with threshold=3, assert None both times
- [ ] Verify RED
- [ ] Implement counter increment for `out_of_bed` (no threshold check yet)
- [ ] Verify GREEN

### Step 4 — `out_of_bed` at threshold returns ACTIVATE
- [ ] Write `test_psm_out_of_bed_at_threshold_returns_activate` — push `out_of_bed` three times, assert third push returns `SilenceEvent.ACTIVATE`
- [ ] Verify RED
- [ ] Add threshold check → return `SilenceEvent.ACTIVATE`, set `_auto_silenced = True`
- [ ] Verify GREEN

### Step 5 — auto_silenced True after ACTIVATE
- [ ] Write `test_psm_auto_silenced_true_after_activate` — trigger ACTIVATE, assert `auto_silenced is True`
- [ ] Verify RED (likely already GREEN from Step 4; if so, note it and proceed)
- [ ] Verify GREEN

### Step 6 — ACTIVATE fires only once per episode
- [ ] Write `test_psm_activate_fires_once_then_none` — push `out_of_bed` x4 with threshold=3; assert 4th push returns None
- [ ] Verify RED
- [ ] Add `not _auto_silenced` guard to ACTIVATE check
- [ ] Verify GREEN

### Step 7 — `in_bed` below resume threshold returns None (while silenced)
- [ ] Write `test_psm_in_bed_below_resume_threshold_returns_none` — trigger ACTIVATE, push `in_bed` once with resume_threshold=2, assert None
- [ ] Verify RED
- [ ] Add counter update for `in_bed` (reset out_of_bed, increment in_bed)
- [ ] Verify GREEN

### Step 8 — `in_bed` at resume threshold returns RESUME
- [ ] Write `test_psm_in_bed_at_resume_threshold_returns_resume` — trigger ACTIVATE, push `in_bed` twice, assert second push returns `SilenceEvent.RESUME`
- [ ] Verify RED
- [ ] Add RESUME threshold check with `_auto_silenced` guard
- [ ] Verify GREEN

### Step 9 — auto_silenced False after RESUME
- [ ] Write `test_psm_auto_silenced_false_after_resume` — trigger ACTIVATE then RESUME, assert `auto_silenced is False`
- [ ] Verify RED (likely already GREEN; note and proceed)
- [ ] Verify GREEN

### Step 10 — RESUME fires only once per episode
- [ ] Write `test_psm_resume_fires_once_then_none` — trigger ACTIVATE, push `in_bed` x3 with resume_threshold=2; assert 3rd push returns None
- [ ] Verify RED
- [ ] Confirm `_auto_silenced = False` in RESUME path prevents re-fire
- [ ] Verify GREEN

### Step 11 — `in_bed` before any silence returns None
- [ ] Write `test_psm_in_bed_before_silence_never_returns_resume` — push `in_bed` x5 with no prior silence, assert all None
- [ ] Verify RED
- [ ] Confirm `_auto_silenced` guard handles this
- [ ] Verify GREEN

### Step 12 — `unknown` treated as `in_bed` (increments in_bed counter)
- [ ] Write `test_psm_unknown_counts_as_in_bed_for_resume` — trigger ACTIVATE, push `unknown` twice with resume_threshold=2, assert second push returns `SilenceEvent.RESUME`
- [ ] Verify RED
- [ ] Add `unknown` → treat as `in_bed` mapping in `push()`
- [ ] Verify GREEN

### Step 13 — `unknown` resets out_of_bed counter
- [ ] Write `test_psm_unknown_resets_out_of_bed_counter` — push `out_of_bed` twice, push `unknown`, push `out_of_bed` twice (threshold=3); assert no ACTIVATE fires in last two pushes
- [ ] Verify RED (likely already GREEN from Step 12; note and proceed)
- [ ] Verify GREEN

### Step 14 — `being_assisted_out` resets out_of_bed counter
- [ ] Write `test_psm_being_assisted_out_resets_out_of_bed_counter` — push `out_of_bed` twice (threshold=3), push `being_assisted_out`, push `out_of_bed` twice; assert no ACTIVATE fires
- [ ] Verify RED
- [ ] Add `being_assisted_out` → reset both counters in `push()`
- [ ] Verify GREEN

### Step 15 — `being_assisted_out` resets in_bed counter
- [ ] Write `test_psm_being_assisted_out_resets_in_bed_counter` — trigger ACTIVATE, push `in_bed` once (resume_threshold=2), push `being_assisted_out`, push `in_bed` once; assert no RESUME fires on last push
- [ ] Verify RED (likely already GREEN from Step 14; note and proceed)
- [ ] Verify GREEN

### Step 16 — Can re-silence after resume
- [ ] Write `test_psm_can_reactivate_after_resume` — full cycle: ACTIVATE → RESUME → push `out_of_bed` x3 → assert ACTIVATE fires again
- [ ] Verify RED
- [ ] Confirm logic handles second silence episode correctly
- [ ] Verify GREEN

### Step 17 — Return type is SilenceEvent or None
- [ ] Write `test_psm_push_returns_silence_event_or_none` — assert return value is always `SilenceEvent | None`
- [ ] Verify RED (likely GREEN; note and proceed)
- [ ] Verify GREEN

---

## Test Helpers

```python
def _make_assessment(location: PatientLocation) -> AssessmentResult:
    return AssessmentResult(
        safe=True,
        confidence=Confidence.HIGH,
        reason="Test.",
        patient_location=location,
    )

def _make_psm(
    *,
    out_threshold: int = 3,
    in_threshold: int = 2,
) -> PatientLocationStateMachine:
    return PatientLocationStateMachine(
        out_of_bed_frames_to_silence=out_threshold,
        in_bed_frames_to_resume=in_threshold,
    )

def _trigger_silence(psm: PatientLocationStateMachine) -> None:
    """Push enough out_of_bed frames to activate auto-silence (threshold=3 default)."""
    for _ in range(3):
        psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
```

---

## Acceptance Criteria

- [ ] All 17 test steps pass
- [ ] `pytest tests/test_patient_location_state_machine.py` exits 0
- [ ] `pytest` (full suite) exits 0 — no regressions
- [ ] `ruff check alert.py` and `black --check alert.py` pass
- [ ] `SilenceEvent` and `PatientLocationStateMachine` are importable from `alert`
- [ ] `todo.taskpaper`: mark "Implement patient_location state machine in alert.py" as `@done`
