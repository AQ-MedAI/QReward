"""Priority Queue Example

Demonstrates how to assign different priority levels to scheduled tasks.
Higher-priority tasks are executed before lower-priority ones when resources
are contended.

Priority levels:
  Priority.HIGH   = 0  (highest)
  Priority.NORMAL = 5  (default)
  Priority.LOW    = 9  (lowest)

The priority queue also includes starvation protection: tasks waiting too long
are automatically promoted to prevent indefinite delays.
"""

import asyncio
import time

from qreward.utils import schedule
from qreward.utils.scheduler import Priority


# --- Example 1: High-priority task ---
@schedule(priority=Priority.HIGH, retry_times=0)
async def critical_task(task_id: int):
    await asyncio.sleep(0.1)
    return f"CRITICAL-{task_id}"


# --- Example 2: Normal-priority task (default) ---
@schedule(priority=Priority.NORMAL, retry_times=0)
async def normal_task(task_id: int):
    await asyncio.sleep(0.1)
    return f"NORMAL-{task_id}"


# --- Example 3: Low-priority task ---
@schedule(priority=Priority.LOW, retry_times=0)
async def background_task(task_id: int):
    await asyncio.sleep(0.1)
    return f"BACKGROUND-{task_id}"


async def demo_priority_levels():
    print("=== Priority Levels Demo ===\n")
    print(f"  Priority.HIGH   = {Priority.HIGH}")
    print(f"  Priority.NORMAL = {Priority.NORMAL}")
    print(f"  Priority.LOW    = {Priority.LOW}\n")

    # Launch tasks with different priorities
    tasks = []
    for i in range(3):
        tasks.append(background_task(i))
    for i in range(3):
        tasks.append(normal_task(i))
    for i in range(3):
        tasks.append(critical_task(i))

    results = await asyncio.gather(*tasks)
    for result in results:
        print(f"  Completed: {result}")


# --- Example 4: Custom numeric priority ---
@schedule(priority=2, retry_times=0)
async def high_priority_custom(task_id: int):
    await asyncio.sleep(0.05)
    return f"PRIORITY-2: {task_id}"


@schedule(priority=7, retry_times=0)
async def low_priority_custom(task_id: int):
    await asyncio.sleep(0.05)
    return f"PRIORITY-7: {task_id}"


async def demo_custom_priority():
    print("\n\n=== Custom Numeric Priority Demo ===\n")
    tasks = [
        low_priority_custom(1),
        high_priority_custom(1),
        low_priority_custom(2),
        high_priority_custom(2),
    ]
    results = await asyncio.gather(*tasks)
    for result in results:
        print(f"  Completed: {result}")


# --- Example 5: Using PriorityTaskQueue directly ---
def demo_priority_queue_direct():
    from qreward.utils.scheduler import PriorityTaskQueue

    print("\n\n=== Direct PriorityTaskQueue Usage ===\n")
    queue = PriorityTaskQueue(starvation_threshold=60.0)

    # Add tasks with different priorities
    queue.put("low-priority-job", priority=Priority.LOW)
    queue.put("normal-priority-job", priority=Priority.NORMAL)
    queue.put("high-priority-job", priority=Priority.HIGH)

    print(f"  Queue size: {queue.queue_size}")

    # Tasks come out in priority order (lowest number = highest priority)
    while not queue.is_empty:
        item = queue.get()
        print(f"  Dequeued: {item}")

    print(f"  Queue empty: {queue.is_empty}")


if __name__ == "__main__":
    asyncio.run(demo_priority_levels())
    asyncio.run(demo_custom_priority())
    demo_priority_queue_direct()
