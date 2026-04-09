# Alert Sliding Window + Cooldown Logic — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `SlidingWindowCounter` and `CooldownTimer` classes to `alert.py` so `decide_alert_type()` can be called with live per-frame counts and cooldown state.

**Architecture:** Two focused classes added to the bottom of `alert.py`. `SlidingWindowCounter` uses a `collections.deque(maxlen=N)` for O(1) push and natural eviction. `CooldownTimer` receives an injectable `clock` callable (default `time.monotonic`) so tests never call `time.sleep()`. Both classes are stateful but side-effect-free; the caller wires them together.

**Tech Stack:** Python 3.11+, `collections.deque`, `time.monotonic`, pytest.

---

## Chunk 1: SlidingWindowCounter

### Task 1: Create test file with SlidingWindowCounter tests (red)

**Files:**
- Create: `tests/test_alert_window_cooldown.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for SlidingWindowCounter and CooldownTimer in alert.py."""

from __future__ import annotations

from typing import Callable

import pytest

from alert import CooldownTimer, SlidingWindowCounter
from models import AssessmentResult, Confidence, PatientLocation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unsafe(confidence: Confidence) -> AssessmentResult:
    return AssessmentResult(
        safe=False,
        confidence=confidence,
        reason="Test.",
        patient_location=PatientLocation.OUT_OF_BED,
    )


def _safe(confidence: Confidence = Confidence.MEDIUM) -> AssessmentResult:
    return AssessmentResult(
        safe=True,
        confidence=confidence,
        reason="Test.",
        patient_location=PatientLocation.IN_BED,
    )


def _make_clock(initial: float = 0.0) -> tuple[Callable[[], float], list[float]]:
    """Return (clock_fn, time_container). Advance time_container[0] to move the clock."""
    t = [initial]
    return lambda: t[0], t


# ---------------------------------------------------------------------------
# SlidingWindowCounter
# ---------------------------------------------------------------------------


def test_swc_push_safe_counts_zero():
    w = SlidingWindowCounter(5)
    w.push(_safe())
    assert w.medium_count() == 0
    assert w.low_count() == 0


def test_swc_push_safe_high_confidence_counts_zero():
    """safe=True wins over confidence=HIGH — None is appended, not Confidence.HIGH."""
    w = SlidingWindowCounter(5)
    w.push(_safe(Confidence.HIGH))
    assert w.medium_count() == 0
    assert w.low_count() == 0


def test_swc_push_medium_unsafe_increments_medium():
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.MEDIUM))
    assert w.medium_count() == 1
    assert w.low_count() == 0


def test_swc_push_low_unsafe_increments_low():
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.LOW))
    assert w.low_count() == 1
    assert w.medium_count() == 0


def test_swc_push_high_unsafe_not_counted():
    """HIGH unsafe frames age through the window but do not affect medium/low counts."""
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.HIGH))
    assert w.medium_count() == 0
    assert w.low_count() == 0


def test_swc_window_not_full():
    """Counts are correct when window has fewer entries than maxlen."""
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.MEDIUM))
    w.push(_safe())
    w.push(_unsafe(Confidence.LOW))
    assert w.medium_count() == 1
    assert w.low_count() == 1


def test_swc_window_at_capacity():
    """Counts are correct when exactly window_size frames have been pushed."""
    w = SlidingWindowCounter(5)
    for _ in range(3):
        w.push(_unsafe(Confidence.MEDIUM))
    for _ in range(2):
        w.push(_unsafe(Confidence.LOW))
    assert w.medium_count() == 3
    assert w.low_count() == 2


def test_swc_window_eviction():
    """Oldest entry drops when window_size + 1 frames are pushed."""
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.MEDIUM))  # frame 1 — will be evicted
    for _ in range(5):
        w.push(_safe())  # frames 2–6 fill the window
    # Frame 1 (MEDIUM) is now gone; only safe frames remain
    assert w.medium_count() == 0
    assert w.low_count() == 0


def test_swc_mixed_frames_known_sequence():
    """Exact counts for a fully specified sequence."""
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.MEDIUM))  # MEDIUM
    w.push(_unsafe(Confidence.LOW))     # LOW
    w.push(_safe())                     # safe
    w.push(_unsafe(Confidence.MEDIUM))  # MEDIUM
    w.push(_unsafe(Confidence.HIGH))    # HIGH (not counted)
    assert w.medium_count() == 2
    assert w.low_count() == 1


def test_swc_flush_clears_window():
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.MEDIUM))
    w.push(_unsafe(Confidence.LOW))
    w.flush()
    assert w.medium_count() == 0
    assert w.low_count() == 0


def test_swc_flush_then_push_works():
    w = SlidingWindowCounter(5)
    w.push(_unsafe(Confidence.MEDIUM))
    w.flush()
    w.push(_unsafe(Confidence.LOW))
    assert w.medium_count() == 0
    assert w.low_count() == 1


def test_swc_flush_empty_window_no_error():
    """flush() on an empty window is a no-op — no exception, counts remain 0."""
    w = SlidingWindowCounter(5)
    w.flush()  # must not raise
    assert w.medium_count() == 0
    assert w.low_count() == 0


def test_swc_medium_count_ignores_low():
    w = SlidingWindowCounter(5)
    for _ in range(3):
        w.push(_unsafe(Confidence.LOW))
    assert w.medium_count() == 0


def test_swc_low_count_ignores_medium():
    w = SlidingWindowCounter(5)
    for _ in range(3):
        w.push(_unsafe(Confidence.MEDIUM))
    assert w.low_count() == 0
```

