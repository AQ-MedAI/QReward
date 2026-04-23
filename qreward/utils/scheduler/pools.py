"""Running task pool for concurrency monitoring."""

import threading
import time
import warnings
from collections import OrderedDict

# Default number of time windows to track historical peak concurrency
DEFAULT_WINDOW_MAX_SIZE = 12

# Default interval (seconds) for each time window
DEFAULT_WINDOW_INTERVAL = 60

# Default concurrency threshold below which tasks are always allowed
DEFAULT_THRESHOLD = 3


class RunningTaskPool:
    """Manager for monitoring and controlling task concurrency."""

    # Global lock for protecting global pool
    global_lock = threading.Lock()

    # Global pool dictionary, storing different pool instances by key
    global_task_pool: dict = {}

    @classmethod
    def get_pool(
        cls,
        key: str,
        window_max_size: int = DEFAULT_WINDOW_MAX_SIZE,
        window_interval: int = DEFAULT_WINDOW_INTERVAL,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> "RunningTaskPool":
        """Get or create a task pool instance for the given key.

        Uses singleton pattern to ensure one pool per key.

        Args:
            key: Unique identifier for the pool
            window_max_size: Max number of time windows, default 12
            window_interval: Interval of each window in seconds, default 60
            threshold: Concurrency threshold, default 3

        Returns:
            RunningTaskPool instance
        """
        with cls.global_lock:
            if key not in cls.global_task_pool:
                cls.global_task_pool[key] = cls(
                    window_max_size=window_max_size,
                    window_interval=window_interval,
                    threshold=threshold,
                )
            return cls.global_task_pool[key]

    def __init__(
        self,
        window_max_size: int = DEFAULT_WINDOW_MAX_SIZE,
        window_interval: int = DEFAULT_WINDOW_INTERVAL,
        threshold: int = DEFAULT_THRESHOLD,
    ):
        """Initialize task pool.

        Args:
            window_max_size: Max number of time windows
            window_interval: Interval of each window in seconds
            threshold: Concurrency threshold
        """
        self._value = 0
        self._max_size_map = OrderedDict()
        self._window_max_size = window_max_size
        self._window_interval = window_interval
        self._threshold = threshold
        self._lock = threading.Lock()

    def add(self, value: int = 1) -> int:
        """Update current running task count and record historical peak.

        Args:
            value: Value to change

        Returns:
            Current running task count
        """
        with self._lock:
            self._value += value
            key = int(time.time()) // self._window_interval
            if key in self._max_size_map:
                if self._max_size_map[key] < self._value:
                    self._max_size_map[key] = self._value
            else:
                while len(self._max_size_map) >= self._window_max_size:
                    self._max_size_map.popitem(last=False)
                self._max_size_map[key] = self._value
            return self._value

    def can_submit(self, multiply: float = 1) -> bool:
        """Check if current task status allows execution.

        Logic:
        1. If current task count is below threshold, allow execution
        2. If historical max exceeds current value * multiply, system is
            overloaded

        Args:
            multiply: Multiplier for load calculation

        Returns:
            True if can continue, False if should throttle
        """
        with self._lock:
            if self._value <= self._threshold:
                return True
            max_value = 0
            for v in self._max_size_map.values():
                if v > max_value:
                    max_value = v
            if max_value > self._value * multiply:
                return True
            return False

    def less_than(self, multiply: float = 1) -> bool:
        warnings.warn(
            "less_than is deprecated, use can_submit instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.can_submit(multiply)
