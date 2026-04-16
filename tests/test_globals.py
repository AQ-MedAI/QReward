from qreward.globals import (
    OVERLOAD_EXCEPTIONS,
    LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING,
    SYSTEM_OVERLOAD_INDICATORS,
    OVERLOAD_KEYWORDS,
)


class TestOverloadExceptions:
    """测试 OVERLOAD_EXCEPTIONS 常量"""

    def test_overload_exceptions_is_frozenset(self):
        """验证 OVERLOAD_EXCEPTIONS 是 frozenset 且包含关键异常名"""
        assert isinstance(
            OVERLOAD_EXCEPTIONS, frozenset
        ), "OVERLOAD_EXCEPTIONS 应该是 frozenset 类型"

        # 验证包含关键异常名
        expected_exceptions = [
            "asyncio.TimeoutError",
            "concurrent.futures.TimeoutError",
            "socket.timeout",
            "TimeoutError",
            "ReadTimeout",
            "ConnectTimeout",
            "ConnectionTimeout",
            "ConnectionError",
            "ConnectionRefusedError",
            "ConnectionAbortedError",
            "ConnectionResetError",
            "BrokenPipeError",
            "TooManyRedirects",
            "MemoryError",
            "OSError",
            "ResourceExhausted",
            "SSLError",
            "ProtocolError",
            "RemoteDisconnected",
            "IncompleteRead",
            "RateLimitExceeded",
            "ThrottlingException",
        ]

        for exception in expected_exceptions:
            assert (
                exception in OVERLOAD_EXCEPTIONS
            ), f"OVERLOAD_EXCEPTIONS 应该包含 '{exception}'"

    def test_overload_exceptions_contains_timeout_errors(self):
        """验证包含超时相关异常"""
        timeout_exceptions = [
            "asyncio.TimeoutError",
            "TimeoutError",
            "socket.timeout",
            "concurrent.futures.TimeoutError",
            "ReadTimeout",
            "ConnectTimeout",
            "ConnectionTimeout",
        ]

        for exception in timeout_exceptions:
            assert (
                exception in OVERLOAD_EXCEPTIONS
            ), f"OVERLOAD_EXCEPTIONS 应该包含超时异常 '{exception}'"

    def test_overload_exceptions_contains_connection_errors(self):
        """验证包含连接相关异常"""
        connection_exceptions = [
            "ConnectionError",
            "ConnectionRefusedError",
            "ConnectionAbortedError",
            "ConnectionResetError",
            "BrokenPipeError",
        ]

        for exception in connection_exceptions:
            assert (
                exception in OVERLOAD_EXCEPTIONS
            ), f"OVERLOAD_EXCEPTIONS 应该包含连接异常 '{exception}'"


class TestLibraryOverloadExceptionsMapping:
    """测试 LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING 常量"""

    def test_library_overload_exceptions_mapping_structure(self):
        """验证 LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING 是 dict，
        包含五个 key，每个 value 是 frozenset"""
        assert isinstance(
            LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING, dict
        ), "LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING 应该是 dict 类型"

        # 验证包含五个 key
        expected_keys = ["requests", "urllib3", "aiohttp", "httpx", "grpc"]
        for key in expected_keys:
            assert (
                key in LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING
            ), f"LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING 应该包含 key '{key}'"

        # 验证每个 value 是 frozenset
        for key, value in LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING.items():
            assert isinstance(value, frozenset), (
                f"LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING['{key}'] "
                f"应该是 frozenset 类型"
            )

    def test_library_mapping_values_are_nonempty(self):
        """验证每个库的异常集合非空"""
        for library_name, exceptions in LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING.items():
            assert len(exceptions) > 0, f"{library_name} 的异常集合不应该为空"


class TestSystemOverloadIndicators:
    """测试 SYSTEM_OVERLOAD_INDICATORS 常量"""

    def test_system_overload_indicators_is_frozenset(self):
        """验证 SYSTEM_OVERLOAD_INDICATORS 是 frozenset 且包含关键 errno"""
        assert isinstance(
            SYSTEM_OVERLOAD_INDICATORS, frozenset
        ), "SYSTEM_OVERLOAD_INDICATORS 应该是 frozenset 类型"

        # 验证包含关键 errno
        expected_errno = [
            "errno 24",  # EMFILE - Too many open files
            "errno 23",  # ENFILE - File table overflow
            "errno 11",  # EAGAIN/EWOULDBLOCK - Resource unavailable
            "errno 12",  # ENOMEM - Out of memory
            "errno 10054",  # WSAECONNRESET - Connection reset
            "errno 104",  # ECONNRESET - Connection reset
            "errno 110",  # ETIMEDOUT - Connection timed out (Linux)
            "errno 10060",  # WSAETIMEDOUT - Connection timed out (Windows)
        ]

        for errno in expected_errno:
            assert (
                errno in SYSTEM_OVERLOAD_INDICATORS
            ), f"SYSTEM_OVERLOAD_INDICATORS 应该包含 '{errno}'"


class TestOverloadKeywords:
    """测试 OVERLOAD_KEYWORDS 常量"""

    def test_overload_keywords_is_frozenset(self):
        """验证 OVERLOAD_KEYWORDS 是 frozenset 且包含关键词如 'overload',
        'timeout', 'rate limit'"""
        assert isinstance(
            OVERLOAD_KEYWORDS, frozenset
        ), "OVERLOAD_KEYWORDS 应该是 frozenset 类型"

        # 验证包含关键关键词
        expected_keywords = [
            "overload",
            "overloaded",
            "timeout",
            "time out",
            "deadline exceeded",
            "timed out",
            "rate limit",
            "throttled",
            "throttle",
            "resource",
            "memory",
            "unavailable",
            "not available",
            "too many",
            "exceeded",
            "limit",
            "quota",
            "capacity",
            "service unavailable",
            "temporarily unavailable",
            "server busy",
            "server overload",
            "high load",
            "traffic spike",
            "load",
            "traffic",
            "request rate",
        ]

        for keyword in expected_keywords:
            assert (
                keyword in OVERLOAD_KEYWORDS
            ), f"OVERLOAD_KEYWORDS 应该包含关键词 '{keyword}'"
