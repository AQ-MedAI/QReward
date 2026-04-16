"""Unit tests for scheduler core modules: overload, pools, and limiter."""

import time
from unittest.mock import Mock, patch

import pytest

from qreward.utils.scheduler.overload import OverloadChecker
from qreward.utils.scheduler.pools import RunningTaskPool
from qreward.utils.scheduler.limiter import LimiterPool


# =============================================================================
# Fixtures for test cleanup
# =============================================================================


@pytest.fixture(autouse=True)
def cleanup_pools():
    """Clean up global pools after each test to avoid interference."""
    yield
    RunningTaskPool.global_task_pool.clear()
    LimiterPool.global_limiter_pool.clear()


# =============================================================================
# OverloadChecker Tests
# =============================================================================


class TestOverloadCheckerHTTPStatus:
    """Test HTTP status code detection in OverloadChecker."""

    def test_check_single_status_429(self):
        """Test detection of 429 Too Many Requests."""
        exc = Mock()
        exc.status_code = 429
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_status_503(self):
        """Test detection of 503 Service Unavailable."""
        exc = Mock()
        exc.status_code = 503
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_status_502(self):
        """Test detection of 502 Bad Gateway."""
        exc = Mock()
        exc.status_code = 502
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_status_504(self):
        """Test detection of 504 Gateway Timeout."""
        exc = Mock()
        exc.status_code = 504
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_status_200(self):
        """Test that 200 OK is not detected as overload."""
        exc = Mock()
        exc.status_code = 200
        exc.__class__.__module__ = "builtins"
        exc.__class__.__name__ = "Mock"
        exc.args = ("200 OK",)
        assert OverloadChecker._check_single(exc) is False

    def test_check_single_no_status_code(self):
        """Test exception without status_code attribute."""
        exc = ValueError("test")
        assert OverloadChecker._check_single(exc) is False


class TestOverloadCheckerExceptionType:
    """Test exception type detection in OverloadChecker."""

    def test_check_single_timeout_error(self):
        """Test detection of TimeoutError."""
        exc = TimeoutError("timeout")
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_connection_error(self):
        """Test detection of ConnectionError."""
        exc = ConnectionError("connection failed")
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_generic_error(self):
        """Test that generic errors are not detected as overload."""
        exc = ValueError("invalid value")
        assert OverloadChecker._check_single(exc) is False


class TestOverloadCheckerLibrarySpecific:
    """Test library-specific exception detection."""

    def test_check_single_requests_connect_timeout(self):
        """Test detection of requests.ConnectTimeout."""
        # Create a mock exception that looks like requests.ConnectTimeout
        exc = Mock()
        exc.__class__.__module__ = "requests.exceptions"
        exc.__class__.__name__ = "ConnectTimeout"
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_httpx_network_error(self):
        """Test detection of httpx.NetworkError."""
        exc = Mock()
        exc.__class__.__module__ = "httpx"
        exc.__class__.__name__ = "NetworkError"
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_non_library_exception(self):
        """Test that non-library exceptions are not detected."""
        exc = Mock()
        exc.__class__.__module__ = "custom.module"
        exc.__class__.__name__ = "CustomError"
        exc.__str__ = lambda self: "normal error message"
        exc.args = ("normal error message",)
        assert OverloadChecker._check_single(exc) is False


class TestOverloadCheckerMessageContent:
    """Test message content keyword detection."""

    def test_check_single_message_overload(self):
        """Test detection of 'overload' in message."""
        exc = Exception("Server is overloaded")
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_message_timeout(self):
        """Test detection of 'timeout' in message."""
        exc = Exception("Request timeout")
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_message_no_keyword(self):
        """Test that messages without keywords are not detected."""
        exc = Exception("Normal error message")
        assert OverloadChecker._check_single(exc) is False

    def test_check_single_message_case_insensitive(self):
        """Test case-insensitive keyword detection."""
        exc = Exception("SERVER OVERLOAD")
        assert OverloadChecker._check_single(exc) is True


class TestOverloadCheckerSystemLevel:
    """Test system-level overload indicators."""

    def test_check_single_errno_24(self):
        """Test detection of errno 24 (too many open files)."""
        exc = OSError(24, "Too many open files")
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_normal_os_error(self):
        """Test that normal OS errors are not detected."""
        exc = OSError(2, "No such file")
        assert OverloadChecker._check_single(exc) is False


