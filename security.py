"""Access tracking and stream pause state for vigil security features."""

from __future__ import annotations

import datetime
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path


class AccessTracker:
    """Track first-seen IPs within a fixed detection window."""

    def __init__(
        self,
        *,
        window_seconds: float,
        whitelist: list[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window_seconds
        self._whitelist = {ip.lower() for ip in (whitelist or [])}
        self._clock = clock
        self._seen: dict[str, float] = {}

    def check_and_record(self, ip: str) -> bool:
        """Return True when this IP should trigger a notification."""
        if ip.lower() in self._whitelist:
            return False
        now = self._clock()
        key = ip.lower()
        first_seen = self._seen.get(key)
        if first_seen is not None and (now - first_seen) < self._window:
            return False
        self._seen[key] = now
        return True


class StreamPauseState:
    """Track whether the MJPEG stream is paused."""

    def __init__(
        self,
        *,
        auto_resume_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._auto_resume_seconds = auto_resume_seconds
        self._clock = clock
        self._paused_at_mono: float | None = None
        self._paused_at_utc: datetime.datetime | None = None

    @property
    def is_paused(self) -> bool:
        return self._paused_at_mono is not None

    @property
    def paused_at(self) -> datetime.datetime | None:
        return self._paused_at_utc

    def pause(self) -> bool:
        """Pause the stream. Return True only if state changed."""
        if self.is_paused:
            return False
        self._paused_at_mono = self._clock()
        self._paused_at_utc = datetime.datetime.now(datetime.UTC)
        return True

    def resume(self) -> bool:
        """Resume the stream. Return True only if state changed."""
        if not self.is_paused:
            return False
        self._paused_at_mono = None
        self._paused_at_utc = None
        return True

    def check_and_auto_resume(self) -> bool:
        """Resume automatically when the configured timeout elapses."""
        paused_at = self._paused_at_mono
        if paused_at is None:
            return False
        if (self._clock() - paused_at) < self._auto_resume_seconds:
            return False
        self._paused_at_mono = None
        self._paused_at_utc = None
        return True


class CallState:
    """Track whether a two-way audio call is active."""

    def __init__(
        self,
        *,
        auto_expire_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._auto_expire_seconds = auto_expire_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._started_at_mono: float | None = None

    def start(self) -> bool:
        """Mark the call as active. Return True only if state changed."""
        with self._lock:
            if self._started_at_mono is not None and not self._is_expired(self._started_at_mono):
                return False
            self._started_at_mono = self._clock()
            return True

    def end(self) -> bool:
        """Mark the call as inactive. Return True only if state changed."""
        with self._lock:
            if self._started_at_mono is None:
                return False
            self._started_at_mono = None
            return True

    def is_active(self) -> bool:
        """Return True when a call is active and has not auto-expired."""
        with self._lock:
            started_at = self._started_at_mono
            if started_at is None:
                return False
            if self._is_expired(started_at):
                self._started_at_mono = None
                return False
            return True

    def _is_expired(self, started_at: float) -> bool:
        return (self._clock() - started_at) >= self._auto_expire_seconds


class ChimeError(RuntimeError):
    """Raised when the pre-call chime cannot be played."""


class ChimePlayer:
    """Play a pre-call WAV chime through the local speaker."""

    def __init__(
        self,
        path: str | Path,
        *,
        run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._path = Path(path)
        if not self._path.is_file():
            raise ChimeError(f"Chime file missing: {self._path}")
        self._run_command = run_command

    def play(self) -> None:
        result = self._run_command(["aplay", str(self._path)], timeout=10)
        if result.returncode != 0:
            raise ChimeError(f"aplay failed for {self._path} with exit code {result.returncode}")
