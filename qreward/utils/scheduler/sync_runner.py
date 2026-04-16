"""Sync runner module for synchronous task execution."""

import concurrent.futures
import logging
import time
from typing import Any, Callable, List, Optional, Sequence

from .base import BaseRunner, _CancelledErrorGroups
from .config import ScheduleConfig
from .context import ExecutionContext

logger = logging.getLogger(__name__)


class SyncRunner(BaseRunner):
    """Synchronous runner for executing scheduled tasks.

    Uses ThreadPoolExecutor to execute tasks synchronously,
    supporting retry, hedge, and rate limiting features.
    """

    def __init__(self):
        super().__init__()
        self._executor: Optional[
            concurrent.futures.ThreadPoolExecutor
        ] = None

    def set_executor(
        self, executor: concurrent.futures.ThreadPoolExecutor
    ):
        """Set the thread pool executor.

        Args:
            executor: Thread pool executor for task execution.
        """
        self._executor = executor

    def create_task(
        self, func: Callable, *args, **kwargs
    ) -> concurrent.futures.Future:
        """Create and submit a task to the executor."""
        if self._executor is None:
            raise RuntimeError("Executor not set")
        return self._executor.submit(func, *args, **kwargs)

    def get_task_result(
        self, task: concurrent.futures.Future
    ) -> Any:
        """Get the result of a completed task."""
        return task.result()

    def get_task_exception(
        self, task: concurrent.futures.Future
    ) -> Optional[BaseException]:
        """Get the exception from a failed task, or None."""
        return task.exception()

    def is_task_cancelled(
        self, task: concurrent.futures.Future
    ) -> bool:
        """Check if a task was cancelled."""
        return task.cancelled()

    def _cancel_tasks(
        self,
        pending: Sequence[concurrent.futures.Future],
        done: List,
        retry_interval: float,
    ) -> None:  # pragma: no cover
        """Cancel pending tasks and consume done tasks."""
        while done:
            try:
                done.pop()
            except _CancelledErrorGroups:
                pass

        for task in pending:
            if not task.done():
                task.cancel()

        if pending:
            try:
                concurrent.futures.wait(
                    pending,
                    timeout=retry_interval,
                    return_when=concurrent.futures.ALL_COMPLETED,
                )
            except _CancelledErrorGroups:
                pass

    def execute_impl(
        self,
        context: ExecutionContext,
        config: ScheduleConfig,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Sync execution implementation."""
        run_tasks: List[concurrent.futures.Future] = []

        try:
            while not context.finish and (
                context.cur_times <= config.retry_times or len(run_tasks) > 0
            ):
                # 1. Submit new tasks if allowed
                if context.can_submit_task(len(run_tasks)):
                    limiter_timeout = context.get_limiter_timeout(
                        len(run_tasks)
                    )

                    if not context.limiter or context.limiter.allow(
                        limiter_timeout if limiter_timeout > 0 else None
                    ):
                        if context.is_hedge_submit(
                            len(run_tasks)
                        ):  # pragma: no cover
                            context.record_hedge()
                        elif (
                            context.result_exception is not None
                        ):  # pragma: no cover
                            context.record_exception(context.result_exception)
                            context.result_exception = None

                        run_tasks.append(
                            self._executor.submit(
                                context.func, *args, **kwargs
                            )
                        )
                        context.mark_task_submitted()

                # 2. Wait for tasks
                done, pending = set(), set()
                if run_tasks:  # pragma: no branch
                    cur_timeout = context.compute_timeout(len(run_tasks))
                    if cur_timeout > 0:
                        done, pending = concurrent.futures.wait(
                            run_tasks,
                            timeout=cur_timeout,
                            return_when=concurrent.futures.FIRST_COMPLETED,
                        )
                    else:  # pragma: no cover
                        done, pending = concurrent.futures.wait(
                            run_tasks,
                            return_when=concurrent.futures.FIRST_COMPLETED,
                        )

                # 3. Process results
                can_add_speed_up = context.can_increase_speed()
                cancel_wait = self._compute_cancel_wait(config, context)

                for finished in list(done):
                    run_tasks.remove(finished)

                    if finished.cancelled():  # pragma: no cover
                        continue

                    exception = finished.exception()
                    if exception is None:
                        # Success
                        self._cancel_tasks(
                            list(pending), list(done), cancel_wait
                        )
                        context.result = finished.result()
                        context.result_exception = None
                        context.finish = True
                        break

                    # Handle exception
                    retryable, increased = self._handle_exception(
                        context, config, finished, can_add_speed_up
                    )
                    if increased:
                        can_add_speed_up = False

                    if retryable:
                        time.sleep(cancel_wait)
                        break
                    else:
                        self._cancel_tasks(
                            list(pending), [], cancel_wait
                        )
                        context.finish = True
                        break

                # 4. Check timeout
                if config.timeout > 0 and context.elapsed > config.timeout:
                    context.result_exception = TimeoutError(
                        f"execute more than {config.timeout} seconds"
                    )
                    self._cancel_tasks(
                        list(pending) + run_tasks, [], cancel_wait
                    )
                    context.finish = True

            # 5. Return result
            return self._return_result(context, config, args, kwargs)

        finally:
            context.running_task_pool.add(-1)
            if config.debug:
                self._log_finish(context)
