
OVERLOAD_EXCEPTIONS = frozenset([
    # 超时异常 - Timeout Exception
    "asyncio.TimeoutError",
    "concurrent.futures.TimeoutError",
    "socket.timeout",
    "TimeoutError",
    "ReadTimeout",
    "ConnectTimeout",
    "ConnectionTimeout",
    # 连接异常 - Connection Exception
    "ConnectionError",
    "ConnectionRefusedError",
    "ConnectionAbortedError",
    "ConnectionResetError",
    "BrokenPipeError",
    "TooManyRedirects",
    # 资源不足异常 - Resource Exhaustion Exception
    "MemoryError",
    "OSError",
    "ResourceExhausted",
    # 网络异常 - Network Exception
    "SSLError",
    "ProtocolError",
    "RemoteDisconnected",
    "IncompleteRead",
    # 其他可能的过载异常 - Other Possible Overload Exception
    "RateLimitExceeded",
    "ThrottlingException",
])

# from requests library
_REQUESTS_OVERLOAD_EXCEPTIONS = frozenset([
    "ConnectTimeout",
    "ReadTimeout",
    "ConnectionError",
    "TooManyRedirects",
    "SSLError",
])

# from urllib3 library
_URLLIB3_OVERLOAD_EXCEPTIONS = frozenset([
    "TimeoutError",
    "TimeoutStateError",
    "ReadTimeoutError",
    "ConnectTimeoutError",
    "ConnectionError",
    "NewConnectionError"
])

# from aiohttp library
_AIOHTTP_OVERLOAD_EXCEPTIONS = frozenset([
    "TimeoutError",
    "ClientError",
    "ServerDisconnectedError",
    "ClientConnectorError",
    "ServerTimeoutError",
])

# from httpx library
_HTTPX_OVERLOAD_EXCEPTIONS = frozenset([
    "TimeoutException",
    "ConnectTimeout",
    "ReadTimeout",
    "PoolTimeout",
    "NetworkError",
])

# from grpc library
_GRPC_OVERLOAD_EXCEPTIONS = frozenset([
    "DeadlineExceeded",
    "Unavailable",
    "ResourceExhausted",
])

# 框架级异常判断（library）
LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING = {
    "requests": _REQUESTS_OVERLOAD_EXCEPTIONS,
    "urllib3": _URLLIB3_OVERLOAD_EXCEPTIONS,
    "aiohttp": _AIOHTTP_OVERLOAD_EXCEPTIONS,
    "httpx": _HTTPX_OVERLOAD_EXCEPTIONS,
    "grpc": _GRPC_OVERLOAD_EXCEPTIONS,
}

# 系统级异常判断（errno）
SYSTEM_OVERLOAD_INDICATORS = frozenset([
    "errno 24",  # EMFILE - Too many open files
    "errno 23",  # ENFILE - File table overflow
    "errno 11",  # EAGAIN/EWOULDBLOCK - Resource temporarily unavailable
    "errno 12",  # ENOMEM - Out of memory
    "errno 10054",  # WSAECONNRESET - Connection reset by peer (Windows)
    "errno 104",  # ECONNRESET - Connection reset by peer (Linux)
    "errno 110",  # ETIMEDOUT - Connection timed out (Linux)
    "errno 10060",  # WSAETIMEDOUT - Connection timed out (Windows)
])

# 过载相关关键词
OVERLOAD_KEYWORDS = frozenset([
    # 资源不足相关
    "overload",
    "overloaded",
    "busy",
    "unavailable",
    "not available",
    "too many",
    "exceeded",
    "limit",
    "quota",
    "capacity",
    # 超时相关
    "timeout",
    "time out",
    "deadline exceeded",
    "timed out",
    # 连接相关
    "connection refused",
    "connection reset",
    "broken pipe",
    "connection pool",
    "pool exhausted",
    # 资源相关
    "resource",
    "memory",
    "cpu",
    "out of memory",
    "out of resources",
    "resource temporarily unavailable",
    # 服务相关
    "service unavailable",
    "temporarily unavailable",
    "server busy",
    "server overload",
    "high load",
    "traffic spike",
    # 负载相关
    "load",
    "high load",
    "traffic",
    "request rate",
    "rate limit",
    "throttled",
    "throttle",
    "limit",
    "limited",
    # 系统资源相关
    "too many open files",
    "file descriptor",
    "process limit",
    "thread limit",
])
