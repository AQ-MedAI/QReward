"""Main schedule decorator implementation."""

import atexit
import concurrent.futures
import functools
import inspect
import threading
from typing import (
    Any, Callable, List, Optional, Tuple, Type, Union,
)

from .adaptive_limiter import AdaptiveRateLimiter
from .async_runner import AsyncRunner
from .circuit_breaker import CircuitBreaker
from .config import ScheduleConfig, _sentinel_none
from .context import ExecutionContext
from .sync_runner import SyncRunner
from .limiter import LimiterPool
from .metrics import ScheduleMetrics
from .pools import RunningTaskPool
from .telemetry import TelemetryExporter

# Global registry for ThreadPoolExecutors created by sync schedule decorators.
# Protected by a lock to ensure thread safety during registration.
_executor_registry_lock = threading.Lock()
_executor_registry: List[concurrent.futures.ThreadPoolExecutor] = []
_atexit_registered = False


def _shutdown_executors() -> None:
    """Shutdown all registered ThreadPoolExecutors.

    Called automatically at process exit via atexit to prevent thread leaks.
    Uses wait=False to avoid blocking process shutdown.
    """
    with _executor_registry_lock:
        for executor in _executor_registry:
            executor.shutdown(wait=False)
        _executor_registry.clear()


def _register_executor(
    executor: concurrent.futures.ThreadPoolExecutor
) -> None:
    """Register a ThreadPoolExecutor for cleanup at process exit.

    Args:
        executor: The ThreadPoolExecutor to register.
    """
    global _atexit_registered
    with _executor_registry_lock:
        _executor_registry.append(executor)
        if not _atexit_registered:
            atexit.register(_shutdown_executors)
            _atexit_registered = True


