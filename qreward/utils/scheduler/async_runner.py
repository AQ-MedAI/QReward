"""Async runner implementation for asynchronous task execution."""

import asyncio
import logging
from typing import Any, Callable, List, Optional, Sequence, Tuple

from .base import BaseRunner, _CancelledErrorGroups
from .config import ScheduleConfig, _sentinel_none
from .context import ExecutionContext

logger = logging.getLogger(__name__)


class AsyncRunner(BaseRunner):
    """Async runner implementation."""

    def create_task(self, func: Callable, *args, **kwargs) -> asyncio.Task:
        """Create an asyncio task."""
        return asyncio.create_task(func(*args, **kwargs))

    def get_task_result(self, task: asyncio.Task) -> Any:
        """Get result from a completed asyncio task."""
        return task.result()

    def get_task_exception(self, task: asyncio.Task) -> Optional[BaseException]:
        """Get exception from a completed asyncio task."""
        return task.exception()

    def is_task_cancelled(self, task: asyncio.Task) -> bool:
        """Check if an asyncio task was cancelled."""
        return task.cancelled()

    async def _cancel_tasks(
        self,
        pending: Sequence[asyncio.Task],
        done: List[asyncio.Task],
        retry_interval: float,
    ) -> None:  # pragma: no cover
        """Cancel pending tasks and consume done tasks.

        Args:
            pending: Pending tasks to cancel.
            done: Done tasks to consume.
            retry_interval: Time to wait for cancellation.
        """
        while done:
            try:
                done.pop()
            except _CancelledErrorGroups:
                pass

        if pending:
            for task in pending:
                if not task.done():
                    task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=retry_interval if retry_interval > 0 else None,
                )
            except _CancelledErrorGroups:
                pass

    async def execute_impl(
        self,
        context: ExecutionContext,
        config: ScheduleConfig,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Async execution implementation.

        Args:
            context: Execution context.
            config: Schedule configuration.
            *args: Function arguments.
            **kwargs: Function keyword arguments.

        Returns:
            Function result.
        """
        run_tasks: List[asyncio.Task] = []

        try:
            while not context.finish and (
                context.cur_times <= config.retry_times or len(run_tasks) > 0
            ):
                # 1. Submit new tasks if allowed
                if context.can_submit_task(len(run_tasks)):
                    limiter_timeout = context.get_limiter_timeout(len(run_tasks))

                    if not context.limiter or await context.limiter.async_allow(
                        limiter_timeout if limiter_timeout > 0 else None
                    ):
                        if context.is_hedge_submit(len(run_tasks)):  # pragma: no cover
                            context.record_hedge()
                        elif context.result_exception is not None:  # pragma: no cover
                            context.record_exception(context.result_exception)
                            context.result_exception = None

                        run_tasks.append(
                            asyncio.create_task(context.func(*args, **kwargs))
                        )
                        context.mark_task_submitted()

                # 2. Wait for tasks
                done, pending = set(), set()
                if run_tasks:  # pragma: no branch
                    cur_timeout = context.compute_timeout(len(run_tasks))
                    if cur_timeout > 0:
                        done, pending = await asyncio.wait(
                            run_tasks,
                            timeout=cur_timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    else:  # pragma: no cover
                        done, pending = await asyncio.wait(
                            run_tasks, return_when=asyncio.FIRST_COMPLETED
                        )

                # 3. Process results
                can_add_speed_up = context.can_increase_speed()
                cancel_wait = self._compute_cancel_wait(config, context)

                for finished in list(done):
                    if finished.cancelled():  # pragma: no cover
                        run_tasks.remove(finished)
                        continue

                    exception = finished.exception()
                    if exception is None:
                        # Success
                        await self._cancel_tasks(
                            list(pending), list(done), cancel_wait
                        )
                        context.result = finished.result()
                        context.result_exception = None
                        context.finish = True
                        run_tasks.remove(finished)
                        return context.result

                    # Handle exception
                    run_tasks.remove(finished)
                    retryable, increased = self._handle_exception(
                        context, config, finished, can_add_speed_up
                    )
                    if increased:
                        can_add_speed_up = False

                    if retryable:
                        await asyncio.sleep(cancel_wait)
                        break
                    else:
                        await self._cancel_tasks(
                            list(pending), list(done), cancel_wait
                        )
                        context.finish = True
                        break

                # 4. Check timeout
                if config.timeout > 0 and context.elapsed > config.timeout:
                    context.result_exception = asyncio.TimeoutError(
                        f"execute more than {config.timeout} seconds"
                    )
                    await self._cancel_tasks(
                        list(pending) + run_tasks, [], cancel_wait
                    )
                    context.finish = True

            # 5. Return result
            return self._return_result(context, config, args, kwargs)

        finally:
            context.running_task_pool.add(-1)
            if config.debug:
                self._log_finish(context)
