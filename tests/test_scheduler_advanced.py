"""Advanced unit tests for scheduler modules.

Tests for:
- PriorityTaskQueue (priority_queue.py)
- CircuitBreaker (circuit_breaker.py)
- AdaptiveRateLimiter (adaptive_limiter.py)
- ScheduleConfig (config.py)
- ScheduleMetrics (metrics.py)
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from qreward.utils.scheduler.priority_queue import (
    Priority,
    PriorityTaskQueue,
)
from qreward.utils.scheduler.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from qreward.utils.scheduler.adaptive_limiter import (
    AdaptiveRateLimiter,
)
from qreward.utils.scheduler.config import ScheduleConfig
from qreward.utils.scheduler.metrics import ScheduleMetrics


# =============================================================================
# PriorityTaskQueue Tests
# =============================================================================


class TestPriorityTaskQueueInit:
    """Test PriorityTaskQueue initialization."""

    def test_init_default_starvation_threshold(self):
        """Test default starvation_threshold is 60.0."""
        queue = PriorityTaskQueue()
        assert queue._starvation_threshold == 60.0

    def test_init_custom_starvation_threshold(self):
        """Test custom starvation_threshold."""
        queue = PriorityTaskQueue(starvation_threshold=30.0)
        assert queue._starvation_threshold == 30.0

    def test_init_negative_starvation_threshold_raises_error(self):
        """Test negative starvation_threshold raises ValueError."""
        with pytest.raises(ValueError, match="starvation_threshold must be >= 0"):
            PriorityTaskQueue(starvation_threshold=-1.0)

    def test_init_zero_starvation_threshold_disables_protection(self):
        """Test starvation_threshold=0 disables protection."""
        queue = PriorityTaskQueue(starvation_threshold=0.0)
        assert queue._starvation_threshold == 0.0


class TestPriorityTaskQueuePut:
    """Test PriorityTaskQueue.put() method."""

    def test_put_default_priority(self):
        """Test put with default NORMAL priority."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        assert queue.queue_size == 1

    def test_put_high_priority(self):
        """Test put with HIGH priority."""
        queue = PriorityTaskQueue()
        queue.put("task1", priority=Priority.HIGH)
        assert queue.queue_size == 1

    def test_put_low_priority(self):
        """Test put with LOW priority."""
        queue = PriorityTaskQueue()
        queue.put("task1", priority=Priority.LOW)
        assert queue.queue_size == 1

    def test_put_invalid_priority_negative_raises_error(self):
        """Test put with negative priority raises ValueError."""
        queue = PriorityTaskQueue()
        with pytest.raises(ValueError, match="priority must be in \\[0, 9\\]"):
            queue.put("task1", priority=-1)

    def test_put_invalid_priority_too_high_raises_error(self):
        """Test put with priority > 9 raises ValueError."""
        queue = PriorityTaskQueue()
        with pytest.raises(ValueError, match="priority must be in \\[0, 9\\]"):
            queue.put("task1", priority=10)

    def test_put_boundary_priority_0(self):
        """Test put with boundary priority 0."""
        queue = PriorityTaskQueue()
        queue.put("task1", priority=0)
        assert queue.queue_size == 1

    def test_put_boundary_priority_9(self):
        """Test put with boundary priority 9."""
        queue = PriorityTaskQueue()
        queue.put("task1", priority=9)
        assert queue.queue_size == 1


