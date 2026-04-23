"""OpenTelemetry Integration Example

Demonstrates how to integrate schedule metrics with OpenTelemetry for
observability. The TelemetryExporter automatically exports counters,
histograms, and spans to your OTel backend.

When OpenTelemetry SDK is not installed, all operations gracefully degrade
to no-ops — no exceptions are raised.

Prerequisites (optional):
  pip install opentelemetry-api opentelemetry-sdk
"""

import asyncio
import random

from qreward.utils import schedule
from qreward.utils.scheduler import TelemetryExporter


# --- Example 1: Check OTel availability ---
def demo_availability():
    print("=== OTel Availability Check ===\n")
    available = TelemetryExporter.is_available()
    print(f"  OpenTelemetry SDK available: {available}")
    if not available:
        print("  (Install opentelemetry-api and opentelemetry-sdk to enable)\n")
    else:
        print("  OTel is ready for metrics export\n")


# --- Example 2: Using TelemetryExporter with schedule ---
# Create an exporter instance. If OTel is not installed, this is a no-op.
exporter = TelemetryExporter(
    meter_name="myapp.scheduler",
    tracer_name="myapp.scheduler",
)


@schedule(
    retry_times=2,
    default_result="fallback",
    telemetry_exporter=exporter,
)
async def monitored_task(task_id: int):
    """A task whose metrics are automatically exported to OTel."""
    await asyncio.sleep(random.uniform(0.05, 0.2))
    if random.random() < 0.3:
        raise RuntimeError(f"Task {task_id} error")
    return f"OK: {task_id}"


async def demo_telemetry_export():
    print("=== Telemetry Export Demo ===\n")
    tasks = [monitored_task(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    successes = sum(1 for r in results if r.startswith("OK"))
    print(f"  Completed {len(results)} tasks ({successes} succeeded)")
    print("  Metrics exported to OTel (if SDK is available)\n")


# --- Example 3: Manual span usage ---
async def demo_manual_span():
    print("=== Manual Span Demo ===\n")
    span = exporter.start_span("custom_operation", attributes={"version": "1.0"})

    # Perform some work inside the span
    await asyncio.sleep(0.1)
    span.set_attribute("result", "success")

    # End the span (no-op if OTel is not installed)
    from qreward.utils.scheduler import ScheduleMetrics

    metrics = ScheduleMetrics(
        total_calls=1, success_count=1, failure_count=0,
        retry_count=0, total_latency_ms=100.0, avg_latency_ms=100.0,
    )
    exporter.end_span(span, metrics)
    print("  Span created and ended successfully")
    print("  (Visible in your OTel backend if SDK is configured)\n")


if __name__ == "__main__":
    demo_availability()
    asyncio.run(demo_telemetry_export())
    asyncio.run(demo_manual_span())
