"""Base runner implementing template method pattern for sync/async execution."""

import asyncio
import concurrent.futures
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

from .config import ScheduleConfig, _sentinel_none
from .context import ExecutionContext
from .overload import OverloadChecker

logger = logging.getLogger(__name__)

# Cancelled error groups
_CancelledErrorGroups = (
    asyncio.CancelledError,
    asyncio.TimeoutError,
    concurrent.futures.CancelledError,
    TimeoutError,
)


class BaseRunner(ABC):
    """Abstract base runner using template method pattern.

    Subclasses implement the I/O primitives; shared pure-logic helpers
    live here so that sync and async runners share the same logic.
    """

    def __init__(self):
        self.overload_checker = OverloadChecker()

    # ------------------------------------------------------------------
    # Abstract I/O primitives
    # ------------------------------------------------------------------

    @abstractmethod
    def create_task(
        self, func: Callable, *args, **kwargs
    ) -> Union[asyncio.Task, concurrent.futures.Future]:
        """Create and submit a task for execution."""

    @abstractmethod
    def get_task_result(
        self, task: Union[asyncio.Task, concurrent.futures.Future]
    ) -> Any:
        """Get result from a completed task."""

    @abstractmethod
    def get_task_exception(
        self, task: Union[asyncio.Task, concurrent.futures.Future]
    ) -> Optional[BaseException]:
        """Get exception from a completed task, or None."""

    @abstractmethod
    def is_task_cancelled(
        self, task: Union[asyncio.Task, concurrent.futures.Future]
    ) -> bool:
        """Check if a task was cancelled."""

    # ------------------------------------------------------------------
    # Shared pure-logic helpers (no I/O, no await)
    # ------------------------------------------------------------------

    def _handle_exception(
        self,
        context: ExecutionContext,
        config: ScheduleConfig,
        finished: Union[asyncio.Task, concurrent.futures.Future],
        can_add_speed_up: bool,
    ) -> Tuple[bool, bool]:
        """Handle task exception.

        Args:
            context: Execution context.
            config: Schedule configuration.
            finished: Completed task with exception.
            can_add_speed_up: Whether speed can be increased.

        Returns:
            Tuple of (is_retryable, did_increase_speed).
        """
        exception = self.get_task_exception(finished)
        context.result_exception = exception
        context.record_exception(exception)

        # Never catch system-level exceptions
        if isinstance(exception, (KeyboardInterrupt, SystemExit)):
            raise exception

        if any(isinstance(exception, t) for t in config.exception_types):
            did_increase = False
            if can_add_speed_up:
                context.increase_speed()
                did_increase = True

            if self.overload_checker.check(exception):
                context.reset_speed()

            return True, did_increase

        return False, False

    @staticmethod
    def _compute_cancel_wait(
        config: ScheduleConfig, context: ExecutionContext
    ) -> float:
        """Compute wait time for cancel_tasks calls."""
        return config.adjust_wait_time(
            config.retry_interval, context.elapsed, config.timeout
        )

    @staticmethod
    def _log_finish(context: ExecutionContext) -> None:
        """Emit debug log on execution finish."""
        logger.debug(
            "[schedule] %s execute finish, "
            "executeTimes: %d, speedUpMultiply: %d, "
            "consumeTime: %.4f, exceptions: %s",
            context.func.__qualname__,
            context.cur_times,
            context.cur_speed_up_multiply,
            context.elapsed,
            context.result_exception_list,
        )

    @staticmethod
    def _return_result(
        context: ExecutionContext,
        config: ScheduleConfig,
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Return the final result, applying default_result if needed."""
        if context.result_exception is not None:
            if config.default_result is not _sentinel_none:
                if callable(config.default_result):
                    return config.default_result(*args, **kwargs)
                return config.default_result
            raise context.result_exception
        return context.result


# Re-export AsyncRunner and SyncRunner for backward compatibility.
from .async_runner import AsyncRunner  # noqa: F401, E402
from .sync_runner import SyncRunner  # noqa: F401, E402