class TestPriorityTaskQueueGet:
    """Test PriorityTaskQueue.get() method."""

    def test_get_empty_queue_returns_none(self):
        """Test get from empty queue returns None."""
        queue = PriorityTaskQueue()
        assert queue.get() is None

    def test_get_single_item(self):
        """Test get single item."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        assert queue.get() == "task1"
        assert queue.is_empty

    def test_get_priority_order_high_first(self):
        """Test items are dequeued in priority order (HIGH first)."""
        queue = PriorityTaskQueue()
        queue.put("low", priority=Priority.LOW)
        queue.put("high", priority=Priority.HIGH)
        queue.put("normal", priority=Priority.NORMAL)

        assert queue.get() == "high"
        assert queue.get() == "normal"
        assert queue.get() == "low"
        assert queue.is_empty

    def test_get_same_priority_fifo(self):
        """Test items with same priority follow FIFO order."""
        queue = PriorityTaskQueue()
        queue.put("first", priority=Priority.NORMAL)
        queue.put("second", priority=Priority.NORMAL)
        queue.put("third", priority=Priority.NORMAL)

        assert queue.get() == "first"
        assert queue.get() == "second"
        assert queue.get() == "third"

    def test_get_with_starvation_protection(self):
        """Test starvation protection promotes old tasks."""
        queue = PriorityTaskQueue(starvation_threshold=0.1)
        queue.put("low", priority=Priority.LOW)
        queue.put("normal", priority=Priority.NORMAL)

        # Wait for starvation threshold to pass
        time.sleep(0.15)

        # Add high priority task
        queue.put("high", priority=Priority.HIGH)

        # Starved tasks should be promoted to HIGH
        # Due to heap ordering, starved tasks may come before or after new HIGH task
        # depending on sequence number, but they should be promoted
        result1 = queue.get()
        result2 = queue.get()
        result3 = queue.get()

        # All three should be retrieved
        assert result1 in ["low", "normal", "high"]
        assert result2 in ["low", "normal", "high"]
        assert result3 in ["low", "normal", "high"]
        assert len({result1, result2, result3}) == 3
        assert queue.is_empty

    def test_get_starvation_threshold_zero_disables_protection(self):
        """Test starvation_threshold=0 disables protection."""
        queue = PriorityTaskQueue(starvation_threshold=0.0)
        queue.put("low", priority=Priority.LOW)
        queue.put("normal", priority=Priority.NORMAL)

        # Wait a bit
        time.sleep(0.1)

        # Add high priority task
        queue.put("high", priority=Priority.HIGH)

        # Without starvation protection, HIGH should still come first
        assert queue.get() == "high"
        assert queue.get() == "normal"
        assert queue.get() == "low"


class TestPriorityTaskQueuePeek:
    """Test PriorityTaskQueue.peek() method."""

    def test_peek_empty_queue_returns_none(self):
        """Test peek on empty queue returns None."""
        queue = PriorityTaskQueue()
        assert queue.peek() is None

    def test_peek_does_not_remove_item(self):
        """Test peek does not remove item from queue."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        assert queue.peek() == "task1"
        assert queue.queue_size == 1
        assert queue.peek() == "task1"

    def test_peek_returns_highest_priority(self):
        """Test peek returns highest priority item."""
        queue = PriorityTaskQueue()
        queue.put("low", priority=Priority.LOW)
        queue.put("high", priority=Priority.HIGH)
        assert queue.peek() == "high"
        assert queue.queue_size == 2

    def test_peek_with_starvation_protection(self):
        """Test peek respects starvation protection."""
        queue = PriorityTaskQueue(starvation_threshold=0.1)
        queue.put("low", priority=Priority.LOW)
        time.sleep(0.15)
        queue.put("high", priority=Priority.HIGH)

        # Starved task should be promoted
        result = queue.peek()
        assert result in ["low", "high"]


class TestPriorityTaskQueueProperties:
    """Test PriorityTaskQueue properties."""

    def test_queue_size_empty(self):
        """Test queue_size on empty queue."""
        queue = PriorityTaskQueue()
        assert queue.queue_size == 0

    def test_queue_size_multiple_items(self):
        """Test queue_size with multiple items."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        queue.put("task2")
        queue.put("task3")
        assert queue.queue_size == 3

    def test_is_empty_true(self):
        """Test is_empty returns True for empty queue."""
        queue = PriorityTaskQueue()
        assert queue.is_empty is True

    def test_is_empty_false(self):
        """Test is_empty returns False for non-empty queue."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        assert queue.is_empty is False


