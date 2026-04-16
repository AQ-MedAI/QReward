"""Sliding window rate limiter implementation."""

import asyncio
import bisect
import threading
import time
from typing import Optional


class LimiterPool:
    """Sliding window rate limiter with both sync and async support."""

    # Global lock for protecting global pool
    global_lock = threading.Lock()

    # Global pool dictionary, storing different pool instances by key
    global_limiter_pool: dict = {}

    @classmethod
    def get_pool(
        cls, key: str, rate: int, window: float
    ) -> Optional["LimiterPool"]:
        """Get or create a limiter pool instance for the given key.

        Uses singleton pattern to ensure one pool per key.

        Args:
            key: Unique identifier for the pool
            rate: Max requests allowed in window
            window: Window duration in seconds

        Returns:
            LimiterPool instance or None if rate/window is invalid
        """
        if rate <= 0 or window <= 0:
            return None
        with cls.global_lock:
            if key not in cls.global_limiter_pool:
                cls.global_limiter_pool[key] = cls(rate=rate, window=window)
            return cls.global_limiter_pool[key]

    def __init__(self, rate: int, window: float, clock=time.monotonic):
        """Initialize sliding window rate limiter.

        Args:
            rate: Max requests allowed in window
            window: Window duration in seconds
            clock: Time function, defaults to time.monotonic
        """
        if rate <= 0 or window <= 0:
            raise ValueError("rate / window must be positive")
        self.rate = rate
        self.window = float(window)
        self._clock = clock
        # Timestamp list, monotonically increasing
        self._times: list[float] = []
        # Condition variable for efficient sync waiting (replaces busy-wait)
        self._condition = threading.Condition(threading.RLock())
        # Alias for backward compatibility — the underlying lock
        self._lock = self._condition
        # Async lock
        self._aio_lock = asyncio.Lock()

    def allow(self, timeout: Optional[float] = None) -> bool:
        """Synchronously acquire a token.

        Uses threading.Condition to efficiently wait for token availability
        instead of busy-waiting with time.sleep.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            True if token acquired, False if timeout
        """
        deadline = None if timeout is None else self._clock() + timeout
        with self._condition:
            while True:
                ok = self._check_and_add()
                if ok:
                    self._condition.notify_all()
                    return True
                sleep_t = self._sleep_time()
                if deadline and self._clock() + sleep_t > deadline:
                    return False
                self._condition.wait(timeout=sleep_t)

    async def async_allow(self, timeout: Optional[float] = None) -> bool:
        """Asynchronously acquire a token.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            True if token acquired, False if timeout
        """
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            async with self._aio_lock:
                ok = self._check_and_add()
                if ok:
                    return True
                sleep_t = self._sleep_time()
            if deadline and self._clock() + sleep_t > deadline:
                return False
            await asyncio.sleep(sleep_t)

    def _check_and_add(self) -> bool:
        """Check if window is full and add timestamp if not.

        Must be called while holding lock.

        Returns:
            True if request allowed, False if window full
        """
        now = self._clock()
        cutoff = now - self.window
        # Clean expired timestamps
        idx = bisect.bisect_left(self._times, cutoff)
        self._times = self._times[idx:]
        # Check if window is full
        if len(self._times) < self.rate:
            bisect.insort(self._times, now)
            return True
        return False

    def _sleep_time(self) -> float:
        """Calculate time to wait until earliest record expires.

        Must be called while holding lock.

        Returns:
            Sleep time in seconds
        """
        if not self._times:
            return 0.01
        earliest = self._times[0]
        return max(0.0, earliest + self.window - self._clock())
