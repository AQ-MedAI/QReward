"""Circuit breaker implementation for fault tolerance.

Provides automatic circuit breaking when consecutive failures reach a threshold,
with half-open state probing for recovery.
"""

import logging
import threading
import time
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker state enumeration.

    Attributes:
        CLOSED: Normal state, requests are allowed.
        OPEN: Tripped state, requests are blocked.
        HALF_OPEN: Probing state, limited requests allowed to test recovery.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker implementation.

    When consecutive failures reach ``failure_threshold`` the breaker trips
    to OPEN state, blocking all requests.  After ``recovery_timeout`` seconds
    it transitions to HALF_OPEN, allowing up to ``half_open_max_calls``
    probe requests.  A successful probe resets the breaker to CLOSED; a
    failed probe re-opens it.

    Args:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN.
        half_open_max_calls: Max probe requests allowed in HALF_OPEN state.
        time_func: Clock function for testability (default ``time.time``).
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        time_func: Optional[Callable[[], float]] = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._time_func = time_func or time.time

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state.

        Automatically transitions from OPEN → HALF_OPEN when the recovery
        timeout has elapsed.
        """
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def allow_request(self) -> bool:
        """Check whether a request should be allowed.

        Returns:
            True if the request is permitted, False otherwise.
        """
        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self._half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            # OPEN
            return False

    def record_success(self) -> None:
        """Record a successful request and update state accordingly."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "CircuitBreaker transitioning HALF_OPEN -> CLOSED "
                    "(probe succeeded)"
                )
                self._reset_unlocked()
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request and update state accordingly."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "CircuitBreaker transitioning HALF_OPEN -> OPEN "
                    "(probe failed)"
                )
                self._state = CircuitState.OPEN
                self._last_failure_time = self._time_func()
                self._half_open_calls = 0
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                logger.warning(
                    "CircuitBreaker transitioning CLOSED -> OPEN "
                    "(failure_count=%d >= threshold=%d)",
                    self._failure_count,
                    self._failure_threshold,
                )
                self._state = CircuitState.OPEN
                self._last_failure_time = self._time_func()

    def reset(self) -> None:
        """Reset the breaker to its initial CLOSED state."""
        with self._lock:
            self._reset_unlocked()

    # ------------------------------------------------------------------
    # Internal helpers (must be called with lock held)
    # ------------------------------------------------------------------

    def _reset_unlocked(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0

    def _maybe_transition_to_half_open(self) -> None:
        if self._state != CircuitState.OPEN:
            return
        elapsed = self._time_func() - self._last_failure_time
        if elapsed >= self._recovery_timeout:
            logger.info(
                "CircuitBreaker transitioning OPEN -> HALF_OPEN "
                "(recovery_timeout=%.1fs elapsed)",
                self._recovery_timeout,
            )
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