- [ ] **Step 2: Run to confirm import error (red)**

```bash
cd /path/to/grandma-watcher
pytest tests/test_alert_window_cooldown.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'SlidingWindowCounter' from 'alert'`

---

### Task 2: Implement SlidingWindowCounter (green)

**Files:**
- Modify: `alert.py` (append after `decide_alert_type`)

- [ ] **Step 3: Add imports and SlidingWindowCounter to alert.py**

At the top of `alert.py`, add `from __future__ import annotations` if not present, and add two new imports:

```python
from __future__ import annotations

from collections import deque

from config import AlertsConfig
from models import AlertType, AssessmentResult, Confidence
```

Then append after `decide_alert_type()`:

```python

class SlidingWindowCounter:
    """Rolling N-frame window tracking medium and low confidence unsafe counts.

    Each push appends the assessment's Confidence (if unsafe) or None (if safe).
    safe=True always appends None regardless of the confidence field value.
    Old entries age out automatically via deque(maxlen=N).
    """

    def __init__(self, window_size: int) -> None:
        self._window: deque[Confidence | None] = deque(maxlen=window_size)

    def push(self, assessment: AssessmentResult) -> None:
        """Append this assessment to the window."""
        if assessment.safe:
            self._window.append(None)
        else:
            self._window.append(assessment.confidence)

    def medium_count(self) -> int:
        """Return how many of the last N frames were MEDIUM confidence unsafe."""
        return sum(1 for c in self._window if c == Confidence.MEDIUM)

    def low_count(self) -> int:
        """Return how many of the last N frames were LOW confidence unsafe."""
        return sum(1 for c in self._window if c == Confidence.LOW)

    def flush(self) -> None:
        """Clear all window entries (called on silence activation)."""
        self._window.clear()
```

- [ ] **Step 4: Run SlidingWindowCounter tests only**

```bash
pytest tests/test_alert_window_cooldown.py -k "swc" -v
```

Expected: all `test_swc_*` tests pass, CooldownTimer tests still import-error (that's fine — we'll add them next).

Actually at this point CooldownTimer tests are not yet in the file, so just:

```bash
pytest tests/test_alert_window_cooldown.py -v
```

Expected: 14 tests pass (all `test_swc_*`). If CooldownTimer import fails at collection time, add a `# noqa` or split the import — but since we're adding both classes in the same commit, just run the full `make check` after Task 4.

---

## Chunk 2: CooldownTimer

### Task 3: Add CooldownTimer tests to test file (red)

**Files:**
- Modify: `tests/test_alert_window_cooldown.py` (append)

- [ ] **Step 5: Append CooldownTimer tests to the test file**

