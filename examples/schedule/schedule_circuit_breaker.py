"""Circuit Breaker Example

Demonstrates how to use the circuit breaker to protect against cascading failures.
When consecutive failures exceed the threshold, the breaker "opens" and immediately
rejects subsequent requests without executing the function, giving the downstream
service time to recover.

States:
  CLOSED  → Normal operation, requests pass through
  OPEN    → Failures exceeded threshold, requests are rejected immediately
  HALF_OPEN → After recovery timeout, one probe request is allowed through
"""

import asyncio
import random
import time

from qreward.utils import schedule


# --- Example 1: Basic circuit breaker ---
# After 3 consecutive failures the breaker opens for 5 seconds.
# During the open period, calls raise RuntimeError immediately.
@schedule(
    circuit_breaker_threshold=3,
    circuit_breaker_recovery=5.0,
    retry_times=0,
    default_result="fallback",
)
async def call_unstable_service(request_id: int):
    # Simulate an unstable service that fails 70% of the time
    if random.random() < 0.7:
        raise ConnectionError(f"Service unavailable for request {request_id}")
    return f"Success: {request_id}"


async def demo_basic_circuit_breaker():
    print("=== Basic Circuit Breaker Demo ===\n")
    for i in range(10):
        try:
            result = await call_unstable_service(i)
            print(f"  Request {i}: {result}")
        except RuntimeError as exc:
            print(f"  Request {i}: BLOCKED by circuit breaker - {exc}")
        await asyncio.sleep(0.3)

    # Wait for recovery timeout
    print("\n  Waiting 5s for breaker recovery...\n")
    await asyncio.sleep(5)

    # After recovery, the breaker enters HALF_OPEN and allows a probe request
    try:
        result = await call_unstable_service(99)
        print(f"  Probe request 99: {result}")
    except RuntimeError as exc:
        print(f"  Probe request 99: BLOCKED - {exc}")


# --- Example 2: Circuit breaker with retry ---
# Combines retry and circuit breaker: retries happen first, but if the breaker
# trips, subsequent calls fail fast without retrying.
@schedule(
    circuit_breaker_threshold=5,
    circuit_breaker_recovery=10.0,
    retry_times=2,
    default_result="default_response",
    debug=True,
)
async def call_with_retry_and_breaker(request_id: int):
    if random.random() < 0.8:
        raise TimeoutError(f"Timeout for request {request_id}")
    return f"OK: {request_id}"


async def demo_breaker_with_retry():
    print("\n=== Circuit Breaker + Retry Demo ===\n")
    for i in range(8):
        try:
            result = await call_with_retry_and_breaker(i)
            print(f"  Request {i}: {result}")
        except RuntimeError as exc:
            print(f"  Request {i}: BLOCKED - {exc}")
        await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(demo_basic_circuit_breaker())
    asyncio.run(demo_breaker_with_retry())
