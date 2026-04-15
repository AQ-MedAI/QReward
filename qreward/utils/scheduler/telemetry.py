"""Optional OpenTelemetry integration for schedule metrics export.

All OTel imports are guarded by try/except so this module works
even when opentelemetry packages are not installed.
"""

import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_OTEL_AVAILABLE = False
_meter_mod: Any = None
_trace_mod: Any = None

try:
    from opentelemetry import metrics as _meter_mod  # type: ignore[no-redef]
    from opentelemetry import trace as _trace_mod  # type: ignore[no-redef]
    _OTEL_AVAILABLE = True
except ImportError:
    pass

_ENV_ENABLED_KEY = "QREWARD_OTEL_ENABLED"


class TelemetryExporter:
    """Exports ScheduleMetrics to OpenTelemetry counters, histograms and spans.

    When OTel SDK is not installed or disabled via environment variable,
    all methods are no-ops.

    Example:
        >>> exporter = TelemetryExporter()
        >>> exporter.record(metrics)  # records counters + histogram
        >>> with exporter.span("my_func") as span:
        ...     span.set_attribute("retry_count", 3)
    """

    def __init__(
        self,
        meter_name: str = "qreward.scheduler",
        tracer_name: str = "qreward.scheduler",
    ) -> None:
        self._enabled = self._check_enabled()
        self._meter: Any = None
        self._tracer: Any = None
        self._total_calls_counter: Any = None
        self._success_counter: Any = None
        self._failure_counter: Any = None
        self._latency_histogram: Any = None

        if self._enabled:
            self._meter = _meter_mod.get_meter(meter_name)
            self._tracer = _trace_mod.get_tracer(tracer_name)
            self._total_calls_counter = self._meter.create_counter(
                "qreward.schedule.total_calls",
                description="Total number of schedule invocations",
            )
            self._success_counter = self._meter.create_counter(
                "qreward.schedule.success_count",
                description="Number of successful schedule completions",
            )
            self._failure_counter = self._meter.create_counter(
                "qreward.schedule.failure_count",
                description="Number of failed schedule attempts",
            )
            self._latency_histogram = self._meter.create_histogram(
                "qreward.schedule.latency_ms",
                unit="ms",
                description="Schedule invocation latency in milliseconds",
            )

    @classmethod
    def is_available(cls) -> bool:
        """Check if OpenTelemetry SDK is installed and enabled."""
        return _OTEL_AVAILABLE and cls._check_enabled()

    @staticmethod
    def _check_enabled() -> bool:
        """Check if OTel is available and not disabled by env var."""
        if not _OTEL_AVAILABLE:
            return False
        env_val = os.environ.get(_ENV_ENABLED_KEY, "true").lower()
        return env_val not in ("false", "0", "no", "off")

    def record(self, metrics: Any) -> None:
        """Record schedule metrics to OTel counters and histogram.

        Args:
            metrics: A ScheduleMetrics instance.
        """
        if not self._enabled:
            return
        self._total_calls_counter.add(metrics.total_calls)
        self._success_counter.add(metrics.success_count)
        self._failure_counter.add(metrics.failure_count)
        self._latency_histogram.record(metrics.total_latency_ms)

    def start_span(
        self, name: str, attributes: Optional[dict[str, Any]] = None
    ) -> Any:
        """Start a new OTel span.

        Args:
            name: Span name (typically the decorated function name).
            attributes: Optional span attributes.

        Returns:
            A span object, or a no-op context if OTel is disabled.
        """
        if not self._enabled or self._tracer is None:
            return _NoOpSpan()
        return self._tracer.start_span(name, attributes=attributes)

    def end_span(self, span: Any, metrics: Any) -> None:
        """End a span and attach metrics as attributes.

        Args:
            span: The span to end.
            metrics: A ScheduleMetrics instance.
        """
        if not self._enabled or isinstance(span, _NoOpSpan):
            return
        span.set_attribute("qreward.total_calls", metrics.total_calls)
        span.set_attribute("qreward.success_count", metrics.success_count)
        span.set_attribute("qreward.failure_count", metrics.failure_count)
        span.set_attribute("qreward.retry_count", metrics.retry_count)
        span.set_attribute("qreward.total_latency_ms", metrics.total_latency_ms)
        span.end()


class _NoOpSpan:
    """No-op span used when OTel is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass
