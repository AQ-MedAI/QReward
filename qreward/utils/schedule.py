"""Compatibility layer — re-exports from qreward.utils.scheduler.

This module preserves backward compatibility so that existing code using
from qreward.utils.schedule import ... continues to work.  The canonical
implementation now lives in qreward.utils.scheduler.
"""

import asyncio
import concurrent.futures
from collections.abc import Sequence
from typing import List, Optional

from qreward.utils.scheduler import (  # noqa: F401  — public re-exports
    LimiterPool,
    RunningTaskPool,
    schedule,
)
from qreward.utils.scheduler.base import _CancelledErrorGroups  # noqa: F401
from qreward.utils.scheduler.config import _sentinel_none  # noqa: F401
from qreward.utils.scheduler.overload import OverloadChecker


# ---------------------------------------------------------------------------
# Legacy standalone helpers kept for backward-compatible test imports.
# The scheduler/ package uses class methods instead, but existing tests
# reference these free functions directly.
# ---------------------------------------------------------------------------


async def _cancel_async_task(
    pending: Sequence[asyncio.Task],
    done: List[asyncio.Task],
    retry_interval: Optional[float],
) -> None:
    """Cancel remaining async tasks (legacy standalone helper)."""
    while len(done) > 0:
        try:
            _ = done.pop()
        except _CancelledErrorGroups:
            pass
    if len(pending) > 0:
        for task in pending:
            if not task.done():
                task.cancel()
        try:
            await asyncio.wait_for(
                fut=asyncio.gather(*pending, return_exceptions=True),
                timeout=retry_interval,
            )
        except _CancelledErrorGroups:
            pass


def _cancel_sync_task(
    not_done: Sequence[concurrent.futures.Future],
    done: List,
    retry_interval: Optional[float],
) -> None:
    """Cancel remaining sync tasks (legacy standalone helper)."""
    while len(done) > 0:
        try:
            _ = done.pop()
        except _CancelledErrorGroups:
            pass
    for task in not_done:
        if not task.done():
            task.cancel()
    if len(not_done) > 0:
        try:
            concurrent.futures.wait(
                not_done,
                timeout=retry_interval,
                return_when=concurrent.futures.ALL_COMPLETED,
            )
        except _CancelledErrorGroups:
            pass


def _overload_check(exception: BaseException) -> bool:
    """Check if exception indicates server overload (legacy standalone helper)."""
    return OverloadChecker.check(exception)


def _get_max_wait_time(
    basic_wait_time: float,
    has_wait_time: float,
    max_wait_time: float,
) -> float:
    """Calculate max wait time considering timeout (legacy standalone helper).

    Delegates to ScheduleConfig.get_max_wait_time with a dummy config instance.
    """
    if basic_wait_time < 0:
        basic_wait_time = 0.01
    if max_wait_time <= 0 or basic_wait_time + has_wait_time < max_wait_time:
        return basic_wait_time
    if has_wait_time > max_wait_time:
        return 0.01
    return max_wait_time - has_wait_time


__all__ = [
    "LimiterPool",
    "RunningTaskPool",
    "_CancelledErrorGroups",
    "_cancel_async_task",
    "_cancel_sync_task",
    "_get_max_wait_time",
    "_overload_check",
    "_sentinel_none",
    "schedule",
]
