"""Thread-safe priority queue for scheduling tasks by priority level."""

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class Priority(IntEnum):
    """Task priority levels. Lower value = higher priority."""

    HIGH = 0
    NORMAL = 5
    LOW = 9


@dataclass(order=True)
class _PriorityEntry:
    """Internal entry for the priority heap.

    Ordering: (effective_priority, sequence) ensures stable FIFO within
    the same priority level.

    Attributes:
        effective_priority: Current priority (may be boosted by starvation
            protection).
        sequence: Monotonically increasing counter for FIFO ordering.
        enqueue_time: Timestamp when the entry was added (for starvation
            detection).
        item: The actual payload (excluded from ordering).
        cancelled: Whether this entry has been cancelled.
    """

    effective_priority: int
    sequence: int
    enqueue_time: float = field(compare=False)
    item: Any = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


class PriorityTaskQueue:
    """Thread-safe priority queue with starvation protection.

    Tasks are dequeued in priority order (lower value = higher priority).
    Within the same priority, tasks follow FIFO order.

    Starvation protection: tasks waiting longer than ``starvation_threshold``
    seconds are automatically promoted to HIGH priority on the next ``get``.

    Example:
        >>> queue = PriorityTaskQueue(starvation_threshold=30.0)
        >>> queue.put("critical_task", priority=Priority.HIGH)
        >>> queue.put("normal_task", priority=Priority.NORMAL)
        >>> queue.get()  # returns "critical_task"
        >>> queue.get()  # returns "normal_task"
    """

    def __init__(self, starvation_threshold: float = 60.0) -> None:
        """Initialize the priority queue.

        Args:
            starvation_threshold: Seconds after which a waiting task is
                promoted to HIGH priority. Set to 0 to disable.
        """
        if starvation_threshold < 0:
            raise ValueError("starvation_threshold must be >= 0")

        self._heap: list[_PriorityEntry] = []
        self._counter = itertools.count()
        self._lock = threading.Lock()
        self._starvation_threshold = starvation_threshold

    def put(self, item: Any, priority: int = Priority.NORMAL) -> None:
        """Add an item to the queue with the given priority.

        Args:
            item: The item to enqueue.
            priority: Priority value (0-9, lower = higher priority).

        Raises:
            ValueError: If priority is not in range [0, 9].
        """
        if not 0 <= priority <= 9:
            raise ValueError(f"priority must be in [0, 9], got {priority}")

        entry = _PriorityEntry(
            effective_priority=priority,
            sequence=next(self._counter),
            enqueue_time=time.monotonic(),
            item=item,
        )
        with self._lock:
            heapq.heappush(self._heap, entry)

    def get(self) -> Optional[Any]:
        """Remove and return the highest-priority item.

        Applies starvation protection before selecting: any entry waiting
        longer than the threshold is promoted to HIGH priority.

        Returns:
            The item, or None if the queue is empty.
        """
        with self._lock:
            self._apply_starvation_protection()
            while self._heap:
                entry = heapq.heappop(self._heap)
                if not entry.cancelled:
                    return entry.item
        return None

    def peek(self) -> Optional[Any]:
        """Return the highest-priority item without removing it.

        Returns:
            The item, or None if the queue is empty.
        """
        with self._lock:
            self._apply_starvation_protection()
            for entry in self._heap:
                if not entry.cancelled:
                    return entry.item
        return None

    @property
    def queue_size(self) -> int:
        """Return the number of non-cancelled items in the queue."""
        with self._lock:
            return sum(1 for entry in self._heap if not entry.cancelled)

    @property
    def is_empty(self) -> bool:
        """Check if the queue has no pending items."""
        return self.queue_size == 0

    def clear(self) -> None:
        """Remove all items from the queue."""
        with self._lock:
            self._heap.clear()

    def snapshot(self) -> list[dict]:
        """Return a snapshot of all pending entries for debugging.

        Returns:
            List of dicts with priority, sequence, wait_seconds, item info.
        """
        now = time.monotonic()
        with self._lock:
            return [
                {
                    "priority": entry.effective_priority,
                    "sequence": entry.sequence,
                    "wait_seconds": round(now - entry.enqueue_time, 3),
                    "cancelled": entry.cancelled,
                }
                for entry in sorted(self._heap)
            ]

    def _apply_starvation_protection(self) -> None:
        """Promote starved entries to HIGH priority. Must hold lock."""
        if self._starvation_threshold <= 0:
            return

        now = time.monotonic()
        promoted = False

        for entry in self._heap:
            if entry.cancelled:
                continue
            wait_time = now - entry.enqueue_time
            if (
                wait_time >= self._starvation_threshold
                and entry.effective_priority > Priority.HIGH
            ):
                entry.effective_priority = Priority.HIGH
                promoted = True

        if promoted:
            heapq.heapify(self._heap)
