"""Metrics Callback Example

Demonstrates how to use the metrics_callback parameter to collect execution
statistics after each function invocation. The callback receives a ScheduleMetrics
dataclass containing:
  - total_calls:      Total task submissions (including retries and hedged requests)
  - success_count:    Number of successful completions
  - failure_count:    Number of failed attempts
  - retry_count:      Number of retries (excludes the first attempt)
  - total_latency_ms: Wall-clock latency from start to finish (ms)
  - avg_latency_ms:   Average latency per attempt (ms)
"""

import asyncio
import random

from qreward.utils import schedule
from qreward.utils.scheduler import ScheduleMetrics


# --- Example 1: Simple metrics logging ---
def log_metrics(metrics: ScheduleMetrics):
    print(
        f"  [Metrics] calls={metrics.total_calls} "
        f"success={metrics.success_count} fail={metrics.failure_count} "
        f"retries={metrics.retry_count} latency={metrics.total_latency_ms:.1f}ms"
    )


@schedule(retry_times=3, default_result="failed", metrics_callback=log_metrics)
async def flaky_task(task_id: int):
    await asyncio.sleep(0.1)
    if random.random() < 0.5:
        raise RuntimeError(f"Task {task_id} failed")
    return f"Done: {task_id}"


async def demo_simple_logging():
    print("=== Simple Metrics Logging ===\n")
    for i in range(5):
        result = await flaky_task(i)
        print(f"  Result: {result}\n")


# --- Example 2: Aggregating metrics across calls ---
class MetricsAggregator:
    """Collects metrics across multiple invocations for summary reporting."""

    def __init__(self):
        self.total_invocations = 0
        self.total_successes = 0
        self.total_failures = 0
        self.total_retries = 0
        self.latencies = []

    def collect(self, metrics: ScheduleMetrics):
        self.total_invocations += 1
        self.total_successes += metrics.success_count
        self.total_failures += metrics.failure_count
        self.total_retries += metrics.retry_count
        self.latencies.append(metrics.total_latency_ms)

    def report(self):
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        print(f"  Total invocations: {self.total_invocations}")
        print(f"  Total successes:   {self.total_successes}")
        print(f"  Total failures:    {self.total_failures}")
        print(f"  Total retries:     {self.total_retries}")
        print(f"  Avg latency:       {avg_latency:.1f}ms")


aggregator = MetricsAggregator()


@schedule(retry_times=2, default_result="fallback", metrics_callback=aggregator.collect)
async def batch_task(task_id: int):
    await asyncio.sleep(random.uniform(0.05, 0.2))
    if random.random() < 0.3:
        raise ValueError(f"Error in task {task_id}")
    return f"OK: {task_id}"


async def demo_aggregation():
    print("\n=== Metrics Aggregation ===\n")
    tasks = [batch_task(i) for i in range(20)]
    await asyncio.gather(*tasks)
    print()
    aggregator.report()


# --- Example 3: Sync function with metrics ---
sync_metrics_log = []


@schedule(retry_times=1, metrics_callback=lambda m: sync_metrics_log.append(m))
def sync_task(value: int):
    if random.random() < 0.3:
        raise RuntimeError("sync error")
    return value * 2


def demo_sync_metrics():
    print("\n\n=== Sync Metrics ===\n")
    for i in range(5):
        result = sync_task(i)
        print(f"  sync_task({i}) = {result}")

    print(f"\n  Collected {len(sync_metrics_log)} metrics entries")
    for idx, m in enumerate(sync_metrics_log):
        print(f"    [{idx}] latency={m.total_latency_ms:.1f}ms retries={m.retry_count}")


if __name__ == "__main__":
    asyncio.run(demo_simple_logging())
    asyncio.run(demo_aggregation())
    demo_sync_metrics()
