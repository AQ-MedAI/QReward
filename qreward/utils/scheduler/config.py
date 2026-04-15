"""Configuration for schedule decorator.

Example:
    >>> from qreward.utils.scheduler.config import ScheduleConfig
    >>> config = ScheduleConfig(timeout=30, retry_times=3, retry_interval=2.0)
    >>> config.timeout
    30
"""

import threading
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, List, Tuple, Type, Union

from .priority_queue import Priority

# Sentinel for distinguishing None from unset
_sentinel_none = object()

# Minimum allowed proportion for hedged requests
MIN_HEDGE_PROPORTION = 1e-6

# Minimum fallback wait time (seconds) when computed wait is zero or negative
MIN_WAIT_TIME = 0.01


@dataclass
class ScheduleConfig:
    """Configuration for schedule decorator.

    Attributes:
        timeout: Timeout in seconds, 0 means no timeout
        hedged_request_time: Time to trigger hedged requests in seconds
        hedged_request_proportion: Max proportion of hedged requests
        hedged_request_max_times: Max number of hedged requests
        speed_up_max_multiply: Max speed up multiplier
        retry_times: Max retry times (not including first call)
        retry_interval: Retry interval in seconds
        limit_size: Rate limit size (requests per window)
        limit_window: Rate limit window in seconds
        key_func: Function to generate key for pool identification
        exception_types: Exception types to catch and retry
        default_result: Default result on failure (callable or value)
        debug: Enable debug logging
        adaptive_limit: Enable adaptive rate limiting (default False).
        adaptive_limit_min: Minimum rate limit floor.
        adaptive_limit_max: Maximum rate limit ceiling.
        adaptive_error_threshold: Error rate threshold to trigger slowdown.
        adaptive_latency_threshold: Avg latency threshold (seconds).
        adaptive_window_seconds: Sliding window duration for statistics.
        priority: Default task priority (Priority.HIGH / NORMAL / LOW or 0-9).
    """

    timeout: float = 0
    hedged_request_time: float = 0
    hedged_request_proportion: float = 0.05
    hedged_request_max_times: int = 2
    speed_up_max_multiply: int = 5
    retry_times: int = 0
    retry_interval: float = 1
    limit_size: int = 0
    limit_window: float = 1.0
    key_func: Any = field(default=_sentinel_none)
    exception_types: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (
        BaseException
    )
    default_result: Any = field(default=_sentinel_none)
    debug: bool = False
    adaptive_limit: bool = False
    adaptive_limit_min: int = 10
    adaptive_limit_max: int = 500
    adaptive_error_threshold: float = 0.3
    adaptive_latency_threshold: float = 5.0
    adaptive_window_seconds: float = 10.0
    priority: int = Priority.NORMAL

    def __post_init__(self):
        # Validate timeout
        if self.timeout < 0:
            raise ValueError("timeout must be >= 0")

        # Validate retry_interval
        if self.retry_interval < 0:
            raise ValueError("retry_interval must be >= 0")

        # Normalize exception_types to tuple
        if self.exception_types is None:
            self.exception_types = (BaseException,)
        elif not isinstance(self.exception_types, tuple):
            self.exception_types = (self.exception_types,)

        # Validate hedged_request_proportion
        if self.hedged_request_time > 0 and (
            self.hedged_request_proportion <= MIN_HEDGE_PROPORTION
            or self.hedged_request_proportion > 1.0
        ):
            raise ValueError(
                f"hedged_request_proportion must be in ({MIN_HEDGE_PROPORTION}, 1]"
            )

    @property
    def hedged_request_multiply(self) -> float:
        """Calculate multiply factor for hedged requests."""
        if self.hedged_request_time > 0 and self.hedged_request_proportion > 0:
            return 1 / self.hedged_request_proportion - 1
        return 0

    def adjust_wait_time(
        self, basic_wait_time: float, has_wait_time: float, max_wait_time: float
    ) -> float:
        """Calculate max wait time considering timeout.

        Args:
            basic_wait_time: Basic wait time
            has_wait_time: Already waited time
            max_wait_time: Maximum wait time (timeout)

        Returns:
            Adjusted wait time
        """
        if basic_wait_time < 0:
            basic_wait_time = MIN_WAIT_TIME
        if max_wait_time <= 0 or basic_wait_time + has_wait_time < max_wait_time:
            return basic_wait_time
        if has_wait_time > max_wait_time:
            return MIN_WAIT_TIME
        return max_wait_time - has_wait_time

    def get_max_wait_time(
        self, basic_wait_time: float, has_wait_time: float, max_wait_time: float
    ) -> float:
        warnings.warn(
            "get_max_wait_time is deprecated, use adjust_wait_time instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.adjust_wait_time(basic_wait_time, has_wait_time, max_wait_time)

    # --- Hot-reload support ---

    _change_callbacks: List[Callable[["ScheduleConfig"], None]] = field(
        default_factory=list, repr=False, compare=False,
    )
    _update_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False,
    )

    def on_change(self, callback: Callable[["ScheduleConfig"], None]) -> None:
        """Register a callback invoked after config is updated.

        Args:
            callback: Function receiving the updated config instance.
        """
        self._change_callbacks.append(callback)

    def update(self, **kwargs: Any) -> None:
        """Atomically update config fields and notify listeners.

        Only known dataclass fields are updated; unknown keys are ignored.
        Validation is re-run after update.

        Args:
            **kwargs: Field name → new value pairs.
        """
        with self._update_lock:
            for key, value in kwargs.items():
                if hasattr(self, key) and key not in ("_change_callbacks", "_update_lock"):
                    setattr(self, key, value)
            self.__post_init__()
        for cb in self._change_callbacks:
            cb(self)

    def snapshot(self) -> dict[str, Any]:
        """Return a dict snapshot of the current config values."""
        from dataclasses import fields as dc_fields
        return {
            f.name: getattr(self, f.name)
            for f in dc_fields(self)
            if not f.name.startswith("_")
        }