"""Execution context for managing state during a single schedule
invocation."""

import time
from typing import Any, Callable, List, Optional

from .config import ScheduleConfig
from .limiter import LimiterPool
from .metrics import ScheduleMetrics
from .pools import RunningTaskPool

# Exponent base and step for hedged request threshold calculation:
#   threshold = pool_size + multiply ** (
#       HEDGE_EXPONENT_BASE + times * HEDGE_EXPONENT_STEP
#   )
HEDGE_EXPONENT_BASE = 0.5
HEDGE_EXPONENT_STEP = 0.5

# Minimum timeout (seconds) returned by get_limiter_timeout to avoid zero-waits
MIN_LIMITER_TIMEOUT = 0.001


class ExecutionContext:
    """Manages execution state for a single schedule invocation."""

    def __init__(
        self,
        func: Callable,
        config: ScheduleConfig,
        key: str,
        running_task_pool: RunningTaskPool,
        limiter: Optional[LimiterPool],
    ):
        """Initialize execution context.

        Args:
            func: Function being decorated
            config: Schedule configuration
            key: Pool key
            running_task_pool: Running task pool instance
            limiter: Rate limiter instance or None
        """
        self.func = func
        self.config = config
        self.key = key
        self.running_task_pool = running_task_pool
        self.limiter = limiter
        self.priority: int = config.priority

        # Execution state
        self.cur_times = 0
        self.cur_speed_up_multiply = 0
        self.start_time = time.perf_counter()
        self.last_submit_time = self.start_time
        self.cur_hedged_request_times = 1

        # Results
        self.result: Any = None
        self.result_exception: Optional[BaseException] = None
        self.result_exception_list: List[str] = []

        # Control
        self.finish = False

    def can_submit_task(self, run_tasks_count: int) -> bool:
        """Check if a new task can be submitted.

        Args:
            run_tasks_count: Current number of running tasks

        Returns:
            True if can submit
        """
        if self.cur_times > self.config.retry_times:
            return False

        # Always allow if no running tasks
        if run_tasks_count <= 0:
            return True

        # Allow if under speed up multiplier
        if run_tasks_count < self.cur_speed_up_multiply:
            if self.running_task_pool.can_submit(
                run_tasks_count + 1
            ):
                return True

        # Allow hedged request
        if self._should_hedge(run_tasks_count):
            return True

        return False

    def _should_hedge(self, run_tasks_count: int) -> bool:
        """Check if hedged request should be submitted.

        Args:
            run_tasks_count: Current number of running tasks

        Returns:
            True if should hedge
        """
        if self.config.hedged_request_time <= 0:
            return False

        if self.cur_hedged_request_times > (
            self.config.hedged_request_max_times
        ):
            return False

        time_since_last = (
            time.perf_counter() - self.last_submit_time
        )
        if not (
            self.config.hedged_request_time < time_since_last
            or self.cur_hedged_request_times > 1
        ):
            return False

        threshold = run_tasks_count + (
            self.config.hedged_request_multiply ** (
                HEDGE_EXPONENT_BASE
                + self.cur_hedged_request_times * HEDGE_EXPONENT_STEP
            )
        )
        return self.running_task_pool.can_submit(threshold)

    def is_hedge_submit(self, run_tasks_count: int) -> bool:
        """Check if current submission is a hedge.

        Args:
            run_tasks_count: Current number of running tasks

        Returns:
            True if this is a hedge submission
        """
        if self.config.hedged_request_time <= 0:
            return False

        if self.cur_speed_up_multiply > run_tasks_count:
            return False

        time_since_last = (
            time.perf_counter() - self.last_submit_time
        )
        if not (
            self.config.hedged_request_time < time_since_last
            or self.cur_hedged_request_times > 1
        ):
            return False

        if self.cur_hedged_request_times > (
            self.config.hedged_request_max_times
        ):
            return False

        threshold = run_tasks_count + (
            self.config.hedged_request_multiply ** (
                HEDGE_EXPONENT_BASE
                + self.cur_hedged_request_times * HEDGE_EXPONENT_STEP
            )
        )
        return self.running_task_pool.can_submit(threshold)

    def compute_timeout(self, run_tasks_count: int) -> float:
        """Compute timeout for current wait.

        Args:
            run_tasks_count: Current number of running tasks

        Returns:
            Timeout in seconds (0 means no timeout)
        """
        cur_timeout = 0.0

        # Base timeout
        if self.config.timeout > 0:
            cur_timeout = (
                self.start_time
                + self.config.timeout
                - time.perf_counter()
            )

        # Hedge request timeout
        if (
            self.cur_hedged_request_times
            <= self.config.hedged_request_max_times
            and self.config.hedged_request_time > 0
        ):
            hedge_timeout = (
                self.start_time
                + self.config.hedged_request_time
                - time.perf_counter()
            )
            if cur_timeout == 0 or hedge_timeout < cur_timeout:
                cur_timeout = hedge_timeout

        # Speed up timeout (retry_interval)
        if run_tasks_count < self.cur_speed_up_multiply:
            if self.cur_times < self.config.retry_times:
                if (
                    cur_timeout > self.config.retry_interval
                    or cur_timeout == 0
                ):
                    cur_timeout = self.config.retry_interval

        if cur_timeout < 0:
            cur_timeout = self.config.retry_interval

        return cur_timeout

    def get_limiter_timeout(self, run_tasks_count: int) -> float:
        """Get timeout for rate limiter.

        Args:
            run_tasks_count: Current number of running tasks

        Returns:
            Timeout in seconds (0 means no timeout)
        """
        if run_tasks_count == 0:
            if self.config.timeout > 0:
                return max(
                    MIN_LIMITER_TIMEOUT,
                    self.config.timeout - self.elapsed
                )
            return 0

        cur_timeout = self.config.retry_interval
        if self.config.timeout > 0:
            remaining = self.config.timeout - self.elapsed
            if remaining < self.config.retry_interval:
                cur_timeout = max(
                    MIN_LIMITER_TIMEOUT, remaining
                )
        return cur_timeout

    @property
    def elapsed(self) -> float:
        """Get elapsed time since start."""
        return time.perf_counter() - self.start_time

    @property
    def is_timeout(self) -> bool:
        """Check if execution has timed out."""
        if self.config.timeout <= 0:
            return False
        return self.elapsed > self.config.timeout

    def record_exception(self, exception: BaseException):
        """Record exception info."""
        self.result_exception_list.append(
            f"{type(exception).__name__} {str(exception)}"
        )

    def record_hedge(self):
        """Record hedge request."""
        self.result_exception_list.append(f"hedged_request: {self.elapsed}")
        self.cur_hedged_request_times += 1

    def mark_task_submitted(self):
        """Mark that a task was submitted."""
        self.cur_times += 1
        self.last_submit_time = time.perf_counter()

    def can_increase_speed(self) -> bool:
        """Check if speed can be increased."""
        return self.cur_speed_up_multiply < self.config.speed_up_max_multiply

    def increase_speed(self):
        """Increase speed multiplier."""
        self.cur_speed_up_multiply += 1

    def reset_speed(self):
        """Reset speed multiplier (on overload)."""
        self.cur_speed_up_multiply = 0

    def build_metrics(self) -> ScheduleMetrics:
        """Build execution metrics from the current context state.

        Returns:
            ScheduleMetrics with aggregated execution statistics.
        """
        total_latency_ms = self.elapsed * 1000.0
        retry_count = max(0, self.cur_times - 1)
        failure_count = len(self.result_exception_list)
        success_count = 1 if self.result_exception is None else 0
        total_calls = self.cur_times
        avg_latency_ms = (
            total_latency_ms / total_calls if total_calls > 0 else 0.0
        )
        return ScheduleMetrics(
            total_calls=total_calls,
            success_count=success_count,
            failure_count=failure_count,
            retry_count=retry_count,
            total_latency_ms=total_latency_ms,
            avg_latency_ms=avg_latency_ms,
        )
