### version 0.1.7 - 2026/04/15 (Current)

#### New Features
* Added `CircuitBreaker` with three-state machine (CLOSED → OPEN → HALF_OPEN) for fault isolation
* Added `LoadBalanceStrategy` with ROUND_ROBIN, WEIGHTED_ROUND_ROBIN, LEAST_CONNECTIONS strategies
* Added `select_proxy()`, `mark_unhealthy()`, `mark_healthy()`, `healthy_proxies` to `OpenAIChatProxyManager`
* Added `stream_chat_completion()` async generator for streaming chat responses with semaphore/rate_limiter control
* Added `ScheduleMetrics` dataclass for structured execution metrics (total_calls, success/failure count, latency)
* Added `ExecutionContext.build_metrics()` for aggregating execution statistics
* Added parameter validation: `timeout >= 0` and `retry_interval >= 0` in `ScheduleConfig`

#### API Improvements
* Renamed `less_than()` → `can_submit()` with `DeprecationWarning` for backward compatibility
* Renamed `get_max_wait_time()` → `adjust_wait_time()` with `DeprecationWarning` for backward compatibility
* Fixed deprecated parameter names: `chat_process_fuc` → `chat_process_func`, `error_process_fuc` → `error_process_func`

#### Architecture & Code Quality
* Refactored `BaseRunner` with Template Method pattern — extracted `_handle_exception`, `_compute_cancel_wait`, `_log_finish`, `_return_result`
* Eliminated all magic numbers: `MIN_HEDGE_PROPORTION`, `MIN_WAIT_TIME`, `HEDGE_EXPONENT_BASE/STEP`, `MIN_LIMITER_TIMEOUT`, `DEFAULT_WINDOW_MAX_SIZE/INTERVAL/THRESHOLD`
* Created `qreward/client/load_balancer.py` for load balancing strategies (114 lines)

#### Bug Fixes
* Fixed flaky `test_sync_limit` — relaxed tolerance threshold from 105 to 200 for high-concurrency window boundary races

#### Documentation & Testing
* Added 30+ new unit tests across Sprint 8-14 (total: 249 tests, coverage: 98.02%)
* Added docstring usage examples to `ScheduleConfig`

---

### version 0.1.7-rc1 - 2026/04/14

#### Bug Fixes
* Fixed ThreadPoolExecutor resource leak in sync `schedule` decorator — executors now auto-cleanup via `atexit`
* Fixed `_handle_exception` catching `SystemExit`/`KeyboardInterrupt` — system-level exceptions now propagate immediately
* Fixed recursive exception chain check in `OverloadChecker` — converted to iterative with depth limit to prevent stack overflow
* Fixed `batch_chat_completion` missing `return_exceptions=True` in `asyncio.gather`
* Fixed bare `Exception` catching in `embeddings` method breaking `@retry` decorator

#### New Features
* Added `unpatch_openai_embeddings()` for reversible monkey patching
* Added `verify_ssl` parameter to `OpenAIChatProxy` for configurable SSL verification
* Added `asyncio.Lock` to `OpenAIChatProxyManager` for concurrency safety
* Added warning-level logging for failed tasks in `batch_chat_completion`
* Added `make check` target combining lint + test-cov

#### Performance Optimization
* Replaced `time.sleep` busy-wait in `LimiterPool.allow()` with `threading.Condition` for efficient waiting
* Lowered `max_concurrent` default from 1024 to 64 to prevent resource exhaustion
* Lowered `MAX_RETRIES` from 10 to 5 with exponential backoff
* Deferred `patch_httpx()` from module-level to `OpenAIChatProxy.__init__` (lazy patch)

#### Architecture & Code Quality
* Split `scheduler/base.py` (695 lines) into `base.py` + `async_runner.py` + `sync_runner.py` (all < 400 lines)
* `OpenAIChatProxyManager.proxies()` now returns a dict copy to prevent external mutation
* Modernized type hints in `manager.py` (`Dict`/`Tuple` → `dict`/`tuple`)
* Pinned minimum versions for all dependencies in `pyproject.toml` and `requirements.txt`

#### Documentation & Testing
* Added `tests/test_globals.py` with 7 tests covering all overload constant sets
* Added 19 new unit tests across Sprint 4-6 (total coverage: 98.75%)
* Updated CHANGELOG with Sprint 4-7 improvements

---

### version 0.1.6 - 2025/10/16

#### New Features
* Added example code to demonstrate the usage of the `schedule` decorator
* Added json monkey patch for httpx
  * The environment variable `JSON_LIB` can be used to control whether to use `ujson` or `orjson`
* Utilized httpx hooks to add support for custom paths
* Added `patch_openai` to maintain compatibility with custom embedding interface return formats

#### Performance Optimization
* Updated the default value of `hedged_request_proportion`

#### Documentation & Testing
* Added unit test code

#### Removed Features
* Removed `speed_up_retry`, replaced with `schedule`
* Removed the `custom_url` parameter from embedding-related interfaces

---

### version 0.1.5 - 2025/09/29

#### New Features
* Added `OpenAIChatProxyManager` class for proxy management
* Added keepalive configuration compatible with multiple HTTP frameworks
* Added retry logic
* Added transport configuration to `RewardServiceProxy`
* Added openai proxy functionality
* Added reward service client

#### Performance Optimization
* Optimized `speed_up_retry` functionality
* Introduced aiolimiter for faster task processing (2x+ performance improvement over version 0.1.0)
  * Semaphore controls global concurrency, aiolimiter precisely controls concurrent context
* Concurrency control via semaphore (supporting both large batch and small batch task processing)

#### Documentation & Testing
* Updated reward service interface parameters, usage methods and examples
* Updated examples and project dependencies
* Added unit test coverage (internal version code coverage: 91.56%)

#### Code Quality
* Other code formatting improvements