class TestOverloadCheckerExceptionArgs:
    """Test exception args checking."""

    def test_check_single_args_with_keyword(self):
        """Test detection of keyword in exception args."""
        exc = Exception("normal message", "overload detected")
        assert OverloadChecker._check_single(exc) is True

    def test_check_single_args_no_keyword(self):
        """Test that args without keywords are not detected."""
        exc = Exception("normal message", "another normal message")
        assert OverloadChecker._check_single(exc) is False

    def test_check_single_empty_args(self):
        """Test exception with empty args."""
        exc = Exception()
        assert OverloadChecker._check_single(exc) is False


class TestOverloadCheckerExceptionChain:
    """Test exception chain traversal."""

    def test_check_normal_exception(self):
        """Test that normal exceptions return False."""
        exc = ValueError("normal error")
        assert OverloadChecker.check(exc) is False

    def test_check_overload_exception(self):
        """Test that overload exceptions return True."""
        exc = TimeoutError("timeout")
        assert OverloadChecker.check(exc) is True

    def test_check_exception_chain_with_cause(self):
        """Test traversal through __cause__ chain."""
        # Create exception chain: ValueError -> TimeoutError
        root = TimeoutError("timeout")
        wrapped = ValueError("wrapper")
        wrapped.__cause__ = root
        assert OverloadChecker.check(wrapped) is True

    def test_check_exception_chain_with_context(self):
        """Test traversal through __context__ chain."""
        # Create exception chain: ValueError -> ConnectionError
        try:
            try:
                raise ConnectionError("connection failed")
            except ConnectionError as e:
                raise ValueError("wrapper") from e
        except ValueError as exc:
            assert OverloadChecker.check(exc) is True

    def test_check_circular_reference_protection(self):
        """Test protection against circular exception references."""
        exc1 = ValueError("error1")
        exc2 = ValueError("error2")
        # Create circular reference
        exc1.__cause__ = exc2
        exc2.__cause__ = exc1
        # Should not infinite loop
        assert OverloadChecker.check(exc1) is False

    def test_check_deep_chain(self):
        """Test traversal of deep exception chains."""
        # Create a chain of 10 exceptions
        root = TimeoutError("timeout")
        exc = root
        for i in range(9):
            new_exc = ValueError(f"level{i}")
            new_exc.__cause__ = exc
            exc = new_exc
        assert OverloadChecker.check(exc) is True

    def test_check_chain_no_overload(self):
        """Test chain without any overload signals."""
        exc1 = ValueError("error1")
        exc2 = ValueError("error2")
        exc1.__cause__ = exc2
        assert OverloadChecker.check(exc1) is False


# =============================================================================
# RunningTaskPool Tests
# =============================================================================


class TestRunningTaskPoolSingleton:
    """Test singleton pattern in RunningTaskPool."""

    def test_get_pool_singleton(self):
        """Test that same key returns same instance."""
        pool1 = RunningTaskPool.get_pool("test_key")
        pool2 = RunningTaskPool.get_pool("test_key")
        assert pool1 is pool2

    def test_get_pool_different_keys(self):
        """Test that different keys return different instances."""
        pool1 = RunningTaskPool.get_pool("key1")
        pool2 = RunningTaskPool.get_pool("key2")
        assert pool1 is not pool2

    def test_get_pool_custom_params(self):
        """Test get_pool with custom parameters."""
        pool = RunningTaskPool.get_pool(
            "custom_key", window_max_size=5, window_interval=30, threshold=10
        )
        assert pool._window_max_size == 5
        assert pool._window_interval == 30
        assert pool._threshold == 10


class TestRunningTaskPoolAdd:
    """Test add method in RunningTaskPool."""

    def test_add_increase(self):
        """Test increasing task count."""
        pool = RunningTaskPool.get_pool("add_test")
        result = pool.add(1)
        assert result == 1
        result = pool.add(2)
        assert result == 3

    def test_add_decrease(self):
        """Test decreasing task count."""
        pool = RunningTaskPool.get_pool("decrease_test")
        pool.add(5)
        result = pool.add(-3)
        assert result == 2

    def test_add_zero(self):
        """Test adding zero."""
        pool = RunningTaskPool.get_pool("zero_test")
        result = pool.add(0)
        assert result == 0

    def test_add_negative_total(self):
        """Test that total can go negative."""
        pool = RunningTaskPool.get_pool("negative_test")
        result = pool.add(-5)
        assert result == -5


