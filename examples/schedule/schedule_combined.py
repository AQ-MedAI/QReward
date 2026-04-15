"""Combined Features Example

Demonstrates how to combine multiple schedule capabilities in a single
decorator call. This is the recommended pattern for production use cases
where you need retry, rate limiting, circuit breaking, metrics, and
telemetry all working together.
"""

import asyncio
import random
import time

from qreward.utils import schedule
from qreward.utils.scheduler import (
    Priority,
    ScheduleConfig,
    ScheduleMetrics,
    TelemetryExporter,
)


# --- Example 1: Production-ready API call ---
# Combines retry, rate limiting, circuit breaker, adaptive limiting,
# metrics callback, and telemetry in a single decorator.
metrics_log = []


@schedule(
    # Timeout & Retry
    timeout=10,
    retry_times=3,
    retry_interval=0.5,
    exception_types=(TimeoutError, ConnectionError, OSError),
    default_result=None,
    # Rate Limiting (adaptive)
    limit_size=100,
    adaptive_limit=True,
    adaptive_limit_min=10,
    adaptive_limit_max=500,
    adaptive_error_threshold=0.3,
    adaptive_latency_threshold=3.0,
    # Circuit Breaker
    circuit_breaker_threshold=10,
    circuit_breaker_recovery=30.0,
    # Priority
    priority=Priority.HIGH,
    # Observability
    metrics_callback=lambda m: metrics_log.append(m),
    debug=True,
)
async def production_api_call(endpoint: str, payload: dict):
    """Simulates a production API call with all protections enabled."""
    latency = random.uniform(0.1, 0.5)
    await asyncio.sleep(latency)

    # Simulate occasional failures
    if random.random() < 0.2:
        raise ConnectionError(f"Failed to reach {endpoint}")

    return {"status": "ok", "endpoint": endpoint, "latency_ms": latency * 1000}


async def demo_production_call():
    print("=== Production-Ready API Call ===\n")
    tasks = [
        production_api_call("/api/users", {"id": i})
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)

    successes = sum(1 for r in results if r is not None)
    print(f"\n  Results: {successes}/{len(results)} succeeded")
    print(f"  Metrics collected: {len(metrics_log)} entries")
    if metrics_log:
        avg_latency = sum(m.total_latency_ms for m in metrics_log) / len(metrics_log)
        total_retries = sum(m.retry_count for m in metrics_log)
        print(f"  Avg latency: {avg_latency:.1f}ms")
        print(f"  Total retries: {total_retries}")


# --- Example 2: Multi-tier service with different priorities ---
@schedule(
    retry_times=1,
    limit_size=50,
    priority=Priority.HIGH,
    default_result="critical_fallback",
)
async def critical_service(request_id: int):
    await asyncio.sleep(random.uniform(0.05, 0.15))
    if random.random() < 0.1:
        raise RuntimeError("critical error")
    return f"critical-{request_id}"


@schedule(
    retry_times=2,
    limit_size=100,
    priority=Priority.NORMAL,
    default_result="normal_fallback",
)
async def normal_service(request_id: int):
    await asyncio.sleep(random.uniform(0.1, 0.3))
    if random.random() < 0.2:
        raise RuntimeError("normal error")
    return f"normal-{request_id}"


@schedule(
    retry_times=3,
    limit_size=200,
    priority=Priority.LOW,
    default_result="batch_fallback",
)
async def batch_service(request_id: int):
    await asyncio.sleep(random.uniform(0.2, 0.5))
    if random.random() < 0.3:
        raise RuntimeError("batch error")
    return f"batch-{request_id}"


async def demo_multi_tier():
    print("\n\n=== Multi-Tier Service Demo ===\n")
    start = time.time()

    tasks = []
    # Critical tasks
    for i in range(5):
        tasks.append(("CRITICAL", critical_service(i)))
    # Normal tasks
    for i in range(10):
        tasks.append(("NORMAL", normal_service(i)))
    # Batch tasks
    for i in range(15):
        tasks.append(("BATCH", batch_service(i)))

    results = await asyncio.gather(*[t[1] for t in tasks])
    elapsed = time.time() - start

    tier_results = {"CRITICAL": [], "NORMAL": [], "BATCH": []}
    for (tier, _), result in zip(tasks, results):
        tier_results[tier].append(result)

    for tier, tier_res in tier_results.items():
        successes = sum(1 for r in tier_res if not r.endswith("_fallback"))
        print(f"  {tier}: {successes}/{len(tier_res)} succeeded")

    print(f"\n  Total time: {elapsed:.2f}s")


# --- Example 3: Hedged request + circuit breaker ---
@schedule(
    hedged_request_time=2.0,
    hedged_request_max_times=1,
    circuit_breaker_threshold=5,
    circuit_breaker_recovery=10.0,
    retry_times=2,
    default_result="hedged_fallback",
)
async def hedged_with_breaker(request_id: int):
    """Combines hedged requests with circuit breaker protection."""
    latency = random.uniform(0.5, 4.0)
    await asyncio.sleep(latency)
    if random.random() < 0.3:
        raise TimeoutError(f"Timeout for {request_id}")
    return f"hedged-{request_id}"


async def demo_hedged_breaker():
    print("\n\n=== Hedged Request + Circuit Breaker ===\n")
    for i in range(8):
        try:
            result = await hedged_with_breaker(i)
            print(f"  Request {i}: {result}")
        except RuntimeError as exc:
            print(f"  Request {i}: BLOCKED - {exc}")


if __name__ == "__main__":
    asyncio.run(demo_production_call())
    asyncio.run(demo_multi_tier())
    asyncio.run(demo_hedged_breaker())
