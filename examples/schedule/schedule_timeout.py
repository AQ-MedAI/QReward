"""Timeout Control Example

Demonstrates how to use the timeout parameter to set a maximum execution time
for scheduled functions. When the total execution time (including retries)
exceeds the timeout, the function is cancelled and either raises
asyncio.TimeoutError or returns the default_result.

Key behaviors:
  - timeout=0 means no timeout (default)
  - timeout > 0 sets a wall-clock deadline for the entire execution
  - Retries are automatically stopped when the deadline is reached
  - Works with both async and sync functions
"""

import asyncio
import time

from qreward.utils import schedule


# --- Example 1: Basic timeout ---
# The function sleeps for 3 seconds but the timeout is 2 seconds.
# Since no default_result is set, asyncio.TimeoutError is raised.
@schedule(timeout=2, retry_times=0)
async def slow_task():
    await asyncio.sleep(3)
    return "This will never be returned"


async def demo_basic_timeout():
    print("=== Basic Timeout Demo ===\n")
    try:
        await slow_task()
    except asyncio.TimeoutError:
        print("  Task timed out as expected (2s deadline, 3s sleep)\n")


# --- Example 2: Timeout with default result ---
# When timeout is reached, the default_result is returned instead of raising.
@schedule(timeout=2, retry_times=3, default_result="timeout_fallback")
async def slow_task_with_fallback():
    await asyncio.sleep(5)
    return "This will never be returned"


async def demo_timeout_with_fallback():
    print("=== Timeout with Default Result ===\n")
    start = time.time()
    result = await slow_task_with_fallback()
    elapsed = time.time() - start
    print(f"  Result: {result}")
    print(f"  Elapsed: {elapsed:.1f}s (timeout was 2s)\n")


# --- Example 3: Timeout with retries ---
# Retries are attempted within the timeout window. Once the deadline is
# reached, no more retries are started.
@schedule(timeout=3, retry_times=10, retry_interval=0.5, default_result="gave_up")
async def flaky_with_timeout(attempt_tracker: list):
    attempt_tracker.append(1)
    await asyncio.sleep(0.8)
    raise ConnectionError("Service unavailable")


async def demo_timeout_with_retries():
    print("=== Timeout Limits Retries ===\n")
    tracker = []
    result = await flaky_with_timeout(tracker)
    print(f"  Attempts made: {len(tracker)} (out of max 11)")
    print(f"  Result: {result}")
    print(f"  (Retries stopped because 3s timeout was reached)\n")


# --- Example 4: Sync function with timeout ---
@schedule(timeout=2, retry_times=0, default_result="sync_timeout")
def sync_slow_task():
    time.sleep(3)
    return "never returned"


def demo_sync_timeout():
    print("=== Sync Timeout Demo ===\n")
    start = time.time()
    result = sync_slow_task()
    elapsed = time.time() - start
    print(f"  Result: {result}")
    print(f"  Elapsed: {elapsed:.1f}s\n")


# --- Example 5: No timeout (timeout=0) ---
@schedule(timeout=0, retry_times=0)
async def no_timeout_task():
    await asyncio.sleep(0.5)
    return "completed without timeout"


async def demo_no_timeout():
    print("=== No Timeout (timeout=0) ===\n")
    result = await no_timeout_task()
    print(f"  Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(demo_basic_timeout())
    asyncio.run(demo_timeout_with_fallback())
    asyncio.run(demo_timeout_with_retries())
    demo_sync_timeout()
    asyncio.run(demo_no_timeout())