class TestRunningTaskPoolHistoricalPeak:
    """Test historical peak recording and window rolling."""

    def test_historical_peak_recording(self):
        """Test that historical peak is recorded."""
        pool = RunningTaskPool.get_pool(
            "peak_test", window_max_size=3, window_interval=1
        )

        # Add tasks and record peak
        pool.add(10)
        assert pool._value == 10

        # Check that peak was recorded in current window
        current_key = int(time.time()) // 1
        if current_key in pool._max_size_map:
            assert pool._max_size_map[current_key] == 10

    def test_window_rolling(self):
        """Test that old windows are removed when limit is reached."""
        pool = RunningTaskPool.get_pool(
            "rolling_test", window_max_size=2, window_interval=1
        )

        # Add tasks in multiple windows
        with patch("qreward.utils.scheduler.pools.time") as mock_time:
            mock_time.time.return_value = 1000
            pool.add(5)

            mock_time.time.return_value = 1002  # New window
            pool.add(8)

            # New window, should remove first
            mock_time.time.return_value = 1004
            pool.add(3)

            # First window should be removed
            assert len(pool._max_size_map) == 2
            assert 1000 not in pool._max_size_map

    def test_peak_in_same_window(self):
        """Test that only peak value is kept in same window."""
        pool = RunningTaskPool.get_pool(
            "same_window_test", window_max_size=3, window_interval=1
        )

        with patch("qreward.utils.scheduler.pools.time") as mock_time:
            mock_time.time.return_value = 1000
            pool.add(5)
            pool.add(3)  # Lower than peak
            pool.add(7)  # Higher than peak

            # Should keep the peak (5 + 3 + 7 = 15)
            assert pool._max_size_map[1000] == 15


class TestRunningTaskPoolCanSubmit:
    """Test can_submit method in RunningTaskPool."""

    def test_can_submit_below_threshold(self):
        """Test that tasks below threshold are always allowed."""
        pool = RunningTaskPool.get_pool("threshold_test", threshold=5)
        pool.add(3)
        assert pool.can_submit() is True
        pool.add(1)
        assert pool.can_submit() is True

    def test_can_submit_at_threshold(self):
        """Test that tasks at threshold are allowed."""
        pool = RunningTaskPool.get_pool("at_threshold_test", threshold=5)
        pool.add(5)
        assert pool.can_submit() is True

    def test_can_submit_above_threshold_no_history(self):
        """Test that tasks above threshold with no history are rejected."""
        pool = RunningTaskPool.get_pool("no_history_test", threshold=5)
        pool.add(10)
        assert pool.can_submit() is False

    def test_can_submit_above_threshold_with_higher_history(self):
        """Test that tasks are allowed when historical peak is higher."""
        pool = RunningTaskPool.get_pool(
            "higher_history_test",
            threshold=5,
            window_max_size=3,
            window_interval=1,
        )

        with patch("qreward.utils.scheduler.pools.time") as mock_time:
            # Create high historical peak
            mock_time.time.return_value = 1000
            pool.add(20)

            # Current value is lower than historical peak
            mock_time.time.return_value = 1002
            pool.add(-10)  # Now value is 10

            # Should be allowed because historical peak (20) > current (10) * 1
            assert pool.can_submit() is True

    def test_can_submit_above_threshold_with_lower_history(self):
        """Test that tasks are rejected when historical peak is not higher."""
        pool = RunningTaskPool.get_pool(
            "lower_history_test",
            threshold=5,
            window_max_size=3,
            window_interval=1,
        )

        with patch("qreward.utils.scheduler.pools.time") as mock_time:
            # Create low historical peak
            mock_time.time.return_value = 1000
            pool.add(10)

            # Current value is higher than historical peak
            mock_time.time.return_value = 1002
            pool.add(5)  # Now value is 15

            # Should be rejected because historical
            # peak (10) <= current (15) * 1
            assert pool.can_submit() is False

    def test_can_submit_with_multiply(self):
        """Test can_submit with multiply parameter."""
        pool = RunningTaskPool.get_pool(
            "multiply_test", threshold=5, window_max_size=3, window_interval=1
        )

        with patch("qreward.utils.scheduler.pools.time") as mock_time:
            # Historical peak is 10
            mock_time.time.return_value = 1000
            pool.add(10)

            # Current value is 7
            mock_time.time.return_value = 1002
            pool.add(-3)

            # With multiply=1, historical (10) > current (7) * 1 -> True
            assert pool.can_submit(multiply=1) is True

            # With multiply=2, historical (10) <= current (7) * 2 (14) -> False
            assert pool.can_submit(multiply=2) is False


class TestRunningTaskPoolLessThan:
    """Test deprecated less_than method."""

    def test_less_than_deprecated_warning(self):
        """Test that less_than shows deprecation warning."""
        pool = RunningTaskPool.get_pool("deprecated_test")
        with pytest.warns(DeprecationWarning, match="less_than is deprecated"):
            pool.less_than()

    def test_less_than_functionality(self):
        """Test that less_than still works correctly."""
        pool = RunningTaskPool.get_pool("deprecated_test2", threshold=5)
        pool.add(3)
        # Should behave same as can_submit
        with pytest.warns(DeprecationWarning):
            assert pool.less_than() is True


