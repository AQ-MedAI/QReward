"""Adaptive rate limiter that dynamically adjusts throughput based on error rate and latency."""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Default slowdown factor when error rate exceeds threshold
DEFAULT_SLOWDOWN_FACTOR = 0.5

# Default speedup factor when metrics are healthy
DEFAULT_SPEEDUP_FACTOR = 1.1

# Minimum cooldown (seconds) between consecutive adjustments
DEFAULT_COOLDOWN_SECONDS = 5.0


@dataclass(frozen=True)
class _RequestRecord:
    """Immutable record of a single request outcome."""

    timestamp: float
    latency_seconds: float
    success: bool


class AdaptiveRateLimiter:
    """Dynamically adjusts rate limit based on observed error rate and latency.

    Uses a sliding time window to collect request outcomes, then periodically
    evaluates whether to slow down (reduce limit) or speed up (increase limit).

    Example:
        >>> limiter = AdaptiveRateLimiter(
        ...     initial_limit=100, limit_min=10, limit_max=500,
        ...     error_threshold=0.3, latency_threshold=5.0,
        ... )
        >>> limiter.current_limit
        100
    """

    def __init__(
        self,
        initial_limit: int,
        limit_min: int = 10,
        limit_max: int = 500,
        error_threshold: float = 0.3,
        latency_threshold: float = 5.0,
        window_seconds: float = 10.0,
        slowdown_factor: float = DEFAULT_SLOWDOWN_FACTOR,
        speedup_factor: float = DEFAULT_SPEEDUP_FACTOR,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ):
        """Initialize adaptive rate limiter.

        Args:
            initial_limit: Starting rate limit value.
            limit_min: Floor for the rate limit.
            limit_max: Ceiling for the rate limit.
            error_threshold: Error rate (0-1) above which to slow down.
            latency_threshold: Average latency (seconds) above which to slow down.
            window_seconds: Sliding window duration for statistics.
            slowdown_factor: Multiplier applied on slowdown (< 1).
            speedup_factor: Multiplier applied on speedup (> 1).
            cooldown_seconds: Minimum interval between adjustments.
        """
        if limit_min > limit_max:
            raise ValueError("limit_min must be <= limit_max")
        if not (0 < error_threshold <= 1):
            raise ValueError("error_threshold must be in (0, 1]")

        self._current_limit = float(max(limit_min, min(initial_limit, limit_max)))
        self._limit_min = limit_min
        self._limit_max = limit_max
        self._error_threshold = error_threshold
        self._latency_threshold = latency_threshold
        self._window_seconds = window_seconds
        self._slowdown_factor = slowdown_factor
        self._speedup_factor = speedup_factor
        self._cooldown_seconds = cooldown_seconds

        self._records: deque[_RequestRecord] = deque()
        self._lock = threading.Lock()
        self._last_adjust_time = 0.0

    @property
    def current_limit(self) -> int:
        """Current effective rate limit (rounded to nearest integer)."""
        with self._lock:
            return int(self._current_limit)

    def record(self, latency_seconds: float, success: bool) -> None:
        """Record a request outcome and possibly adjust the limit.

        Args:
            latency_seconds: How long the request took.
            success: Whether the request succeeded.
        """
        now = time.monotonic()
        entry = _RequestRecord(
            timestamp=now, latency_seconds=latency_seconds, success=success
        )
        with self._lock:
            self._records.append(entry)
            self._evict_expired(now)
            self._maybe_adjust(now)

    def _evict_expired(self, now: float) -> None:
        """Remove records older than the sliding window. Must hold lock."""
        cutoff = now - self._window_seconds
        while self._records and self._records[0].timestamp < cutoff:
            self._records.popleft()

    def _maybe_adjust(self, now: float) -> None:
        """Evaluate metrics and adjust limit if cooldown has elapsed. Must hold lock."""
        if now - self._last_adjust_time < self._cooldown_seconds:
            return

        total = len(self._records)
        if total == 0:
            return

        failures = sum(1 for record in self._records if not record.success)
        error_rate = failures / total
        avg_latency = (
            sum(record.latency_seconds for record in self._records) / total
        )

        previous_limit = self._current_limit

        if error_rate > self._error_threshold or avg_latency > self._latency_threshold:
            self._current_limit = max(
                self._limit_min, self._current_limit * self._slowdown_factor
            )
        elif error_rate < self._error_threshold * 0.5:
            self._current_limit = min(
                self._limit_max, self._current_limit * self._speedup_factor
            )

        if self._current_limit != previous_limit:
            self._last_adjust_time = now
            logger.debug(
                "Adaptive limiter adjusted: %.0f -> %.0f "
                "(error_rate=%.2f, avg_latency=%.3fs)",
                previous_limit,
                self._current_limit,
                error_rate,
                avg_latency,
            )

    def snapshot(self) -> dict:
        """Return a snapshot of current statistics.

        Returns:
            Dict with current_limit, total_records, error_rate, avg_latency.
        """
        with self._lock:
            total = len(self._records)
            if total == 0:
                return {
                    "current_limit": int(self._current_limit),
                    "total_records": 0,
                    "error_rate": 0.0,
                    "avg_latency": 0.0,
                }
            failures = sum(1 for record in self._records if not record.success)
            avg_latency = (
                sum(record.latency_seconds for record in self._records) / total
            )
            return {
                "current_limit": int(self._current_limit),
                "total_records": total,
                "error_rate": failures / total,
                "avg_latency": avg_latency,
            }
