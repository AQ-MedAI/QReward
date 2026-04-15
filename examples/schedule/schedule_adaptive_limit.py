"""Adaptive Rate Limiting Example

Demonstrates how adaptive rate limiting dynamically adjusts the concurrency limit
based on real-time error rates and latency. When the service is healthy, the limit
gradually increases (speedup). When errors or high latency are detected, the limit
decreases (slowdown) to protect the downstream service.

Key parameters:
  adaptive_limit=True          → Enable adaptive limiting
  limit_size=100               → Initial concurrency limit
  adaptive_limit_min=10        → Minimum limit floor
  adaptive_limit_max=500       → Maximum limit ceiling
  adaptive_error_threshold=0.3 → Error rate threshold to trigger slowdown
  adaptive_latency_threshold=5 → Latency threshold (seconds) to trigger slowdown
"""

import asyncio
import random
import time

from qreward.utils import schedule


# --- Example 1: Adaptive limit under normal conditions ---
# The limiter starts at 50 and gradually increases as requests succeed.
@schedule(
    limit_size=50,
    adaptive_limit=True,
    adaptive_limit_min=10,
    adaptive_limit_max=200,
    adaptive_error_threshold=0.3,
    adaptive_latency_threshold=2.0,
    adaptive_window_seconds=5.0,
    retry_times=0,
)
async def healthy_service(request_id: int):
    # Simulate a healthy service with low latency
    await asyncio.sleep(random.uniform(0.05, 0.2))
    return f"OK: {request_id}"


async def demo_healthy():
    print("=== Adaptive Limit - Healthy Service ===\n")
    start = time.time()
    tasks = [healthy_service(i) for i in range(20)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start
    print(f"  Completed {len(results)} requests in {elapsed:.2f}s")
    print(f"  All succeeded: {all(r.startswith('OK') for r in results)}\n")


# --- Example 2: Adaptive limit under degraded conditions ---
# When error rate exceeds the threshold, the limiter automatically reduces
# the concurrency to protect the service.
@schedule(
    limit_size=50,
    adaptive_limit=True,
    adaptive_limit_min=5,
    adaptive_limit_max=200,
    adaptive_error_threshold=0.2,
    adaptive_latency_threshold=1.0,
    adaptive_window_seconds=3.0,
    retry_times=1,
    default_result="degraded_fallback",
)
async def degraded_service(request_id: int):
    # Simulate a degraded service: 40% failure rate, high latency
    if random.random() < 0.4:
        raise ConnectionError(f"Service error for {request_id}")
    await asyncio.sleep(random.uniform(0.5, 2.0))
    return f"OK: {request_id}"


async def demo_degraded():
    print("=== Adaptive Limit - Degraded Service ===\n")
    start = time.time()
    tasks = [degraded_service(i) for i in range(20)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start
    successes = sum(1 for r in results if r.startswith("OK"))
    fallbacks = sum(1 for r in results if r == "degraded_fallback")
    print(f"  Completed {len(results)} requests in {elapsed:.2f}s")
    print(f"  Successes: {successes}, Fallbacks: {fallbacks}\n")


if __name__ == "__main__":
    asyncio.run(demo_healthy())
    asyncio.run(demo_degraded())