```python

# ---------------------------------------------------------------------------
# CooldownTimer
# ---------------------------------------------------------------------------


def test_cd_inactive_before_start():
    clock, _ = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    assert not cd.active


def test_cd_active_after_start():
    clock, _ = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    cd.start()
    assert cd.active  # clock still at 0.0, expires_at = 300.0


def test_cd_inactive_after_expiry():
    clock, t = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    cd.start()
    t[0] = 300.0  # advance to exactly expiry — 300 < 300 is False
    assert not cd.active


def test_cd_inactive_after_cancel():
    clock, _ = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    cd.start()
    cd.cancel()
    assert not cd.active


def test_cd_cancel_before_start_no_error():
    """cancel() before any start() is a no-op — must not raise."""
    clock, _ = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    cd.cancel()  # must not raise
    assert not cd.active


def test_cd_start_idempotent_does_not_extend():
    """Second start() while active must NOT extend the expiry."""
    clock, t = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    cd.start()                   # expires_at = 300.0
    t[0] = 100.0                 # advance to t=100
    cd.start()                   # must be ignored — still expires at 300
    t[0] = 250.0                 # advance to t=250 (still before 300)
    assert cd.active             # cooldown still running
    t[0] = 300.0                 # advance to expiry
    assert not cd.active         # now expired at original expiry, not 100+300=400


def test_cd_start_after_expiry_restarts():
    """start() after the cooldown has expired should start a new cooldown."""
    clock, t = _make_clock()
    cd = CooldownTimer(300.0, clock=clock)
    cd.start()          # expires at t=300
    t[0] = 400.0        # advance past expiry
    assert not cd.active
    cd.start()          # restart — new expiry at t=700
    assert cd.active
    t[0] = 699.0
    assert cd.active
    t[0] = 700.0
    assert not cd.active


def test_cd_zero_duration_inactive_immediately():
    """Duration of 0: active is False immediately after start (boundary)."""
    clock, _ = _make_clock(0.0)
    cd = CooldownTimer(0.0, clock=clock)
    cd.start()
    # expires_at = 0.0; clock() = 0.0; 0.0 < 0.0 is False
    assert not cd.active
```

- [ ] **Step 6: Run to confirm CooldownTimer import error (red)**

```bash
pytest tests/test_alert_window_cooldown.py -k "cd" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'CooldownTimer' from 'alert'`

---

### Task 4: Implement CooldownTimer (green)

**Files:**
- Modify: `alert.py` (append after SlidingWindowCounter)
- Modify: `alert.py` imports (add `import time` and `from collections.abc import Callable`)

- [ ] **Step 7: Add time import and Callable import to alert.py**

At the top of `alert.py`, add:

```python
import time
from collections import deque
from collections.abc import Callable
```

Full import block for `alert.py` should look like:

```python
"""Alert decision logic for grandma-watcher.

Single public function: decide_alert_type().
Pure function — no I/O, no logging, no global state.
Dependencies: models.py, config.py only.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from config import AlertsConfig
from models import AlertType, AssessmentResult, Confidence
```

- [ ] **Step 8: Append CooldownTimer class to alert.py**

```python

class CooldownTimer:
    """Tracks whether a cooldown period is active for a given alert type.

    clock is injectable for testability — tests pass a fake clock and
    advance it without sleeping. Production code uses time.monotonic.

    start() is idempotent: if the cooldown is already active, calling
    start() again does nothing. It does NOT extend the expiry — extending
    would allow repeated unsafe frames to keep pushing the cooldown forward
    indefinitely, preventing any further alert from firing.

    cancel() is used on silence activation to abandon the active cooldown.
    """

    def __init__(
        self,
        duration_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._duration = duration_seconds
        self._clock = clock
        self._expires_at: float | None = None

    @property
    def active(self) -> bool:
        """True if a cooldown is running and has not yet expired.

        clock() is called fresh on every access — not cached.
        """
        if self._expires_at is None:
            return False
        return self._clock() < self._expires_at

    def start(self) -> None:
        """Start the cooldown. No-op if already active."""
        if self.active:
            return
        self._expires_at = self._clock() + self._duration

    def cancel(self) -> None:
        """Cancel the active cooldown (used on silence activation)."""
        self._expires_at = None
```

- [ ] **Step 9: Run all tests in the new file**

```bash
pytest tests/test_alert_window_cooldown.py -v
```

Expected: 22 tests pass (14 SlidingWindowCounter + 8 CooldownTimer).

- [ ] **Step 10: Run full test suite**

```bash
make check
```

Expected: all 176 tests pass (154 existing + 22 new), black and ruff clean.

If black reports reformatting needed, run:

```bash
black tests/test_alert_window_cooldown.py alert.py
make check
```

- [ ] **Step 11: Mark task done in todo.taskpaper**

In `todo.taskpaper`, change:

```
- Implement alert sliding window + cooldown logic in alert.py @na
```

to:

```
- Implement alert sliding window + cooldown logic in alert.py @done
```

- [ ] **Step 12: Append lesson to context/lessons.md**

Append the following dated one-liner to `context/lessons.md`:

```
2026-04-09: CooldownTimer.start() must not extend an active cooldown — extending lets repeated unsafe frames push expiry forward indefinitely; idempotent no-op is the safe behavior.
```

- [ ] **Step 13: Commit**

```bash
git add alert.py tests/test_alert_window_cooldown.py todo.taskpaper context/lessons.md
git commit -m "feat: add SlidingWindowCounter and CooldownTimer to alert.py (Milestone 1)

Deque-based rolling window for medium/low unsafe frame counts.
Clock-injectable cooldown timer with idempotent start(). 22 tests.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