# =============================================================================
# LimiterPool Tests
# =============================================================================


class TestLimiterPoolSingleton:
    """Test singleton pattern in LimiterPool."""

    def test_get_pool_singleton(self):
        """Test that same key returns same instance."""
        pool1 = LimiterPool.get_pool("test_key", 10, 1.0)
        pool2 = LimiterPool.get_pool("test_key", 10, 1.0)
        assert pool1 is pool2

    def test_get_pool_different_keys(self):
        """Test that different keys return different instances."""
        pool1 = LimiterPool.get_pool("key1", 10, 1.0)
        pool2 = LimiterPool.get_pool("key2", 10, 1.0)
        assert pool1 is not pool2

    def test_get_pool_invalid_rate(self):
        """Test that invalid rate returns None."""
        pool = LimiterPool.get_pool("invalid_rate", 0, 1.0)
        assert pool is None

    def test_get_pool_invalid_window(self):
        """Test that invalid window returns None."""
        pool = LimiterPool.get_pool("invalid_window", 10, 0)
        assert pool is None

    def test_get_pool_negative_rate(self):
        """Test that negative rate returns None."""
        pool = LimiterPool.get_pool("negative_rate", -5, 1.0)
        assert pool is None


class TestLimiterPoolInit:
    """Test LimiterPool initialization."""

    def test_init_valid_params(self):
        """Test initialization with valid parameters."""
        pool = LimiterPool(rate=10, window=1.0)
        assert pool.rate == 10
        assert pool.window == 1.0

    def test_init_invalid_rate(self):
        """Test that invalid rate raises ValueError."""
        with pytest.raises(ValueError, match="rate / window must be positive"):
            LimiterPool(rate=0, window=1.0)

    def test_init_invalid_window(self):
        """Test that invalid window raises ValueError."""
        with pytest.raises(ValueError, match="rate / window must be positive"):
            LimiterPool(rate=10, window=0)

    def test_init_negative_window(self):
        """Test that negative window raises ValueError."""
        with pytest.raises(ValueError, match="rate / window must be positive"):
            LimiterPool(rate=10, window=-1.0)