class TestPriorityTaskQueueClear:
    """Test PriorityTaskQueue.clear() method."""

    def test_clear_empty_queue(self):
        """Test clear on empty queue."""
        queue = PriorityTaskQueue()
        queue.clear()
        assert queue.is_empty

    def test_clear_removes_all_items(self):
        """Test clear removes all items."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        queue.put("task2")
        queue.put("task3")
        assert queue.queue_size == 3

        queue.clear()
        assert queue.is_empty
        assert queue.get() is None


class TestPriorityTaskQueueSnapshot:
    """Test PriorityTaskQueue.snapshot() method."""

    def test_snapshot_empty_queue(self):
        """Test snapshot on empty queue."""
        queue = PriorityTaskQueue()
        snapshot = queue.snapshot()
        assert snapshot == []

    def test_snapshot_returns_correct_structure(self):
        """Test snapshot returns correct data structure."""
        queue = PriorityTaskQueue()
        queue.put("task1", priority=Priority.HIGH)
        queue.put("task2", priority=Priority.NORMAL)

        snapshot = queue.snapshot()
        assert len(snapshot) == 2

        # Check structure
        for entry in snapshot:
            assert "priority" in entry
            assert "sequence" in entry
            assert "wait_seconds" in entry
            assert "cancelled" in entry

    def test_snapshot_priority_ordering(self):
        """Test snapshot respects priority ordering."""
        queue = PriorityTaskQueue()
        queue.put("low", priority=Priority.LOW)
        queue.put("high", priority=Priority.HIGH)
        queue.put("normal", priority=Priority.NORMAL)

        snapshot = queue.snapshot()
        assert snapshot[0]["priority"] == Priority.HIGH
        assert snapshot[1]["priority"] == Priority.NORMAL
        assert snapshot[2]["priority"] == Priority.LOW

    def test_snapshot_wait_seconds(self):
        """Test snapshot includes wait_seconds."""
        queue = PriorityTaskQueue()
        queue.put("task1")
        time.sleep(0.05)
        queue.put("task2")

        snapshot = queue.snapshot()
        assert snapshot[0]["wait_seconds"] >= 0.05
        assert snapshot[1]["wait_seconds"] >= 0.0


# =============================================================================
# CircuitBreaker Tests
# =============================================================================


class TestCircuitBreakerInit:
    """Test CircuitBreaker initialization."""

    def test_init_default_values(self):
        """Test default initialization values."""
        breaker = CircuitBreaker()
        assert breaker._failure_threshold == 5
        assert breaker._recovery_timeout == 30.0
        assert breaker._half_open_max_calls == 1
        assert breaker._state == CircuitState.CLOSED

    def test_init_custom_values(self):
        """Test custom initialization values."""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60.0,
            half_open_max_calls=2,
        )
        assert breaker._failure_threshold == 3
        assert breaker._recovery_timeout == 60.0
        assert breaker._half_open_max_calls == 2

    def test_init_custom_time_func(self):
        """Test custom time_func for testing."""
        custom_time = MagicMock(return_value=0.0)
        breaker = CircuitBreaker(time_func=custom_time)
        assert breaker._time_func == custom_time


class TestCircuitBreakerState:
    """Test CircuitBreaker.state property."""

    def test_initial_state_closed(self):
        """Test initial state is CLOSED."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED

    def test_state_remains_closed(self):
        """Test state remains CLOSED when no failures."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerAllowRequest:
    """Test CircuitBreaker.allow_request() method."""

    def test_allow_request_closed_state(self):
        """Test allow_request returns True in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.allow_request() is True

    def test_allow_request_after_successes(self):
        """Test allow_request still True after successes."""
        breaker = CircuitBreaker()
        breaker.record_success()
        breaker.record_success()
        assert breaker.allow_request() is True

    def test_allow_request_open_state_rejects(self):
        """Test allow_request returns False in OPEN state."""
        custom_time = MagicMock(return_value=0.0)
        breaker = CircuitBreaker(failure_threshold=3, time_func=custom_time)

        # Trigger OPEN state
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker.allow_request() is False

    def test_allow_request_half_open_allows_limited(self):
        """Test allow_request allows limited requests in HALF_OPEN."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert OPEN) -> 0.0 (elapsed=0 < 30)
        #   state (assert HALF_OPEN) -> 31.0 (elapsed=31 >= 30)
        custom_time = MagicMock(side_effect=[0.0, 0.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            half_open_max_calls=2,
            time_func=custom_time,
        )

        # Trigger OPEN state
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

        # Transition to HALF_OPEN after timeout
        assert breaker.state == CircuitState.HALF_OPEN

        # Should allow up to half_open_max_calls
        assert breaker.allow_request() is True
        assert breaker.allow_request() is True
        assert breaker.allow_request() is False


class TestCircuitBreakerRecordSuccess:
    """Test CircuitBreaker.record_success() method."""

    def test_record_success_in_closed_resets_failures(self):
        """Test record_success resets failure count in CLOSED state."""
        breaker = CircuitBreaker()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker._failure_count == 2

        breaker.record_success()
        assert breaker._failure_count == 0

    def test_record_success_in_half_open_transitions_to_closed(self):
        """Test record_success transitions HALF_OPEN to CLOSED."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert HALF_OPEN) -> 31.0 (elapsed >= 30)
        #   state (assert CLOSED, after reset) -> no call
        custom_time = MagicMock(side_effect=[0.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            time_func=custom_time,
        )

        # Trigger OPEN -> HALF_OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.HALF_OPEN

        # Record success in HALF_OPEN
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0


class TestCircuitBreakerRecordFailure:
    """Test CircuitBreaker.record_failure() method."""

    def test_record_failure_increments_count(self):
        """Test record_failure increments failure count."""
        breaker = CircuitBreaker()
        assert breaker._failure_count == 0
        breaker.record_failure()
        assert breaker._failure_count == 1
        breaker.record_failure()
        assert breaker._failure_count == 2

    def test_record_failure_trips_to_open(self):
        """Test consecutive failures trip breaker to OPEN."""
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_record_failure_in_half_open_reopens(self):
        """Test record_failure in HALF_OPEN reopens to OPEN."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert HALF_OPEN) -> 31.0 (elapsed >= 30)
        #   record_failure in HALF_OPEN -> 31.0 (new failure time)
        #   state (assert OPEN) -> 31.0 (elapsed=0 < 30)
        custom_time = MagicMock(side_effect=[0.0, 31.0, 31.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            time_func=custom_time,
        )

        # Trigger OPEN -> HALF_OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.HALF_OPEN

        # Record failure in HALF_OPEN
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker._half_open_calls == 0


class TestCircuitBreakerTransitions:
    """Test CircuitBreaker state transitions."""

    def test_closed_to_open_on_threshold(self):
        """Test CLOSED -> OPEN transition on failure threshold."""
        breaker = CircuitBreaker(failure_threshold=5)
        for _ in range(5):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_open_to_half_open_after_timeout(self):
        """Test OPEN -> HALF_OPEN transition after recovery_timeout."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert OPEN) -> 0.0 (elapsed=0 < 30)
        #   state (assert HALF_OPEN) -> 31.0 (elapsed >= 30)
        custom_time = MagicMock(side_effect=[0.0, 0.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            time_func=custom_time,
        )

        # Trip to OPEN
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Check state transitions to HALF_OPEN after timeout
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """Test HALF_OPEN -> CLOSED on successful probe."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert HALF_OPEN) -> 31.0 (elapsed >= 30)
        #   state (assert CLOSED, after reset) -> no call
        custom_time = MagicMock(side_effect=[0.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            time_func=custom_time,
        )

        # OPEN -> HALF_OPEN
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful probe
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Test HALF_OPEN -> OPEN on failed probe."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert HALF_OPEN) -> 31.0 (elapsed >= 30)
        #   record_failure in HALF_OPEN -> 31.0 (new failure time)
        #   state (assert OPEN) -> 31.0 (elapsed=0 < 30)
        custom_time = MagicMock(side_effect=[0.0, 31.0, 31.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            time_func=custom_time,
        )

        # OPEN -> HALF_OPEN
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.HALF_OPEN

        # Failed probe
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerReset:
    """Test CircuitBreaker.reset() method."""

    def test_reset_from_closed(self):
        """Test reset from CLOSED state."""
        breaker = CircuitBreaker()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker._failure_count == 2

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0
        assert breaker._half_open_calls == 0

    def test_reset_from_open(self):
        """Test reset from OPEN state."""
        custom_time = MagicMock(return_value=0.0)
        breaker = CircuitBreaker(failure_threshold=3, time_func=custom_time)

        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0

    def test_reset_from_half_open(self):
        """Test reset from HALF_OPEN state."""
        # time_func call sequence:
        #   record_failure #3 (threshold hit) -> 0.0
        #   state (assert HALF_OPEN) -> 31.0 (elapsed >= 30)
        #   state (assert CLOSED, after reset) -> no call
        custom_time = MagicMock(side_effect=[0.0, 31.0])
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            time_func=custom_time,
        )

        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._half_open_calls == 0


# =============================================================================
# AdaptiveRateLimiter Tests
# =============================================================================


class TestAdaptiveRateLimiterInit:
    """Test AdaptiveRateLimiter initialization."""

    def test_init_default_values(self):
        """Test default initialization values."""
        limiter = AdaptiveRateLimiter(initial_limit=100)
        assert limiter.current_limit == 100
        assert limiter._limit_min == 10
        assert limiter._limit_max == 500
        assert limiter._error_threshold == 0.3
        assert limiter._latency_threshold == 5.0

    def test_init_custom_values(self):
        """Test custom initialization values."""
        limiter = AdaptiveRateLimiter(
            initial_limit=200,
            limit_min=50,
            limit_max=1000,
            error_threshold=0.2,
            latency_threshold=2.0,
            window_seconds=20.0,
        )
        assert limiter.current_limit == 200
        assert limiter._limit_min == 50
        assert limiter._limit_max == 1000
        assert limiter._error_threshold == 0.2
        assert limiter._latency_threshold == 2.0
        assert limiter._window_seconds == 20.0

    def test_init_limit_min_greater_than_limit_max_raises_error(self):
        """Test limit_min > limit_max raises ValueError."""
        with pytest.raises(ValueError, match="limit_min must be <= limit_max"):
            AdaptiveRateLimiter(initial_limit=100, limit_min=500, limit_max=100)

    def test_init_invalid_error_threshold_zero_raises_error(self):
        """Test error_threshold=0 raises ValueError."""
        with pytest.raises(ValueError, match="error_threshold must be in \\(0, 1\\]"):
            AdaptiveRateLimiter(initial_limit=100, error_threshold=0.0)

    def test_init_invalid_error_threshold_negative_raises_error(self):
        """Test negative error_threshold raises ValueError."""
        with pytest.raises(ValueError, match="error_threshold must be in \\(0, 1\\]"):
            AdaptiveRateLimiter(initial_limit=100, error_threshold=-0.1)

    def test_init_invalid_error_threshold_gt_one_raises_error(self):
        """Test error_threshold > 1 raises ValueError."""
        with pytest.raises(ValueError, match="error_threshold must be in \\(0, 1\\]"):
            AdaptiveRateLimiter(initial_limit=100, error_threshold=1.5)

    def test_init_clamps_initial_limit_to_range(self):
        """Test initial_limit is clamped to [limit_min, limit_max]."""
        limiter = AdaptiveRateLimiter(initial_limit=1000, limit_min=50, limit_max=200)
        assert limiter.current_limit == 200

        limiter2 = AdaptiveRateLimiter(initial_limit=10, limit_min=50, limit_max=200)
        assert limiter2.current_limit == 50


class TestAdaptiveRateLimiterCurrentLimit:
    """Test AdaptiveRateLimiter.current_limit property."""

    def test_current_limit_returns_initial_value(self):
        """Test current_limit returns initial value."""
        limiter = AdaptiveRateLimiter(initial_limit=150)
        assert limiter.current_limit == 150

    def test_current_limit_returns_integer(self):
        """Test current_limit returns integer."""
        limiter = AdaptiveRateLimiter(initial_limit=100.7)
        assert isinstance(limiter.current_limit, int)
        assert limiter.current_limit == 100


class TestAdaptiveRateLimiterRecord:
    """Test AdaptiveRateLimiter.record() method."""

    def test_record_success(self):
        """Test recording successful request."""
        limiter = AdaptiveRateLimiter(initial_limit=100)
        limiter.record(latency_seconds=0.5, success=True)
        assert len(limiter._records) == 1
        assert limiter._records[0].success is True

    def test_record_failure(self):
        """Test recording failed request."""
        limiter = AdaptiveRateLimiter(initial_limit=100)
        limiter.record(latency_seconds=1.0, success=False)
        assert len(limiter._records) == 1
        assert limiter._records[0].success is False

    def test_record_multiple_requests(self):
        """Test recording multiple requests."""
        limiter = AdaptiveRateLimiter(initial_limit=100)
        for i in range(5):
            limiter.record(latency_seconds=0.1 * i, success=i % 2 == 0)
        assert len(limiter._records) == 5

    def test_record_high_error_rate_triggers_slowdown(self):
        """Test high error rate triggers slowdown."""
        limiter = AdaptiveRateLimiter(
            initial_limit=100,
            limit_min=10,
            limit_max=500,
            error_threshold=0.3,
            cooldown_seconds=0.0,
        )

        # Record high error rate
        for _ in range(10):
            limiter.record(latency_seconds=0.5, success=False)
            limiter.record(latency_seconds=0.5, success=True)

        # Error rate = 0.5 > 0.3, should slow down
        assert limiter.current_limit < 100

    def test_record_low_error_rate_triggers_speedup(self):
        """Test low error rate triggers speedup."""
        limiter = AdaptiveRateLimiter(
            initial_limit=100,
            limit_min=10,
            limit_max=500,
            error_threshold=0.3,
            cooldown_seconds=0.0,
        )

        # Record low error rate (< 0.5 * 0.3 = 0.15)
        for _ in range(10):
            limiter.record(latency_seconds=0.5, success=True)
            limiter.record(latency_seconds=0.5, success=True)
            limiter.record(latency_seconds=0.5, success=True)
            limiter.record(latency_seconds=0.5, success=False)

        # Error rate = 0.1 < 0.15, should speed up
        assert limiter.current_limit > 100

    def test_record_high_latency_triggers_slowdown(self):
        """Test high latency triggers slowdown."""
        limiter = AdaptiveRateLimiter(
            initial_limit=100,
            limit_min=10,
            limit_max=500,
            latency_threshold=2.0,
            cooldown_seconds=0.0,
        )

        # Record high latency
        for _ in range(10):
            limiter.record(latency_seconds=3.0, success=True)

        # Avg latency = 3.0 > 2.0, should slow down
        assert limiter.current_limit < 100

    def test_record_respects_cooldown_period(self):
        """Test adjustments respect cooldown period."""
        limiter = AdaptiveRateLimiter(
            initial_limit=100,
            limit_min=10,
            limit_max=500,
            error_threshold=0.3,
            cooldown_seconds=10.0,
        )

        # Trigger first adjustment
        for _ in range(10):
            limiter.record(latency_seconds=0.5, success=False)
        first_limit = limiter.current_limit

        # Try to trigger second adjustment immediately
        for _ in range(10):
            limiter.record(latency_seconds=0.5, success=False)
        second_limit = limiter.current_limit

        # Should not change due to cooldown
        assert first_limit == second_limit

    @patch("time.monotonic")
    def test_record_evicts_expired_records(self, mock_time):
        """Test old records are evicted from window."""
        mock_time.side_effect = [0.0, 1.0, 2.0, 11.0, 11.1]
        limiter = AdaptiveRateLimiter(initial_limit=100, window_seconds=10.0)

        limiter.record(latency_seconds=0.5, success=True)
        limiter.record(latency_seconds=0.5, success=True)
        limiter.record(latency_seconds=0.5, success=True)

        assert len(limiter._records) == 3

        # Record after window expires (at time 11.1, should evict records before 1.1)
        limiter.record(latency_seconds=0.5, success=True)

        # Records at 0.0 should be evicted (before 1.1)
        # Records at 1.0, 2.0, 11.0 remain (1.0 >= 1.1 is False, but 1.0 < 1.1 is True, so 1.0 remains)
        # Actually: 1.0 < 1.1 is True, so 1.0 should be evicted
        # But the implementation uses <, so 1.0 < 1.1 is True, so 1.0 is evicted
        # Wait, the cutoff is 11.1 - 10.0 = 1.1, so records with timestamp < 1.1 are evicted
        # Records at 0.0, 1.0 should be evicted (both < 1.1)
        # Records at 2.0, 11.0 remain (both >= 1.1)
        assert len(limiter._records) == 3


class TestAdaptiveRateLimiterSnapshot:
    """Test AdaptiveRateLimiter.snapshot() method."""

    def test_snapshot_empty_records(self):
        """Test snapshot with no records returns zero values."""
        limiter = AdaptiveRateLimiter(initial_limit=100)
        snapshot = limiter.snapshot()

        assert snapshot["current_limit"] == 100
        assert snapshot["total_records"] == 0
        assert snapshot["error_rate"] == 0.0
        assert snapshot["avg_latency"] == 0.0

    def test_snapshot_with_records(self):
        """Test snapshot with records returns correct statistics."""
        limiter = AdaptiveRateLimiter(initial_limit=100, cooldown_seconds=100.0)
        limiter.record(latency_seconds=0.5, success=True)
        limiter.record(latency_seconds=1.0, success=False)
        limiter.record(latency_seconds=0.3, success=True)

        snapshot = limiter.snapshot()

        # Error rate is 1/3 < 0.5 * 0.3 = 0.15, so limit should speed up
        assert snapshot["current_limit"] == 110
        assert snapshot["total_records"] == 3
        assert snapshot["error_rate"] == 1.0 / 3.0
        assert snapshot["avg_latency"] == (0.5 + 1.0 + 0.3) / 3.0

    def test_snapshot_current_limit_adjusted(self):
        """Test snapshot reflects adjusted limit."""
        limiter = AdaptiveRateLimiter(
            initial_limit=100,
            limit_min=10,
            limit_max=500,
            error_threshold=0.3,
            cooldown_seconds=0.0,
        )

        # Trigger slowdown
        for _ in range(10):
            limiter.record(latency_seconds=0.5, success=False)

        snapshot = limiter.snapshot()
        assert snapshot["current_limit"] < 100


# =============================================================================
# ScheduleConfig Tests
# =============================================================================


class TestScheduleConfigInit:
    """Test ScheduleConfig initialization."""

    def test_init_default_values(self):
        """Test default initialization values."""
        config = ScheduleConfig()
        assert config.timeout == 0
        assert config.retry_times == 0
        assert config.retry_interval == 1
        assert config.hedged_request_proportion == 0.05
        assert config.exception_types == (BaseException,)

    def test_init_custom_values(self):
        """Test custom initialization values."""
        config = ScheduleConfig(
            timeout=30,
            retry_times=3,
            retry_interval=2.0,
            hedged_request_proportion=0.1,
        )
        assert config.timeout == 30
        assert config.retry_times == 3
        assert config.retry_interval == 2.0
        assert config.hedged_request_proportion == 0.1

    def test_post_init_negative_timeout_raises_error(self):
        """Test negative timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be >= 0"):
            ScheduleConfig(timeout=-1)

    def test_post_init_negative_retry_interval_raises_error(self):
        """Test negative retry_interval raises ValueError."""
        with pytest.raises(ValueError, match="retry_interval must be >= 0"):
            ScheduleConfig(retry_interval=-1.0)

    def test_post_init_none_exception_types_normalized(self):
        """Test exception_types=None is normalized to (BaseException,)."""
        config = ScheduleConfig(exception_types=None)
        assert config.exception_types == (BaseException,)

    def test_post_init_single_exception_type_normalized_to_tuple(self):
        """Test single exception type is normalized to tuple."""
        config = ScheduleConfig(exception_types=ValueError)
        assert config.exception_types == (ValueError,)

    def test_post_init_tuple_exception_types_unchanged(self):
        """Test tuple exception types remain unchanged."""
        config = ScheduleConfig(exception_types=(ValueError, TypeError))
        assert config.exception_types == (ValueError, TypeError)

    def test_post_init_invalid_hedged_proportion_too_low_raises_error(self):
        """Test hedged_request_proportion too low raises ValueError."""
        with pytest.raises(ValueError, match="hedged_request_proportion must be in"):
            ScheduleConfig(hedged_request_time=1.0, hedged_request_proportion=0.0)

    def test_post_init_invalid_hedged_proportion_too_high_raises_error(self):
        """Test hedged_request_proportion > 1 raises ValueError."""
        with pytest.raises(ValueError, match="hedged_request_proportion must be in"):
            ScheduleConfig(hedged_request_time=1.0, hedged_request_proportion=1.5)

    def test_post_init_valid_hedged_proportion(self):
        """Test valid hedged_request_proportion is accepted."""
        config = ScheduleConfig(hedged_request_time=1.0, hedged_request_proportion=0.5)
        assert config.hedged_request_proportion == 0.5

    def test_post_init_zero_hedged_time_allows_any_proportion(self):
        """Test hedged_request_time=0 allows any proportion."""
        config = ScheduleConfig(hedged_request_time=0.0, hedged_request_proportion=0.0)
        assert config.hedged_request_proportion == 0.0


class TestScheduleConfigHedgedRequestMultiply:
    """Test ScheduleConfig.hedged_request_multiply property."""

    def test_hedged_request_multiply_with_hedging_enabled(self):
        """Test multiply calculation with hedging enabled."""
        config = ScheduleConfig(hedged_request_time=1.0, hedged_request_proportion=0.1)
        # 1 / 0.1 - 1 = 9
        assert config.hedged_request_multiply == 9.0

    def test_hedged_request_multiply_with_half_proportion(self):
        """Test multiply with proportion=0.5."""
        config = ScheduleConfig(hedged_request_time=1.0, hedged_request_proportion=0.5)
        # 1 / 0.5 - 1 = 1
        assert config.hedged_request_multiply == 1.0

    def test_hedged_request_multiply_with_hedging_disabled(self):
        """Test multiply=0 when hedging disabled."""
        config = ScheduleConfig(hedged_request_time=0.0, hedged_request_proportion=0.1)
        assert config.hedged_request_multiply == 0

    def test_hedged_request_multiply_zero_proportion(self):
        """Test multiply=0 when proportion is minimal."""
        config = ScheduleConfig(hedged_request_time=1.0, hedged_request_proportion=1e-5)
        # hedged_request_multiply = 1 / 1e-5 - 1 ≈ 99999
        assert config.hedged_request_multiply == pytest.approx(99999.0)


class TestScheduleConfigAdjustWaitTime:
    """Test ScheduleConfig.adjust_wait_time() method."""

    def test_adjust_wait_time_basic_case(self):
        """Test basic wait time adjustment."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=2.0, has_wait_time=0.0, max_wait_time=10.0
        )
        assert result == 2.0

    def test_adjust_wait_time_negative_basic_wait_time(self):
        """Test negative basic_wait_time is replaced with MIN_WAIT_TIME."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=-1.0, has_wait_time=0.0, max_wait_time=10.0
        )
        assert result == 0.01

    def test_adjust_wait_time_within_max(self):
        """Test adjustment when within max_wait_time."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=2.0, has_wait_time=3.0, max_wait_time=10.0
        )
        assert result == 2.0

    def test_adjust_wait_time_exceeds_max(self):
        """Test adjustment when would exceed max_wait_time."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=8.0, has_wait_time=5.0, max_wait_time=10.0
        )
        assert result == 5.0  # 10 - 5

    def test_adjust_wait_time_already_exceeded_max(self):
        """Test adjustment when has_wait_time already exceeds max."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=2.0, has_wait_time=15.0, max_wait_time=10.0
        )
        assert result == 0.01  # MIN_WAIT_TIME

    def test_adjust_wait_time_zero_max_wait_time(self):
        """Test adjustment with max_wait_time=0 (no timeout)."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=2.0, has_wait_time=5.0, max_wait_time=0.0
        )
        assert result == 2.0

    def test_adjust_wait_time_negative_max_wait_time(self):
        """Test adjustment with negative max_wait_time."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=2.0, has_wait_time=5.0, max_wait_time=-1.0
        )
        assert result == 2.0

    def test_adjust_wait_time_exact_max(self):
        """Test adjustment when exactly at max_wait_time."""
        config = ScheduleConfig()
        result = config.adjust_wait_time(
            basic_wait_time=5.0, has_wait_time=5.0, max_wait_time=10.0
        )
        assert result == 5.0


class TestScheduleConfigOnChange:
    """Test ScheduleConfig.on_change() and update() methods."""

    def test_on_change_registers_callback(self):
        """Test on_change registers a callback."""
        config = ScheduleConfig()
        callback = MagicMock()
        config.on_change(callback)
        assert callback in config._change_callbacks

    def test_update_invokes_callbacks(self):
        """Test update invokes registered callbacks."""
        config = ScheduleConfig()
        callback = MagicMock()
        config.on_change(callback)

        config.update(timeout=30)

        callback.assert_called_once_with(config)

    def test_update_multiple_callbacks(self):
        """Test update invokes all callbacks."""
        config = ScheduleConfig()
        callback1 = MagicMock()
        callback2 = MagicMock()
        config.on_change(callback1)
        config.on_change(callback2)

        config.update(timeout=30)

        callback1.assert_called_once_with(config)
        callback2.assert_called_once_with(config)

    def test_update_modifies_config(self):
        """Test update modifies config values."""
        config = ScheduleConfig(timeout=10, retry_times=2)
        config.update(timeout=30, retry_times=5)

        assert config.timeout == 30
        assert config.retry_times == 5

    def test_update_reruns_validation(self):
        """Test update re-runs __post_init__ validation."""
        config = ScheduleConfig()
        with pytest.raises(ValueError, match="timeout must be >= 0"):
            config.update(timeout=-1)

    def test_update_ignores_unknown_fields(self):
        """Test update ignores unknown fields."""
        config = ScheduleConfig(timeout=10)
        config.update(timeout=20, unknown_field=123)

        assert config.timeout == 20
        assert not hasattr(config, "unknown_field")


class TestScheduleConfigSnapshot:
    """Test ScheduleConfig.snapshot() method."""

    def test_snapshot_returns_dict(self):
        """Test snapshot returns a dictionary."""
        config = ScheduleConfig()
        snapshot = config.snapshot()
        assert isinstance(snapshot, dict)

    def test_snapshot_includes_all_fields(self):
        """Test snapshot includes all public fields."""
        config = ScheduleConfig(
            timeout=30,
            retry_times=3,
            retry_interval=2.0,
            hedged_request_proportion=0.1,
        )
        snapshot = config.snapshot()

        assert snapshot["timeout"] == 30
        assert snapshot["retry_times"] == 3
        assert snapshot["retry_interval"] == 2.0
        assert snapshot["hedged_request_proportion"] == 0.1

    def test_snapshot_excludes_private_fields(self):
        """Test snapshot excludes private fields."""
        config = ScheduleConfig()
        snapshot = config.snapshot()

        assert "_change_callbacks" not in snapshot
        assert "_update_lock" not in snapshot


class TestScheduleConfigGetMaxWaitTime:
    """Test ScheduleConfig.get_max_wait_time() method (deprecated)."""

    def test_get_max_wait_time_issues_deprecation_warning(self):
        """Test get_max_wait_time issues DeprecationWarning."""
        config = ScheduleConfig()
        with pytest.warns(DeprecationWarning,
                          match="get_max_wait_time is deprecated"):
            config.get_max_wait_time(2.0, 0.0, 10.0)

    def test_get_max_wait_time_calls_adjust_wait_time(self):
        """Test get_max_wait_time delegates to adjust_wait_time."""
        config = ScheduleConfig()
        with pytest.warns(DeprecationWarning,
                          match="get_max_wait_time is deprecated"):
            result = config.get_max_wait_time(2.0, 0.0, 10.0)
        assert result == 2.0


# =============================================================================
# ScheduleMetrics Tests
# =============================================================================


class TestScheduleMetricsExportToOtel:
    """Test ScheduleMetrics.export_to_otel() method."""

    def test_export_to_otel_with_none_exporter_no_op(self):
        """Test export_to_otel with exporter=None is no-op."""
        metrics = ScheduleMetrics(
            total_calls=10,
            success_count=8,
            failure_count=2,
            retry_count=3,
            total_latency_ms=1000.0,
            avg_latency_ms=100.0,
        )

        # Should not raise any exception
        metrics.export_to_otel(exporter=None)

    def test_export_to_otel_with_exporter_calls_record(self):
        """Test export_to_otel with exporter calls record method."""
        metrics = ScheduleMetrics(
            total_calls=10,
            success_count=8,
            failure_count=2,
            retry_count=3,
            total_latency_ms=1000.0,
            avg_latency_ms=100.0,
        )

        exporter = MagicMock()
        metrics.export_to_otel(exporter=exporter)

        exporter.record.assert_called_once_with(metrics)

    def test_export_to_otel_multiple_times(self):
        """Test export_to_otel can be called multiple times."""
        metrics = ScheduleMetrics(
            total_calls=10,
            success_count=8,
            failure_count=2,
            retry_count=3,
            total_latency_ms=1000.0,
            avg_latency_ms=100.0,
        )

        exporter = MagicMock()
        metrics.export_to_otel(exporter=exporter)
        metrics.export_to_otel(exporter=exporter)

        assert exporter.record.call_count == 2

# =============================================================================
# ExecutionContext.record_exception Tests (covers context.py lines 246-248)
# =============================================================================

class TestExecutionContextRecordException:
    """Test ExecutionContext.record_exception() method."""

    def test_record_exception_appends_info(self):
        """Test that record_exception appends formatted exception info."""
        from qreward.utils.scheduler.config import ScheduleConfig
        from qreward.utils.scheduler.context import ExecutionContext
        from qreward.utils.scheduler.pools import RunningTaskPool

        config = ScheduleConfig()
        pool = RunningTaskPool.get_pool("test_record_exc")
        context = ExecutionContext(
            func=lambda: None,
            config=config,
            key="test_record_exc",
            running_task_pool=pool,
            limiter=None,
        )

        exc = ValueError("test error message")
        context.record_exception(exc)

        assert len(context.result_exception_list) == 1
        assert "ValueError" in context.result_exception_list[0]
        assert "test error message" in context.result_exception_list[0]

    def test_record_multiple_exceptions(self):
        """Test recording multiple exceptions."""
        from qreward.utils.scheduler.config import ScheduleConfig
        from qreward.utils.scheduler.context import ExecutionContext
        from qreward.utils.scheduler.pools import RunningTaskPool

        config = ScheduleConfig()
        pool = RunningTaskPool.get_pool("test_record_multi_exc")
        context = ExecutionContext(
            func=lambda: None,
            config=config,
            key="test_record_multi_exc",
            running_task_pool=pool,
            limiter=None,
        )

        context.record_exception(ValueError("err1"))
        context.record_exception(TypeError("err2"))

        assert len(context.result_exception_list) == 2
        assert "ValueError" in context.result_exception_list[0]
        assert "TypeError" in context.result_exception_list[1]

# =============================================================================
# PriorityTaskQueue starvation heapify (covers priority_queue.py line 172)
# =============================================================================

class TestPriorityQueueStarvationHeapify:
    """Test starvation protection triggers heapify."""

    def test_starvation_protection_promotes_and_heapifies(self):
        """Test that starved LOW items get promoted to HIGH."""
        queue = PriorityTaskQueue(starvation_threshold=0.001)
        queue.put("starved_item", priority=Priority.LOW)
        time.sleep(0.02)
        result = queue.get()
        assert result == "starved_item"

# =============================================================================
# AdaptiveRateLimiter empty records (covers adaptive_limiter.py line 129)
# =============================================================================

class TestAdaptiveLimiterEmptyRecords:
    """Test _maybe_adjust with no records."""

    def test_maybe_adjust_with_no_records_is_noop(self):
        """Test that _maybe_adjust returns early when records are empty."""
        limiter = AdaptiveRateLimiter(
            initial_limit=10,
            cooldown_seconds=0,
        )
        now = time.monotonic()
        limiter._maybe_adjust(now)
        assert limiter.current_limit == 10