def schedule(
    timeout: float = 0,
    hedged_request_time: float = 0,
    hedged_request_proportion: float = 0.05,
    hedged_request_max_times: int = 2,
    speed_up_max_multiply: int = 5,
    retry_times: int = 0,
    retry_interval: float = 1,
    limit_size: int = 0,
    limit_window: float = 1.0,
    key_func: object = _sentinel_none,
    exception_types: Union[
        Type[BaseException],
        Tuple[Type[BaseException], ...],
    ] = BaseException,
    default_result: object = _sentinel_none,
    debug: bool = False,
    metrics_callback: Optional[Callable[[ScheduleMetrics], None]] = None,
    circuit_breaker_threshold: int = 0,
    circuit_breaker_recovery: float = 30.0,
    adaptive_limit: bool = False,
    adaptive_limit_min: int = 10,
    adaptive_limit_max: int = 500,
    adaptive_error_threshold: float = 0.3,
    adaptive_latency_threshold: float = 5.0,
    adaptive_window_seconds: float = 10.0,
    priority: int = 5,
    telemetry_exporter: Optional[TelemetryExporter] = None,
):
    """Decorator for scheduling function execution with retry, hedging,
    rate limiting, etc.

    Args:
        timeout: Timeout in seconds, 0 means no timeout
        hedged_request_time: Time to trigger hedged requests
        hedged_request_proportion: Max proportion for hedged requests
        hedged_request_max_times: Max number of hedged requests
        speed_up_max_multiply: Max speed up multiplier
        retry_times: Max retry times (not including first call)
        retry_interval: Retry interval in seconds
        limit_size: Rate limit size
        limit_window: Rate limit window in seconds
        key_func: Function to generate pool key
        exception_types: Exceptions to catch and retry
        default_result: Default result on failure
        debug: Enable debug logging
        metrics_callback: Optional callback invoked after each execution
            with a ScheduleMetrics instance containing execution statistics
        circuit_breaker_threshold: Failure threshold to trip the circuit
            breaker. 0 disables the circuit breaker.
        circuit_breaker_recovery: Seconds before the breaker transitions
            from OPEN to HALF_OPEN for probe requests.
        adaptive_limit: Enable adaptive rate limiting.
        adaptive_limit_min: Minimum rate limit floor.
        adaptive_limit_max: Maximum rate limit ceiling.
        adaptive_error_threshold: Error rate threshold to trigger slowdown.
        adaptive_latency_threshold: Avg latency threshold to trigger slowdown.
        adaptive_window_seconds: Sliding window duration for statistics.
        priority: Task priority (0-9, lower = higher). Default 5 (NORMAL).
        telemetry_exporter: Optional TelemetryExporter for OTel metrics export.

    Returns:
        Decorated function
    """
    config = ScheduleConfig(
        timeout=timeout,
        hedged_request_time=hedged_request_time,
        hedged_request_proportion=hedged_request_proportion,
        hedged_request_max_times=hedged_request_max_times,
        speed_up_max_multiply=speed_up_max_multiply,
        retry_times=retry_times,
        retry_interval=retry_interval,
        limit_size=limit_size,
        limit_window=limit_window,
        key_func=key_func,
        exception_types=exception_types,
        default_result=default_result,
        debug=debug,
        adaptive_limit=adaptive_limit,
        adaptive_limit_min=adaptive_limit_min,
        adaptive_limit_max=adaptive_limit_max,
        adaptive_error_threshold=adaptive_error_threshold,
        adaptive_latency_threshold=adaptive_latency_threshold,
        adaptive_window_seconds=adaptive_window_seconds,
        priority=priority,
    )

    # Create adaptive rate limiter if enabled
    adaptive_limiter: Optional[AdaptiveRateLimiter] = None
    if adaptive_limit and limit_size > 0:
        adaptive_limiter = AdaptiveRateLimiter(
            initial_limit=limit_size,
            limit_min=adaptive_limit_min,
            limit_max=adaptive_limit_max,
            error_threshold=adaptive_error_threshold,
            latency_threshold=adaptive_latency_threshold,
            window_seconds=adaptive_window_seconds,
        )

    # Create circuit breaker if threshold > 0
    breaker: Optional[CircuitBreaker] = None
    if circuit_breaker_threshold > 0:
        breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            recovery_timeout=circuit_breaker_recovery,
        )

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):
            # Async function
            runner = AsyncRunner()

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Generate key
                key = func.__qualname__
                if key_func is not _sentinel_none and callable(key_func):
                    key = f"{func.__qualname__}.{key_func(*args, **kwargs)}"

                # Get pools
                if timeout <= 0:
                    running_task = RunningTaskPool.get_pool(key)
                else:
                    running_task = RunningTaskPool.get_pool(
                        key, window_interval=timeout
                    )
                limiter = LimiterPool.get_pool(key, limit_size, limit_window)

                # Check circuit breaker before execution
                if breaker is not None and not breaker.allow_request():
                    raise RuntimeError(
                        f"Circuit breaker is open for {func.__qualname__}"
                    )

                # Create context
                context = ExecutionContext(
                    func, config, key, running_task, limiter
                )
                running_task.add(1)

                # Execute
                result = await runner.execute_impl(
                    context, config, *args, **kwargs
                )

                # Record to adaptive limiter
                if adaptive_limiter is not None:
                    metrics = context.build_metrics()
                    adaptive_limiter.record(
                        latency_seconds=metrics.total_latency_ms / 1000.0,
                        success=context.result_exception is None,
                    )

                # Update circuit breaker based on execution outcome
                if breaker is not None:
                    if context.result_exception is not None:
                        breaker.record_failure()
                    else:
                        breaker.record_success()

                # Invoke metrics callback
                built_metrics = context.build_metrics()
                if metrics_callback is not None:
                    metrics_callback(built_metrics)
                if telemetry_exporter is not None:
                    built_metrics.export_to_otel(telemetry_exporter)

                return result

            return async_wrapper

        else:
            # Sync function
            runner = SyncRunner()
            executor = concurrent.futures.ThreadPoolExecutor()
            _register_executor(executor)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Generate key
                key = func.__qualname__
                if key_func is not _sentinel_none and callable(key_func):
                    key = f"{func.__qualname__}.{key_func(*args, **kwargs)}"

                # Get pools
                if timeout <= 0:
                    running_task = RunningTaskPool.get_pool(key)
                else:
                    running_task = RunningTaskPool.get_pool(
                        key, window_interval=timeout
                    )
                limiter = LimiterPool.get_pool(key, limit_size, limit_window)

                # Check circuit breaker before execution
                if breaker is not None and not breaker.allow_request():
                    raise RuntimeError(
                        f"Circuit breaker is open for {func.__qualname__}"
                    )

                # Create context and execute with shared executor
                runner.set_executor(executor)
                context = ExecutionContext(
                    func, config, key, running_task, limiter
                )
                running_task.add(1)

                result = runner.execute_impl(
                    context, config, *args, **kwargs
                )

                # Record to adaptive limiter
                if adaptive_limiter is not None:
                    metrics = context.build_metrics()
                    adaptive_limiter.record(
                        latency_seconds=metrics.total_latency_ms / 1000.0,
                        success=context.result_exception is None,
                    )

                # Update circuit breaker based on execution outcome
                if breaker is not None:
                    if context.result_exception is not None:
                        breaker.record_failure()
                    else:
                        breaker.record_success()

                # Invoke metrics callback
                built_metrics = context.build_metrics()
                if metrics_callback is not None:
                    metrics_callback(built_metrics)
                if telemetry_exporter is not None:
                    built_metrics.export_to_otel(telemetry_exporter)

                return result

            return sync_wrapper

    return decorator