class TestLimiterPoolAllow:
    """Test allow method in LimiterPool."""

    def test_allow_within_limit(self):
        """Test that requests within limit are allowed."""
        pool = LimiterPool(rate=5, window=1.0)
        for i in range(5):
            assert pool.allow() is True

    def test_allow_exceeds_limit(self):
        """Test that requests exceeding limit are blocked."""
        pool = LimiterPool(rate=3, window=1.0)
        # Fill the window
        for i in range(3):
            assert pool.allow() is True
        # Next request should be blocked (will wait and timeout)
        with patch("qreward.utils.scheduler.limiter.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            assert pool.allow(timeout=0.1) is False

    def test_allow_window_expiration(self):
        """Test that expired requests are removed from window."""
        pool = LimiterPool(rate=3, window=1.0)

        with patch("qreward.utils.scheduler.limiter.time") as mock_time:
            mock_time.monotonic.return_value = 0.0

            # Fill the window
            for i in range(3):
                assert pool.allow() is True

            # Next request should be blocked
            assert pool.allow(timeout=0.1) is False

            # Advance time beyond window
            mock_time.monotonic.return_value = 1.5

            # Now should be allowed again
            assert pool.allow() is True

    def test_allow_with_timeout(self):
        """Test allow with timeout parameter."""
        pool = LimiterPool(rate=2, window=1.0)

        # Fill the window
        pool.allow()
        pool.allow()

        # Request with timeout should eventually return False
        with patch("qreward.utils.scheduler.limiter.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            # This should wait and timeout
            result = pool.allow(timeout=0.1)
            assert result is False

    def test_allow_timeout_not_expired(self):
        """Test that allow waits for window to expire."""
        pool = LimiterPool(rate=2, window=0.1)

        # Fill the window
        pool.allow()
        pool.allow()

        # Request should wait and succeed when window expires
        start = time.monotonic()
        result = pool.allow(timeout=0.2)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.1  # Should have waited for window to expire


class TestLimiterPoolAsyncAllow:
    """Test async_allow method in LimiterPool."""

    @pytest.mark.asyncio
    async def test_async_allow_within_limit(self):
        """Test that async requests within limit are allowed."""
        pool = LimiterPool(rate=5, window=1.0)
        for i in range(5):
            assert await pool.async_allow() is True

    @pytest.mark.asyncio
    async def test_async_allow_exceeds_limit(self):
        """Test that async requests exceeding limit are blocked."""
        pool = LimiterPool(rate=3, window=1.0)
        # Fill the window
        for i in range(3):
            assert await pool.async_allow() is True
        # Next request should be blocked (will wait and timeout)
        with patch("qreward.utils.scheduler.limiter.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            assert await pool.async_allow(timeout=0.1) is False

    @pytest.mark.asyncio
    async def test_async_allow_window_expiration(self):
        """Test that async expired requests are removed from window."""
        pool = LimiterPool(rate=3, window=1.0)

        with patch("qreward.utils.scheduler.limiter.time") as mock_time:
            mock_time.monotonic.return_value = 0.0

            # Fill the window
            for i in range(3):
                assert await pool.async_allow() is True

            # Next request should be blocked
            assert await pool.async_allow(timeout=0.1) is False

            # Advance time beyond window
            mock_time.monotonic.return_value = 1.5

            # Now should be allowed again
            assert await pool.async_allow() is True

    @pytest.mark.asyncio
    async def test_async_allow_with_timeout(self):
        """Test async_allow with timeout parameter."""
        pool = LimiterPool(rate=2, window=1.0)

        # Fill the window
        await pool.async_allow()
        await pool.async_allow()

        # Request with timeout should eventually return False
        with patch("qreward.utils.scheduler.limiter.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            result = await pool.async_allow(timeout=0.1)
            assert result is False

    @pytest.mark.asyncio
    async def test_async_allow_timeout_not_expired(self):
        """Test that async_allow waits for window to expire."""
        pool = LimiterPool(rate=2, window=0.1)

        # Fill the window
        await pool.async_allow()
        await pool.async_allow()

        # Request should wait and succeed when window expires
        start = time.monotonic()
        result = await pool.async_allow(timeout=0.2)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.1  # Should have waited for window to expire


class TestLimiterPoolCheckAndAdd:
    """Test _check_and_add method in LimiterPool."""

    def test_check_and_add_window_not_full(self):
        """Test that request is allowed when window is not full."""
        pool = LimiterPool(rate=5, window=1.0)
        assert pool._check_and_add() is True
        assert len(pool._times) == 1

    def test_check_and_add_window_full(self):
        """Test that request is blocked when window is full."""
        pool = LimiterPool(rate=2, window=1.0)
        assert pool._check_and_add() is True
        assert pool._check_and_add() is True
        assert pool._check_and_add() is False
        assert len(pool._times) == 2

    def test_check_and_add_expired_timestamps(self):
        """Test that expired timestamps are removed."""
        # Create a custom clock that returns different values
        time_values = [0.0, 0.1, 1.5]
        pool = LimiterPool(
            rate=5,
            window=1.0,
            clock=lambda: time_values.pop(0) if time_values else 1.5,
        )

        pool._check_and_add()  # Uses 0.0
        pool._check_and_add()  # Uses 0.1

        # Expired timestamps should be removed
        result = pool._check_and_add()  # Uses 1.5
        assert result is True
        # After time advances, old timestamps should be removed
        # Only the new timestamp should remain
        assert len(pool._times) == 1
        # The remaining timestamp should be the new one (1.5)
        assert pool._times[0] == 1.5


class TestLimiterPoolSleepTime:
    """Test _sleep_time method in LimiterPool."""

    def test_sleep_time_empty_list(self):
        """Test that empty list returns 0.01."""
        pool = LimiterPool(rate=5, window=1.0)
        sleep_time = pool._sleep_time()
        assert sleep_time == 0.01

    def test_sleep_time_with_timestamps(self):
        """Test sleep time calculation with timestamps."""
        pool = LimiterPool(rate=5, window=1.0)

        # Create a custom clock that returns different values
        time_values = [0.0, 0.5]
        pool._clock = lambda: time_values.pop(0) if time_values else 0.5

        pool._check_and_add()  # Uses 0.0
        sleep_time = pool._sleep_time()  # Uses 0.5
        # Should be window (1.0) + earliest (0.0) - current (0.5) = 0.5
        assert sleep_time == 0.5

    def test_sleep_time_expired_timestamp(self):
        """Test that expired timestamps return 0."""
        pool = LimiterPool(rate=5, window=1.0)

        # Create a custom clock that returns different values
        time_values = [0.0, 2.0]
        pool._clock = lambda: time_values.pop(0) if time_values else 2.0

        pool._check_and_add()  # Uses 0.0
        sleep_time = pool._sleep_time()  # Uses 2.0
        # Should be max(0.0, 0.0 + 1.0 - 2.0) = 0.0
        assert sleep_time == 0.0
