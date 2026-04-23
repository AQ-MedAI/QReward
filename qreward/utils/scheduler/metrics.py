"""Execution metrics for schedule decorator."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ScheduleMetrics:
    """Execution metrics collected after a schedule invocation.

    Attributes:
        total_calls: Total number of task submissions (including retries
            and hedged requests).
        success_count: Number of successful completions.
        failure_count: Number of failed attempts.
        retry_count: Number of retries (excludes the first attempt).
        total_latency_ms: Wall-clock latency from start to finish
            in milliseconds.
        avg_latency_ms: Average latency per attempt in milliseconds.
    """

    total_calls: int
    success_count: int
    failure_count: int
    retry_count: int
    total_latency_ms: float
    avg_latency_ms: float

    def export_to_otel(self, exporter: Optional[Any] = None) -> None:
        """Export metrics to OpenTelemetry via a TelemetryExporter.

        Args:
            exporter: A TelemetryExporter instance. If None, this is a no-op.
        """
        if exporter is not None:
            exporter.record(self)
