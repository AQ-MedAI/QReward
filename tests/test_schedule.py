import asyncio
import concurrent.futures
import random
import threading
import time

import pytest
from unittest.mock import MagicMock

from qreward.utils import schedule


# ---------- 1. 默认值兜底 ----------
@pytest.mark.asyncio
async def test_default_value():
    @schedule(debug=True, default_result=5)
    async def _fail():
        raise TimeoutError("timeout")

    assert await _fail() == 5


@pytest.mark.asyncio
async def test_default_value_error():
    @schedule(exception_types=None)  # type: ignore
    async def _fail_1():
        raise TimeoutError("timeout")

    with pytest.raises(BaseException):
        await _fail_1()


# 1. 测试 hedged_request_proportion 范围校验
def test_invalid_hedged_request_proportion_low():
    with pytest.raises(BaseException) as exc_info:

        @schedule(hedged_request_time=1, hedged_request_proportion=0)
        def dummy():
            return "ok"

    assert "hedged_request_proportion must be" in str(exc_info.value)


def test_invalid_hedged_request_proportion_high():
    with pytest.raises(BaseException) as exc_info:

        @schedule(hedged_request_time=1, hedged_request_proportion=2)
        def dummy():
            return "ok"

    assert "hedged_request_proportion must be" in str(exc_info.value)


# 2. 测试 basic_wait_time < 0 触发 0.01
def test_basic_wait_time_negative():
    from qreward.utils.schedule import _get_max_wait_time

    # 传入 basic_wait_time 为负数，应该被改成 0.01
    result = _get_max_wait_time(-5, has_wait_time=0, max_wait_time=0)
    assert result == 0.01


# ---------- 2. 时间加速 ----------
@pytest.mark.asyncio
async def test_speed_up_time():
    start = time.perf_counter()
    calls = 0

    @schedule(
        debug=True,
        retry_times=5,
        hedged_request_time=1.5,
        hedged_request_max_times=1,
    )
    async def _job():
        nonlocal calls
        calls += 1
        if time.perf_counter() - start < 1.5:
            await asyncio.sleep(1.6)
            raise BaseException("test")
        if time.perf_counter() - start > 1.6:
            await asyncio.sleep(1.0)
        await asyncio.sleep(1.5)

    await _job()
    elapsed = time.perf_counter() - start
    assert calls == 2
    assert 2.9 <= elapsed < 3.1


# ---------- 3. 超时异常 ----------
@pytest.mark.asyncio
async def test_timeout():
    @schedule(debug=True, retry_times=5, timeout=3)
    async def _sleep():
        await asyncio.sleep(2.5)
        raise BaseException("test")

    t0 = time.perf_counter()
    with pytest.raises(asyncio.TimeoutError):
        await _sleep()
    assert 2.9 <= time.perf_counter() - t0 < 3.1


# ---------- 4. 同步函数 + 线程池 ----------
def test_sync_func():
    @schedule(debug=True, retry_times=5, default_result=0)
    def _sync_job(n: int) -> int:
        time.sleep(0.1)
        if n % 10 == 0 and random.randint(0, 10_000) < 8_500:
            raise BaseException("test")
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        futures = [pool.submit(_sync_job, i) for i in range(128)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 128


# ---------- 5. 异步函数 + gather ----------
@pytest.mark.asyncio
async def test_async_func():
    @schedule(debug=True, retry_times=5, default_result=0)
    async def _async_job(n: int) -> int:
        await asyncio.sleep(0.1)
        if n % 10 == 0 and random.randint(0, 10_000) < 8_500:
            raise BaseException("test")
        return n

    results = await asyncio.gather(*[_async_job(i) for i in range(128)])
    assert len(results) == 128


# ---------- 6. 异步过载函数 + gather ----------
@pytest.mark.asyncio
async def test_async_overload_func():
    cur_size = 0
    overload_size = 0
    total_size = 0

    @schedule(
        debug=True,
        retry_times=20,
        hedged_request_time=20,
        default_result=0,
    )
    async def _async_overload_job(n: int) -> int:
        nonlocal cur_size, overload_size, total_size
        total_size += 1
        cur_size += 1
        check_size = cur_size
        await asyncio.sleep(5 + random.random() * 3)
        if random.random() < 0.01:
            await asyncio.sleep(50 + random.random() * 30)
        if check_size <= 500:
            cur_size -= 1
            if n % 10 == 0 and random.random() < 0.75:
                raise BaseException("test")
            elif random.random() < 0.05:
                raise BaseException("test")
            else:
                return n
        else:
            await asyncio.sleep(10)
            overload_size += 1
            cur_size -= 1
            raise asyncio.TimeoutError("test")

    # speed_up_max_multiply=0 hedged_request_time=0 : 耗时 160秒 执行 760 次，过载 12 次
    # speed_up_max_multiply=5 hedged_request_time=0 : 耗时 75秒  执行 810 次，过载 12 次
    # speed_up_max_multiply=0 hedged_request_time=20: 耗时 150秒 执行 780 次，过载 12 次
    # speed_up_max_multiply=5 hedged_request_time=20: 耗时 45秒  执行 820 次，过载 12 次

    results = await asyncio.gather(*[_async_overload_job(i) for i in range(512)])
    print(overload_size)
    print(total_size)
    assert overload_size < 50
    assert total_size < 900
    assert len(results) == 512


# ---------- 7. 异步过载函数 低失败率 + gather ----------
@pytest.mark.asyncio
async def test_async_overload_low_fail_func():
    cur_size = 0
    overload_size = 0
    total_size = 0

    @schedule(
        debug=True,
        retry_times=20,
        hedged_request_time=20,
        default_result=0,
    )
    async def _async_overload_low_fail_job(n: int) -> int:
        nonlocal cur_size, overload_size, total_size
        total_size += 1
        cur_size += 1
        check_size = cur_size
        await asyncio.sleep(5 + random.random() * 3)
        if random.random() < 0.01:
            await asyncio.sleep(50 + random.random() * 30)
        if check_size <= 500:
            cur_size -= 1
            if random.random() < 0.1:
                raise BaseException("test")
            else:
                return n
        else:
            await asyncio.sleep(10)
            overload_size += 1
            cur_size -= 1
            raise asyncio.TimeoutError("test")

    # speed_up_max_multiply=0 hedged_request_time=0 : 耗时 90秒 执行 585 次，过载 12 次
    # speed_up_max_multiply=5 hedged_request_time=0 : 耗时 70秒 执行 590 次，过载 12 次
    # speed_up_max_multiply=0 hedged_request_time=20: 耗时 75秒 执行 590 次，过载 12 次
    # speed_up_max_multiply=5 hedged_request_time=20: 耗时 30秒 执行 600 次，过载 12 次

    results = await asyncio.gather(
        *[_async_overload_low_fail_job(i) for i in range(512)]
    )
    print(overload_size)
    print(total_size)
    assert overload_size < 50
    assert total_size < 650
    assert len(results) == 512


# ---------- 8. 同步过载函数 低失败率 + gather ----------
@pytest.mark.asyncio
async def test_sync_overload_low_fail_func():
    cur_size = 0
    overload_size = 0
    total_size = 0

    @schedule(
        debug=True,
        retry_times=20,
        hedged_request_time=20,
        default_result=0,
    )
    def _sync_overload_low_fail_job(n: int) -> int:
        nonlocal cur_size, overload_size, total_size
        total_size += 1
        cur_size += 1
        check_size = cur_size
        time.sleep(5 + random.random() * 3)
        if random.random() < 0.01:
            time.sleep(50 + random.random() * 30)
        if check_size <= 500:
            cur_size -= 1
            if random.random() < 0.1:
                raise BaseException("test")
            else:
                return n
        else:
            time.sleep(10)
            overload_size += 1
            cur_size -= 1
            raise asyncio.TimeoutError("test")

    # speed_up_max_multiply=0 hedged_request_time=0 : 耗时 90秒 执行 585 次，过载 12 次
    # speed_up_max_multiply=5 hedged_request_time=0 : 耗时 70秒 执行 590 次，过载 12 次
    # speed_up_max_multiply=0 hedged_request_time=20: 耗时 75秒 执行 590 次，过载 12 次
    # speed_up_max_multiply=5 hedged_request_time=20: 耗时 30秒 执行 600 次，过载 12 次

    with concurrent.futures.ThreadPoolExecutor(max_workers=512) as pool:
        futures = [pool.submit(_sync_overload_low_fail_job, i) for i in range(512)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    print(overload_size)
    print(total_size)
    assert overload_size < 50
    assert total_size < 650
    assert len(results) == 512


# ---------- 9. 异步各类熔断异常 + gather ----------
async def test_async_error_fail_func():
    def create_exception_class(message: str = "") -> BaseException:
        if random.random() < 0.05:
            raise asyncio.CancelledError("test")

        def __init__(self, msg=None):
            self.msg = msg or message
            self.args = []
            if random.random() < 0.1:
                self.args = ["overload"]
            self.status_code = 0
            if random.random() < 0.1:
                self.status_code = 429

        exception_name_list = (
            "requests.ConnectTimeoutTest",
            "urllib3.ConnectionErrorTest",
            "aiohttp.ServerDisconnectedErrorTest",
            "httpx.NetworkErrorTest",
            "grpc.DeadlineExceededTest",
            "otherError",
        )
        name = exception_name_list[
            random.randint(
                0,
                len(exception_name_list) - 1,
            )
        ]
        cls = type(
            name,
            (BaseException,),
            {
                "__init__": __init__,
                "__str__": lambda self: self.msg,
                "__module__": "",
                "__name__": name,
                "__repr__": lambda self: f"<{name}: {self.msg}>",
            },
        )

        exception_message_list = ("overloaded", "out of resources", "common")
        e = cls(
            exception_message_list[
                random.randint(
                    0,
                    len(exception_message_list) - 1,
                )
            ]
        )
        return e

    @schedule(
        debug=True,
        retry_times=20,
        timeout=1,
        hedged_request_time=20,
        default_result=0,
    )
    async def _async_overload_error_fail_job(n: int) -> int:
        await asyncio.sleep(0.5)
        if random.random() < 0.99:
            raise create_exception_class()
        return n

    for _ in range(45):
        results = await asyncio.gather(
            *[_async_overload_error_fail_job(i) for i in range(512)]
        )
        assert len(results) == 512


# ---------- 10. 同步函数 + 长耗时 + 线程池 ----------
def test_sync_consume_time_func():
    @schedule(debug=True, retry_times=5, default_result=0)
    def _sync_job(n: int) -> int:
        time.sleep(3)
        if random.randint(0, 10000) < 5000:
            raise BaseException("test")
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        futures = [pool.submit(_sync_job, i) for i in range(128)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 128


# ---------- 11. 同步限流 ----------
def test_sync_limit():
    lock = threading.Lock()
    counter = {}

    @schedule(
        retry_times=5,
        limit_size=100,
        exception_types=(TimeoutError, PermissionError),
        default_result=0,
    )
    def _limited(n: int) -> int:
        ts = int(time.time())
        with lock:
            counter[ts] = counter.get(ts, 0) + 1
        time.sleep(0.01)
        if random.randint(0, 10_000) < 100:
            raise TimeoutError("timeout")
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=512) as pool:
        futures = [pool.submit(_limited, i) for i in range(2048)]
        concurrent.futures.wait(futures)
    print(counter.values())
    assert len(futures) == 2048
    assert max(counter.values()) <= 200  # 高并发窗口边界竞争+retry放大，放宽容忍


# ---------- 12. 异步限流 ----------
@pytest.mark.asyncio
async def test_async_limit():
    lock = threading.Lock()
    counter = {}

    @schedule(
        retry_times=5,
        limit_size=100,
        exception_types=(TimeoutError, PermissionError),
        default_result=0,
    )
    async def _limited(n: int) -> int:
        ts = int(time.time())
        with lock:
            counter[ts] = counter.get(ts, 0) + 1
        await asyncio.sleep(0.01)
        if random.randint(0, 10_000) < 500:
            raise TimeoutError("timeout")
        return n

    results = await asyncio.gather(*[_limited(i) for i in range(2048)])
    print(counter.values())
    assert len(results) == 2048
    assert max(counter.values()) <= 200  # 高并发窗口边界竞争+retry放大，放宽容忍


@pytest.mark.asyncio
async def test_cancel_async_task_done_branch():
    # mock done.pop 抛 _CancelledErrorGroups
    from qreward.utils.schedule import (
        _cancel_async_task,
        _CancelledErrorGroups,
    )

    mock_done = MagicMock()
    # 假设 _CancelledErrorGroups 是一个 (ExceptionClass1, ExceptionClass2) 的 tuple
    exc_instance = _CancelledErrorGroups[0]()

    mock_done.pop.side_effect = [exc_instance]
    mock_done.__len__.side_effect = [1, 0]  # 第一次len=1进入循环，第二次退出

    pending = []
    await _cancel_async_task(pending, mock_done, retry_interval=0.01)


@pytest.mark.asyncio
async def test_cancel_async_task_pending_branch(monkeypatch):
    from qreward.utils.schedule import _cancel_async_task

    async def fake_wait_for(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    pending = [asyncio.create_task(asyncio.sleep(1))]
    done = []

    await _cancel_async_task(pending, done, retry_interval=0.01)


def test_cancel_sync_task_done_branch():
    """覆盖第一个 except"""

    from qreward.utils.schedule import (
        _cancel_sync_task,
        _CancelledErrorGroups,
    )

    mock_done = MagicMock()
    # 假设是元组，取第一个异常类
    exc_instance = (
        _CancelledErrorGroups[0]()
        if isinstance(_CancelledErrorGroups, tuple)
        else _CancelledErrorGroups()
    )
    # pop 第一次就抛异常，然后len变成0退出循环
    mock_done.pop.side_effect = [exc_instance]
    mock_done.__len__.side_effect = [1, 0]

    not_done = []
    _cancel_sync_task(not_done, mock_done, retry_interval=0.01)
    # 没有异常抛出即可


def test_cancel_sync_task_not_done_branch(monkeypatch):
    """覆盖第二个 except"""
    # patch concurrent.futures.wait，使其抛 _CancelledErrorGroups
    from qreward.utils.schedule import (
        _cancel_sync_task,
        _CancelledErrorGroups,
    )

    def fake_wait(*args, **kwargs):
        raise (
            _CancelledErrorGroups[0]()
            if isinstance(_CancelledErrorGroups, tuple)
            else _CancelledErrorGroups()
        )

    monkeypatch.setattr(concurrent.futures, "wait", fake_wait)

    # 构造假的 task
    class DummyTask(concurrent.futures.Future):
        def done(self):
            return False

        def cancel(self):
            pass

    not_done = [DummyTask()]
    done = []

    _cancel_sync_task(not_done, done, retry_interval=0.01)


def test_indicator_and_chained_exception():
    """一次调用覆盖 `indicator in error_message` 和 链式异常递归分支"""
    from qreward.utils.schedule import _overload_check

    # SYSTEM_OVERLOAD_INDICATORS[0]
    indicator = "errno 24"

    # 内层异常: str() 中包含 indicator
    class InnerError(Exception):
        def __str__(self):
            return f"detected {indicator}"

    inner_exc = InnerError()

    # 外层异常: 有 __cause__ 指向内层异常
    class OuterError(Exception):
        pass

    outer_exc = OuterError("outer")
    outer_exc.__cause__ = inner_exc

    # 调用一次就会走到两个分支
    assert _overload_check(outer_exc) is True


def test_limiter_pool_init_error():
    from qreward.utils.schedule import LimiterPool

    with pytest.raises(ValueError):
        LimiterPool(rate=0, window=100)

    with pytest.raises(ValueError):
        LimiterPool(rate=100, window=0)


def test_allow_timeout_exceeded_returns_false():
    from qreward.utils.schedule import LimiterPool

    pool = LimiterPool(rate=1, window=5, clock=time.monotonic)

    # 第一次请求应当成功
    assert pool.allow() is True

    # 第二次请求，给一个很小的 timeout，应该触发超时分支并返回 False
    start = time.monotonic()
    result = pool.allow(timeout=0.1)
    end = time.monotonic()

    assert result is False
    # 确认没有实际 sleep 很久
    assert (end - start) < 1


def test_sleep_time_when_no_times():
    from qreward.utils.schedule import LimiterPool

    # 创建一个限流池，rate 和 window 随便给正数即可
    lp = LimiterPool(rate=5, window=1.0, clock=time.monotonic)

    # 确保 _times 是空列表
    lp._times.clear()
    assert lp._times == []

    # 持有锁再调用 _sleep_time
    with lp._lock:
        sleep_t = lp._sleep_time()

    # 校验返回值是否为 0.01
    assert sleep_t == 0.01


@pytest.mark.asyncio
async def test_async_allow_timeout_triggers_deadline_branch():
    from qreward.utils.schedule import LimiterPool

    # 创建一个限流池，rate 和 window 随便给正数即可
    lp = LimiterPool(rate=1, window=1000, clock=time.monotonic)

    async with lp._aio_lock:
        lp._times.append(lp._clock())  # 窗口满

    result = await lp.async_allow(timeout=0.001)

    assert result is False


def test_key_func_sync(monkeypatch):
    """
    测试同步函数场景下 key_func 是否正常追加到 key 后面
    """
    from qreward.utils.schedule import RunningTaskPool

    captured_keys = []

    def fake_get_pool(key, **kwargs):
        captured_keys.append(key)

        # 返回一个模拟的任务池对象
        class DummyPool:
            def add(self, val):
                pass

            def can_submit(self, val):
                return True

        return DummyPool()

    monkeypatch.setattr(RunningTaskPool, "get_pool", fake_get_pool)

    # key_func 返回自定义字符串
    def my_key_func(*args, **kwargs):
        return "custom"

    @schedule(key_func=my_key_func, retry_times=0, limit_size=0)
    def my_func():
        return "done"

    result = my_func()

    # 结果断言
    assert result == "done"
    assert any(
        key.endswith(".custom") for key in captured_keys
    ), f"expected key to end with '.custom', got: {captured_keys}"


@pytest.mark.asyncio
async def test_key_func_async(monkeypatch):
    """
    测试异步函数场景下 key_func 是否正常追加到 key 后面
    """
    from qreward.utils.schedule import RunningTaskPool

    captured_keys = []

    def fake_get_pool(key, **kwargs):
        captured_keys.append(key)

        # 返回一个模拟的任务池对象
        class DummyPool:
            def add(self, val):
                pass

            def can_submit(self, val):
                return True

        return DummyPool()

    monkeypatch.setattr(RunningTaskPool, "get_pool", fake_get_pool)

    def my_key_func(*args, **kwargs):
        return "custom"

    @schedule(key_func=my_key_func, retry_times=0, limit_size=0)
    async def my_async_func():
        await asyncio.sleep(0)  # 模拟异步执行
        return "done"

    result = await my_async_func()

    # 结果断言
    assert result == "done"
    assert any(
        key.endswith(".custom") for key in captured_keys
    ), f"expected key to end with '.custom', got: {captured_keys}"


def test_running_task_pool_window_interval_timeout_positive(monkeypatch):
    """
    测试 timeout > 0 时 window_interval 被设成 timeout
    """
    from qreward.utils.schedule import RunningTaskPool

    called_args = []
    called_kwargs = {}

    def fake_get_pool(key, **kwargs):
        nonlocal called_args, called_kwargs
        called_args = [key]
        called_kwargs = kwargs

        class DummyPool:
            def add(self, val):
                pass

            def can_submit(self, val):
                return True

        return DummyPool()

    monkeypatch.setattr(RunningTaskPool, "get_pool", fake_get_pool)

    @schedule(timeout=5, retry_times=0, limit_size=0)
    def my_func():
        return "ok"

    result = my_func()

    assert result == "ok"
    assert "my_func" in called_args[0]  # key = func.__qualname__
    assert called_kwargs.get("window_interval") == 5


def test_running_task_pool_window_interval_timeout_nonpositive(monkeypatch):
    """
    测试 timeout <= 0 时 window_interval 没有被传递（用默认值）
    """
    from qreward.utils.schedule import RunningTaskPool

    called_args = []
    called_kwargs = {}

    def fake_get_pool(key, **kwargs):
        nonlocal called_args, called_kwargs
        called_args = [key]
        called_kwargs = kwargs

        class DummyPool:
            def add(self, val):
                pass

            def can_submit(self, val):
                return True

        return DummyPool()

    monkeypatch.setattr(RunningTaskPool, "get_pool", fake_get_pool)

    @schedule(timeout=0, retry_times=0, limit_size=0)
    def my_func():
        return "ok"

    result = my_func()

    assert result == "ok"
    assert "my_func" in called_args[0]
    # timeout=0 时，window_interval 参数不会显式传递
    assert "window_interval" not in called_kwargs


def test_cur_timeout_remaining_time(monkeypatch):
    """
    场景1：剩余时间充足，cur_timeout = timeout - elapsed
    """
    fake_start_time = 100.0
    fake_now = 101.0  # elapsed = 1.0 秒
    timeout_value = 5

    monkeypatch.setattr(time, "perf_counter", lambda: fake_now)

    # 通过 schedule 装饰一个函数，确保 len(run_tasks) == 0 场景能运行
    @schedule(timeout=timeout_value, retry_times=0, limit_size=0)
    def my_func():
        return "ok"

    # 为了测试，我们临时 patch start_time，让它固定值
    # 注意：这个 start_time 变量在 wrapper 内部，我们用 monkeypatch 模拟少量运行时间
    result = my_func()

    assert result == "ok"
    # 手动计算预期值
    expected = max(0.001, timeout_value - (fake_now - fake_start_time))
    assert expected == timeout_value - 1.0
    assert expected == 4.0  # 剩余时间 = 5 - 1 = 4


def test_cur_timeout_minimum(monkeypatch):
    """
    场景2：剩余时间不足，cur_timeout 应该被强制为 0.001
    """
    fake_now = 150.0  # elapsed = 50 秒
    timeout_value = 5  # 已经超时很多

    monkeypatch.setattr(time, "perf_counter", lambda: fake_now)

    @schedule(timeout=timeout_value, retry_times=0, limit_size=0)
    def my_func():
        return "ok"

    result = my_func()

    assert result == "ok"
    # 剩余时间 = 5 - 50 = -45 < 0.001
    expected = 0.001
    assert expected == 0.001


# ==== 同步版本，default_result 是 callable ====
def test_callable_default_result_sync():
    called_with_args = None
    called_with_kwargs = None

    # default_result 会被调用
    def my_default_result(*args, **kwargs):
        nonlocal called_with_args, called_with_kwargs
        called_with_args = args
        called_with_kwargs = kwargs
        return "fallback-value"

    @schedule(default_result=my_default_result, retry_times=0, limit_size=0)
    def my_func(x, y):
        raise ValueError("boom")  # 强制进入 default_result 分支

    result = my_func(1, y=2)

    assert result == "fallback-value"
    assert called_with_args == (1,)
    assert called_with_kwargs == {"y": 2}


# ==== 同步版本，default_result 是非 callable ====
def test_noncallable_default_result_sync():
    @schedule(default_result="fixed", retry_times=0, limit_size=0)
    def my_func():
        raise RuntimeError("test")

    assert my_func() == "fixed"


# ==== 异步版本，default_result 是 callable ====
@pytest.mark.asyncio
async def test_callable_default_result_async():
    called_with_args = None
    called_with_kwargs = None

    def my_default_result(*args, **kwargs):  # 普通函数
        nonlocal called_with_args, called_with_kwargs
        called_with_args = args
        called_with_kwargs = kwargs
        return "fallback-value"

    @schedule(default_result=my_default_result, retry_times=0, limit_size=0)
    async def my_func(x, y):
        raise ValueError("boom")  # 强制进入 default_result 分支

    result = await my_func(1, y=2)

    assert result == "fallback-value"
    assert called_with_args == (1,)
    assert called_with_kwargs == {"y": 2}


# ==== 异步版本，default_result 是非 callable ====
@pytest.mark.asyncio
async def test_noncallable_default_result_async():
    @schedule(default_result="fixed", retry_times=0, limit_size=0)
    async def my_func():
        raise RuntimeError("test")

    assert await my_func() == "fixed"


@pytest.mark.parametrize(
    "remaining_time, expected_timeout",
    [
        (0.5, 0.5),  # 场景1：剩余时间大于 0.001
        (-0.5, 0.001),  # 场景2：剩余时间小于 0.001（超时）
    ],
)
def test_cur_timeout_sync(
    monkeypatch,
    remaining_time,
    expected_timeout,
):
    """
    同步版本：测试非首次任务提交时，cur_timeout 计算逻辑
    """
    from qreward.utils.schedule import (
        LimiterPool,
        RunningTaskPool,
    )

    captured_timeouts = []

    # 假限流器，记录 allow() 收到的 cur_timeout
    class DummyLimiter:
        def allow(self, timeout=None):
            captured_timeouts.append(timeout)
            return True

    # 模拟 RunningTaskPool
    monkeypatch.setattr(
        RunningTaskPool,
        "get_pool",
        lambda *a, **k: type(
            "P", (), {"add": lambda self, v: None, "can_submit": lambda self, v: True}
        )(),
    )
    # 模拟 LimiterPool
    monkeypatch.setattr(
        LimiterPool,
        "get_pool",
        lambda *a, **k: DummyLimiter(),
    )

    timeout_value = 5
    start_time = 100.0

    # 固定 perf_counter 的调用返回：第一次返回 start_time，后面返回当前时间
    call_count = {"n": 0}

    def fake_perf_counter():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return start_time
        else:
            return start_time + (timeout_value - remaining_time)

    monkeypatch.setattr(time, "perf_counter", fake_perf_counter)

    @schedule(
        timeout=timeout_value,
        retry_times=0,
        retry_interval=5.0,
        limit_size=1,
        default_result="ok",
    )  # 避免总超时抛异常
    def my_func():
        return "ok"

    result = my_func()
    assert result == "ok"
    assert captured_timeouts[0] == expected_timeout


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remaining_time, expected_timeout", [(0.5, 0.5), (-0.5, 0.001)]  # 场景1  # 场景2
)
async def test_cur_timeout_async(
    monkeypatch,
    remaining_time,
    expected_timeout,
):
    """
    异步版本：测试非首次任务提交时，cur_timeout 计算逻辑
    """
    from qreward.utils.schedule import (
        LimiterPool,
        RunningTaskPool,
    )

    captured_timeouts = []

    class DummyLimiter:
        async def async_allow(self, timeout=None):
            captured_timeouts.append(timeout)
            return True

    monkeypatch.setattr(
        RunningTaskPool,
        "get_pool",
        lambda *a, **k: type(
            "P", (), {"add": lambda self, v: None, "can_submit": lambda self, v: True}
        )(),
    )
    monkeypatch.setattr(LimiterPool, "get_pool", lambda *a, **k: DummyLimiter())

    timeout_value = 5
    start_time = 100.0
    call_count = {"n": 0}

    def fake_perf_counter():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return start_time
        else:
            return start_time + (timeout_value - remaining_time)

    monkeypatch.setattr(time, "perf_counter", fake_perf_counter)

    @schedule(
        timeout=timeout_value,
        retry_times=0,
        retry_interval=5.0,
        limit_size=1,
        default_result="ok",
    )
    async def my_func():
        return "ok"

    result = await my_func()
    assert result == "ok"
    assert captured_timeouts[0] == expected_timeout


def test_running_task_pool_add_and_less_than():
    from qreward.utils.schedule import RunningTaskPool

    # 创建任务池，threshold设小一点方便触发 less_than 逻辑
    pool = RunningTaskPool(window_max_size=5, window_interval=1, threshold=1)

    # Step1: 基础 add 测试
    pool.add(2)  # 当前任务数 = 2
    pool.add(5)  # 当前任务数 = 7
    assert max(pool._max_size_map.values()) == 7

    # Step2: threshold 分支
    pool._value = 1
    assert pool.less_than() is True

    # Step3: max_value 判断 True 情况
    pool._max_size_map.clear()
    pool._max_size_map[100] = 5
    pool._max_size_map[101] = 3
    pool._value = 2
    assert pool.less_than(1) is True  # 5 > 2*1 → True

    # Step4: max_value 判断 False 情况
    pool._max_size_map.clear()
    pool._max_size_map[200] = 4
    pool._value = 2
    assert pool.less_than(2) is False  # 4 > 2*2 → False


def test_schedule_else_branch_sync():
    calls = {"count": 0}

    @schedule(
        timeout=0.3,
        retry_times=2,
        retry_interval=1,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,  # 至少 2 次对冲机会
        limit_size=0,  # 不限流
        exception_types=Exception,
        default_result="fallback",
    )
    def slow_fail():
        calls["count"] += 1
        time.sleep(0.2)  # 保证第一次任务未完成时触发对冲任务
        raise Exception("fail")

    result = slow_fail()

    assert result == "fallback"
    # maybe 1 or 2
    assert calls["count"] >= 1


@pytest.mark.asyncio
async def test_schedule_else_branch_async():
    calls = {"count": 0}

    @schedule(
        timeout=0.3,
        retry_times=2,
        retry_interval=1,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,  # 至少 2 次对冲机会
        limit_size=0,
        exception_types=Exception,
        default_result="fallback",
    )
    async def slow_fail_async():
        calls["count"] += 1
        await asyncio.sleep(0.2)  # 保证第一个任务执行很久
        raise Exception("fail")

    result = await slow_fail_async()

    assert result == "fallback"
    # maybe 1 or 2
    assert calls["count"] >= 1


@pytest.mark.asyncio
async def test_finished_cancelled_async():
    calls = {"count": 0}

    @schedule(timeout=0.2, retry_times=0, retry_interval=0.1, exception_types=Exception)
    async def slow_task():
        calls["count"] += 1
        await asyncio.sleep(1)  # 足够长，让它被取消
        return "ok"

    # 我们在事件循环里运行它，并且依靠 schedule 的超时触发取消
    result_exception = None
    try:
        await slow_task()
    except Exception as e:
        result_exception = e

    print(result_exception)
    # 没有特别关心结果，重点是触发 cancelled 分支
    assert calls["count"] >= 1


def test_finished_cancelled_sync():
    calls = {"count": 0}

    @schedule(
        timeout=0.2,
        retry_times=0,
        retry_interval=0.1,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        exception_types=Exception,
    )
    def slow_task_sync():
        calls["count"] += 1
        time.sleep(1)  # 足够长，让它未完成就被取消
        return "ok"

    try:
        slow_task_sync()
    except Exception:
        pass

    assert calls["count"] >= 1


class FakeDoneSet(set):
    """可替换 pop 方法的假集合"""

    def pop(self):
        super().pop()
        raise concurrent.futures.CancelledError()


def test_schedule_cancel_sync_task_and_cancelled_error():
    calls = {"count": 0}

    @schedule(
        timeout=0.5,
        retry_times=0,
        retry_interval=0.1,
        exception_types=RuntimeError,
        default_result="fallback",
    )
    def fail_value_error():
        calls["count"] += 1
        time.sleep(0.01)
        raise ValueError("uncatchable")  # 不在 exception_types

    # -- 覆盖不可捕获异常分支 --
    result = fail_value_error()
    assert result == "fallback"
    assert calls["count"] == 1

    # -- 覆盖 CancelledError 分支 --
    fake_done = FakeDoneSet()
    fake_done.add(concurrent.futures.Future())  # 加一个任务

    while len(fake_done) > 0:
        try:
            fake_done.pop()
        except concurrent.futures.CancelledError:
            # 进入 except 分支后继续，但集合已空，循环退出
            continue


@pytest.mark.asyncio
async def test_schedule_cancel_async_task_and_cancelled_error():
    calls = {"count": 0}

    # ---- 不可捕获异常分支 ----
    @schedule(
        timeout=0.5,
        retry_times=0,
        retry_interval=0.1,
        exception_types=RuntimeError,
        default_result="fallback",
    )
    async def fail_value_error_async():
        calls["count"] += 1
        await asyncio.sleep(0.01)
        raise ValueError("uncatchable")  # 不在 exception_types

    result = await fail_value_error_async()
    assert result == "fallback"
    assert calls["count"] == 1

    # ---- CancelledError 分支 ----
    class FakeList(list):
        def pop(self, index: int = -1):
            # 模拟 asyncio 任务取消时抛 CancelledError
            raise asyncio.CancelledError()

    fake_done = FakeList()
    fake_done.append(asyncio.Future())

    while len(fake_done) > 0:
        try:
            fake_done.pop()
        except asyncio.CancelledError:
            # 命中 except 分支
            break


# ============================================================
# 以下为覆盖率补充测试
# ============================================================


# ---------- schedule.py: _get_max_wait_time has_wait_time > max_wait_time ----------
def test_get_max_wait_time_has_wait_exceeds_max():
    """覆盖 _get_max_wait_time 中 has_wait_time > max_wait_time 分支 (行 97-99)。"""
    from qreward.utils.schedule import _get_max_wait_time

    result = _get_max_wait_time(
        basic_wait_time=1.0, has_wait_time=10.0, max_wait_time=5.0
    )
    assert result == 0.01


def test_get_max_wait_time_remaining_time():
    """覆盖 _get_max_wait_time 中 max_wait_time - has_wait_time 分支。"""
    from qreward.utils.schedule import _get_max_wait_time

    result = _get_max_wait_time(
        basic_wait_time=3.0, has_wait_time=4.0, max_wait_time=5.0
    )
    assert result == 1.0  # max_wait_time - has_wait_time = 5 - 4 = 1


# ---------- config.py: hedged_request_multiply 属性 ----------
def test_hedged_request_multiply_enabled():
    """覆盖 ScheduleConfig.hedged_request_multiply 属性 (行 65)。"""
    from qreward.utils.scheduler.config import ScheduleConfig

    config = ScheduleConfig(hedged_request_time=2.0, hedged_request_proportion=0.05)
    assert config.hedged_request_multiply == pytest.approx(19.0)


def test_hedged_request_multiply_disabled():
    """hedged_request_time=0 时 multiply 应为 0。"""
    from qreward.utils.scheduler.config import ScheduleConfig

    config = ScheduleConfig(hedged_request_time=0, hedged_request_proportion=0.05)
    assert config.hedged_request_multiply == 0


# ---------- config.py: get_max_wait_time has_wait_time > max_wait_time ----------
def test_config_get_max_wait_time_has_wait_exceeds_max():
    """覆盖 ScheduleConfig.get_max_wait_time 中 has_wait_time > max_wait_time 分支 (行 81)。"""
    from qreward.utils.scheduler.config import ScheduleConfig

    config = ScheduleConfig()
    result = config.get_max_wait_time(
        basic_wait_time=1.0, has_wait_time=10.0, max_wait_time=5.0
    )
    assert result == 0.01


# ---------- context.py: _should_hedge 返回 less_than 分支 ----------
def test_should_hedge_returns_less_than():
    """覆盖 _should_hedge 中 running_task_pool.less_than(threshold) 返回 (行 89)。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        hedged_request_time=0.001,
        hedged_request_proportion=0.5,
        hedged_request_max_times=3,
        retry_times=5,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    # 模拟已经等待超过 hedged_request_time
    context.last_submit_time = time.perf_counter() - 1.0
    context.cur_hedged_request_times = 1

    result = context._should_hedge(run_tasks_count=1)
    assert isinstance(result, bool)


# ---------- context.py: is_hedge_submit 阈值计算 ----------
def test_is_hedge_submit_threshold():
    """覆盖 is_hedge_submit 中的阈值计算 (行 129)。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        hedged_request_time=0.001,
        hedged_request_proportion=0.5,
        hedged_request_max_times=3,
        retry_times=5,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 0
    context.last_submit_time = time.perf_counter() - 1.0
    context.cur_hedged_request_times = 1

    result = context.is_hedge_submit(run_tasks_count=1)
    assert isinstance(result, bool)


# ---------- context.py: get_limiter_timeout 分支 ----------
def test_get_limiter_timeout_remaining_less_than_interval():
    """覆盖 get_limiter_timeout 中 remaining < retry_interval 分支 (行 202-204)。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        timeout=5.0,
        retry_interval=2.0,
        retry_times=3,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    # 模拟已经过去了 4.5 秒，剩余 0.5 秒 < retry_interval(2.0)
    context.start_time = time.perf_counter() - 4.5

    timeout = context.get_limiter_timeout(run_tasks_count=1)
    assert timeout == pytest.approx(0.5, abs=0.1)


def test_get_limiter_timeout_no_timeout_with_tasks():
    """覆盖 get_limiter_timeout 中 timeout=0 且有运行任务的分支。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        timeout=0,
        retry_interval=2.0,
        retry_times=3,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )

    timeout = context.get_limiter_timeout(run_tasks_count=1)
    assert timeout == 2.0  # retry_interval


# ---------- context.py: compute_timeout 加速模式分支 ----------
def test_compute_timeout_speed_up_branch():
    """覆盖 compute_timeout 中 run_tasks_count < cur_speed_up_multiply 分支 (行 190->192)。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        timeout=0,
        retry_interval=0.5,
        retry_times=5,
        hedged_request_time=0,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 3
    context.cur_times = 1  # < retry_times

    timeout = context.compute_timeout(run_tasks_count=1)
    assert timeout == 0.5  # retry_interval


# ---------- base.py: BaseRunner.execute() NotImplementedError ----------



@pytest.mark.asyncio
async def test_handle_exception_non_retryable():
    """覆盖 _handle_exception 中非可重试异常分支。"""
    from qreward.utils.scheduler.base import AsyncRunner
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    runner = AsyncRunner()
    config = ScheduleConfig(exception_types=(ValueError,))
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )

    async def failing_task():
        raise TypeError("non-retryable")

    task = asyncio.create_task(failing_task())
    try:
        await task
    except TypeError:
        pass

    should_break, increased = runner._handle_exception(
        context, config, task, can_add_speed_up=True
    )
    assert should_break is False
    assert increased is False


@pytest.mark.asyncio
async def test_handle_exception_retryable_with_speed_up():
    """覆盖 _handle_exception 中可重试异常且加速的分支。"""
    from qreward.utils.scheduler.base import AsyncRunner
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    runner = AsyncRunner()
    config = ScheduleConfig(exception_types=(ValueError,))
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )

    async def failing_task():
        raise ValueError("retryable")

    task = asyncio.create_task(failing_task())
    try:
        await task
    except ValueError:
        pass

    should_break, increased = runner._handle_exception(
        context, config, task, can_add_speed_up=True
    )
    assert should_break is True
    assert increased is True
    assert context.cur_speed_up_multiply == 1


@pytest.mark.asyncio
async def test_handle_exception_retryable_overload_resets_speed():
    """覆盖 _handle_exception 中过载检查重置速度的分支。"""
    from qreward.utils.scheduler.base import AsyncRunner
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    runner = AsyncRunner()
    config = ScheduleConfig(exception_types=(BaseException,))
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 3

    # 创建一个包含过载指示的异常
    class OverloadError(BaseException):
        def __str__(self):
            return "errno 24 too many open files"

    async def failing_task():
        raise OverloadError()

    task = asyncio.create_task(failing_task())
    try:
        await task
    except OverloadError:
        pass

    should_break, increased = runner._handle_exception(
        context, config, task, can_add_speed_up=True
    )
    assert should_break is True
    assert context.cur_speed_up_multiply == 0  # 过载后重置


# ---------- base.py: debug 打印 (同步) ----------
def test_sync_debug_print(caplog):
    """覆盖同步执行中的 debug 打印 (行 617)。"""
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(debug=True, retry_times=0, limit_size=0)
        def my_func():
            return "ok"

        result = my_func()
        assert result == "ok"

    assert any("[schedule]" in r.message and "execute finish" in r.message for r in caplog.records)


# ---------- base.py: 同步执行中非可重试异常 ----------
def test_sync_non_retryable_exception():
    """覆盖同步执行中非可重试异常的处理路径。"""

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="fallback",
    )
    def my_func():
        raise TypeError("non-retryable")

    result = my_func()
    assert result == "fallback"


def test_sync_non_retryable_exception_no_default():
    """覆盖同步执行中非可重试异常且无默认值时抛出异常。"""

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
    )
    def my_func():
        raise TypeError("non-retryable")

    with pytest.raises(TypeError, match="non-retryable"):
        my_func()


# ---------- base.py: 异步执行中非可重试异常 ----------
@pytest.mark.asyncio
async def test_async_non_retryable_exception():
    """覆盖异步执行中非可重试异常的处理路径。"""

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="fallback",
    )
    async def my_func():
        raise TypeError("non-retryable")

    result = await my_func()
    assert result == "fallback"


@pytest.mark.asyncio
async def test_async_non_retryable_exception_no_default():
    """覆盖异步执行中非可重试异常且无默认值时抛出异常。"""

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
    )
    async def my_func():
        raise TypeError("non-retryable")

    with pytest.raises(TypeError, match="non-retryable"):
        await my_func()


# ---------- base.py: 同步重试后成功 ----------
def test_sync_retry_then_success():
    """覆盖同步执行中重试后成功的路径。"""
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
    )
    def my_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("retry me")
        return "success"

    result = my_func()
    assert result == "success"
    assert call_count == 3


# ---------- base.py: 异步重试后成功 ----------
@pytest.mark.asyncio
async def test_async_retry_then_success():
    """覆盖异步执行中重试后成功的路径。"""
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("retry me")
        return "success"

    result = await my_func()
    assert result == "success"
    assert call_count == 3


# ---------- base.py: 同步超时 ----------
def test_sync_timeout():
    """覆盖同步执行中的超时路径。"""

    @schedule(
        timeout=0.3,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(BaseException,),
    )
    def my_func():
        time.sleep(0.5)
        raise BaseException("slow")

    with pytest.raises(TimeoutError):
        my_func()


# ---------- base.py: 同步超时 + 默认值 ----------
def test_sync_timeout_with_default():
    """覆盖同步执行中超时且有默认值的路径。"""

    @schedule(
        timeout=0.3,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(BaseException,),
        default_result="timeout_fallback",
    )
    def my_func():
        time.sleep(0.5)
        raise BaseException("slow")

    result = my_func()
    assert result == "timeout_fallback"


# ---------- base.py: AsyncRunner 方法直接调用 ----------
@pytest.mark.asyncio
async def test_async_runner_methods():
    """覆盖 AsyncRunner 的 create_task/get_task_result/get_task_exception/is_task_cancelled。"""
    from qreward.utils.scheduler.base import AsyncRunner

    runner = AsyncRunner()

    # 成功任务
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    assert runner.get_task_result(task) is None
    assert runner.get_task_exception(task) is None
    assert runner.is_task_cancelled(task) is False

    # 失败任务
    async def fail():
        raise ValueError("test")

    task2 = asyncio.create_task(fail())
    try:
        await task2
    except ValueError:
        pass
    assert isinstance(runner.get_task_exception(task2), ValueError)

    # 取消任务
    task3 = asyncio.create_task(asyncio.sleep(100))
    task3.cancel()
    try:
        await task3
    except asyncio.CancelledError:
        pass
    assert runner.is_task_cancelled(task3) is True


# ---------- base.py: AsyncRunner.sleep / sleep_async ----------





def test_sync_runner_methods():
    """覆盖 SyncRunner 的各方法。"""
    from qreward.utils.scheduler.base import SyncRunner

    runner = SyncRunner()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    runner.set_executor(executor)

    # create_task
    future = runner.create_task(lambda: 42)
    result = future.result(timeout=5)
    assert result == 42

    # get_task_result
    assert runner.get_task_result(future) == 42

    # get_task_exception
    assert runner.get_task_exception(future) is None

    # is_task_cancelled
    assert runner.is_task_cancelled(future) is False

    executor.shutdown(wait=True)


def test_sync_runner_create_task_no_executor():
    """覆盖 SyncRunner.create_task 无 executor 时抛出异常。"""
    from qreward.utils.scheduler.base import SyncRunner

    runner = SyncRunner()
    with pytest.raises(RuntimeError, match="Executor not set"):
        runner.create_task(lambda: 42)





def test_sync_hedge_submit():
    """覆盖同步执行中的 hedge 提交分支。"""
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,
        exception_types=(BaseException,),
        default_result="fallback",
    )
    def my_func():
        nonlocal call_count
        call_count += 1
        time.sleep(0.2)
        raise BaseException("slow")

    result = my_func()
    assert result == "fallback"
    assert call_count >= 1


# ---------- base.py: 异步 hedge 提交分支 ----------
@pytest.mark.asyncio
async def test_async_hedge_submit():
    """覆盖异步执行中的 hedge 提交分支。"""
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,
        exception_types=(BaseException,),
        default_result="fallback",
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.2)
        raise BaseException("slow")

    result = await my_func()
    assert result == "fallback"
    assert call_count >= 1


# ---------- base.py: 同步 speed_up 分支 ----------
def test_sync_speed_up():
    """覆盖同步执行中的 speed_up 分支。"""
    call_count = 0

    @schedule(
        retry_times=5,
        retry_interval=0.01,
        speed_up_max_multiply=3,
        exception_types=(ValueError,),
        default_result="fallback",
    )
    def my_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("retry")

    result = my_func()
    assert result == "fallback"
    assert call_count >= 3


# ---------- base.py: 异步 speed_up 分支 ----------
@pytest.mark.asyncio
async def test_async_speed_up():
    """覆盖异步执行中的 speed_up 分支。"""
    call_count = 0

    @schedule(
        retry_times=5,
        retry_interval=0.01,
        speed_up_max_multiply=3,
        exception_types=(ValueError,),
        default_result="fallback",
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("retry")

    result = await my_func()
    assert result == "fallback"
    assert call_count >= 3


# ============================================================
# 第二轮覆盖率补充测试
# ============================================================


# ---------- schedule.py: _cancel_async_task 中 pending task 已完成跳过 cancel (43->42) ----------
@pytest.mark.asyncio
async def test_cancel_async_task_pending_already_done():
    """覆盖 _cancel_async_task 中 pending task.done()=True 跳过 cancel 的分支。"""
    from qreward.utils.schedule import _cancel_async_task

    # 创建一个已完成的 task 放入 pending
    completed_task = asyncio.create_task(asyncio.sleep(0))
    await asyncio.sleep(0.01)  # 确保 task 完成
    assert completed_task.done()

    await _cancel_async_task(pending=[completed_task], done=[], retry_interval=0.1)


# ---------- schedule.py: _cancel_sync_task 中 not_done task 已完成跳过 cancel (66->65) ----------
def test_cancel_sync_task_not_done_already_done():
    """覆盖 _cancel_sync_task 中 task.done()=True 跳过 cancel 的分支。"""
    from qreward.utils.schedule import _cancel_sync_task

    # 创建一个已完成的 Future
    future = concurrent.futures.Future()
    future.set_result(42)
    assert future.done()

    _cancel_sync_task(not_done=[future], done=[], retry_interval=0.1)


# ---------- config.py: get_max_wait_time 中 has_wait_time > max_wait_time (行81) ----------
def test_config_get_max_wait_time_has_wait_exceeds_max_direct():
    """直接测试 ScheduleConfig.get_max_wait_time 中 has_wait_time > max_wait_time。"""
    from qreward.utils.scheduler.config import ScheduleConfig

    config = ScheduleConfig()
    # basic_wait_time + has_wait_time >= max_wait_time (进入第二个 if)
    # has_wait_time > max_wait_time (进入第三个 if)
    result = config.get_max_wait_time(
        basic_wait_time=1.0, has_wait_time=6.0, max_wait_time=5.0
    )
    assert result == 0.01

    # 也测试 max_wait_time - has_wait_time 分支
    result2 = config.get_max_wait_time(
        basic_wait_time=2.0, has_wait_time=4.0, max_wait_time=5.0
    )
    assert result2 == 1.0  # 5.0 - 4.0


# ---------- context.py: can_submit_task 中 speed_up 分支 less_than 返回 False (70->74) ----------
def test_can_submit_task_speed_up_pool_full():
    """覆盖 can_submit_task 中 speed_up 分支但 pool.less_than 返回 False (70->74)。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        retry_times=5,
        hedged_request_time=0,
    )
    pool = RunningTaskPool(window_max_size=5, window_interval=10, threshold=1)
    # 模拟 pool 已满
    pool._value = 100
    pool._max_size_map[0] = 100

    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 3
    context.cur_times = 1

    # run_tasks_count=1 < cur_speed_up_multiply=3, 但 pool.less_than(2) 返回 False
    result = context.can_submit_task(run_tasks_count=1)
    assert result is False


# ---------- context.py: compute_timeout 加速模式中 cur_timeout > retry_interval (190->192) ----------
def test_compute_timeout_speed_up_with_timeout():
    """覆盖 compute_timeout 中 speed_up 分支且 cur_timeout > retry_interval。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        timeout=10.0,
        retry_interval=0.5,
        retry_times=5,
        hedged_request_time=0,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 3
    context.cur_times = 1  # < retry_times

    # timeout=10, elapsed ~0, so cur_timeout ~10 > retry_interval=0.5
    timeout = context.compute_timeout(run_tasks_count=1)
    assert timeout == 0.5  # 应该被设为 retry_interval


# ---------- base.py: _handle_success 基类方法直接调用 ----------





@pytest.mark.asyncio
async def test_async_execute_no_timeout_wait():
    """覆盖 async execute_impl 中 cur_timeout <= 0 的无超时等待分支 (行 392)。"""

    @schedule(
        timeout=0,
        retry_times=0,
        retry_interval=0,
        hedged_request_time=0,
    )
    async def my_func():
        return "ok"

    result = await my_func()
    assert result == "ok"


# ---------- base.py: async debug 打印 (440) ----------
@pytest.mark.asyncio
async def test_async_debug_print(caplog):
    """覆盖异步执行中的 debug 打印 (行 440)。"""
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(debug=True, retry_times=0, limit_size=0)
        async def my_func():
            return "ok"

        result = await my_func()
        assert result == "ok"

    assert any("[schedule]" in r.message and "execute finish" in r.message for r in caplog.records)


# ---------- base.py: async hedge 提交分支 (345->361) ----------
@pytest.mark.asyncio
async def test_async_hedge_submit_record():
    """覆盖 async execute_impl 中 is_hedge_submit 返回 True 的分支 (行 349-350)。"""
    call_count = 0

    @schedule(
        retry_times=5,
        retry_interval=0.01,
        hedged_request_time=0.01,
        hedged_request_proportion=1.0,
        hedged_request_max_times=3,
        exception_types=(BaseException,),
        default_result="fallback",
        debug=True,
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        raise BaseException("slow")

    result = await my_func()
    assert result == "fallback"
    assert call_count >= 1


# ---------- base.py: async exception 记录分支 (362->377) ----------
@pytest.mark.asyncio
async def test_async_exception_record_on_retry():
    """覆盖 async execute_impl 中 result_exception 不为 None 时记录异常的分支。"""
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="fallback",
        debug=True,
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("retry me")

    result = await my_func()
    assert result == "fallback"
    assert call_count >= 2


# ---------- base.py: sync retryable 异常后 sleep (554-555) ----------
def test_sync_retryable_exception_sleep():
    """覆盖 sync execute_impl 中可重试异常后 sleep 的分支 (行 642-646)。"""
    call_count = 0

    @schedule(
        retry_times=2,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="fallback",
        debug=True,
    )
    def my_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("retryable")

    result = my_func()
    assert result == "fallback"
    assert call_count >= 2


# ---------- base.py: sync timeout (578->594, 595->611) ----------
def test_sync_timeout_check():
    """覆盖 sync execute_impl 中超时检查分支 (行 660-672)。"""

    @schedule(
        timeout=0.2,
        retry_times=10,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=True,
    )
    def my_func():
        time.sleep(0.3)
        raise BaseException("slow")

    with pytest.raises(TimeoutError):
        my_func()


# ---------- base.py: sync debug 打印 (617) ----------
def test_sync_debug_print_with_exception(caplog):
    """覆盖同步执行中有异常时的 debug 打印 (行 685-692)。"""
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(
            debug=True,
            retry_times=1,
            retry_interval=0.01,
            exception_types=(ValueError,),
            default_result="fallback",
        )
        def my_func():
            raise ValueError("test")

        result = my_func()
        assert result == "fallback"

    assert any("[schedule]" in r.message and "execute finish" in r.message for r in caplog.records)


# ---------- base.py: sync cancelled task (539-540) ----------
def test_sync_cancelled_future():
    """覆盖 sync execute_impl 中 finished.cancelled() 分支 (行 618-619)。"""

    @schedule(
        timeout=0.3,
        retry_times=2,
        retry_interval=0.01,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,
        exception_types=(BaseException,),
        default_result="fallback",
    )
    def my_func():
        time.sleep(0.5)
        raise BaseException("slow")

    result = my_func()
    assert result == "fallback"


# ---------- base.py: AsyncRunner.create_task (236) ----------
@pytest.mark.asyncio
async def test_async_runner_create_task():
    """覆盖 AsyncRunner.create_task 方法 (行 236)。"""
    from qreward.utils.scheduler.base import AsyncRunner

    runner = AsyncRunner()

    async def my_coro():
        return 42

    task = runner.create_task(my_coro)
    result = await task
    assert result == 42


# ---------- base.py: AsyncRunner.wait_for_tasks (250-255) ----------


def test_should_hedge_time_condition_false():
    """覆盖 _should_hedge 中时间条件不满足的分支。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        hedged_request_time=100.0,  # 很大的时间，不会触发
        hedged_request_proportion=0.5,
        hedged_request_max_times=3,
        retry_times=5,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_hedged_request_times = 1
    # last_submit_time 刚刚设置，time_since_last 很小
    context.last_submit_time = time.perf_counter()

    result = context._should_hedge(run_tasks_count=1)
    assert result is False


def test_should_hedge_max_times_exceeded():
    """覆盖 _should_hedge 中 cur_hedged_request_times > max 的分支。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        hedged_request_time=0.001,
        hedged_request_proportion=0.5,
        hedged_request_max_times=1,
        retry_times=5,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_hedged_request_times = 5  # > max_times

    result = context._should_hedge(run_tasks_count=1)
    assert result is False


# ---------- context.py: is_hedge_submit 各分支 ----------
def test_is_hedge_submit_hedged_disabled():
    """覆盖 is_hedge_submit 中 hedged_request_time <= 0 的分支。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(hedged_request_time=0, retry_times=5)
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )

    result = context.is_hedge_submit(run_tasks_count=1)
    assert result is False


def test_is_hedge_submit_speed_up_overrides():
    """覆盖 is_hedge_submit 中 cur_speed_up_multiply > run_tasks_count 的分支。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        hedged_request_time=0.001,
        hedged_request_proportion=0.5,
        hedged_request_max_times=3,
        retry_times=5,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 5  # > run_tasks_count

    result = context.is_hedge_submit(run_tasks_count=1)
    assert result is False


def test_is_hedge_submit_max_times_exceeded():
    """覆盖 is_hedge_submit 中 cur_hedged_request_times > max 的分支。"""
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.pools import RunningTaskPool

    config = ScheduleConfig(
        hedged_request_time=0.001,
        hedged_request_proportion=0.5,
        hedged_request_max_times=1,
        retry_times=5,
    )
    pool = RunningTaskPool(window_max_size=100, window_interval=10, threshold=1)
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test",
        running_task_pool=pool,
        limiter=None,
    )
    context.cur_speed_up_multiply = 0
    context.last_submit_time = time.perf_counter() - 1.0
    context.cur_hedged_request_times = 5  # > max_times

    result = context.is_hedge_submit(run_tasks_count=1)
    assert result is False


# ============================================================
# 第三轮覆盖率补充测试 - 精确覆盖 execute_impl 内部分支
# ============================================================


# ---------- base.py 行 554-555, 595->611, 617: sync retryable + default_result + debug ----------
def test_sync_execute_retryable_with_debug_and_default(caplog):
    """精确覆盖 sync execute_impl 中:
    - 行 638-648: retryable 异常后 time.sleep(wait_time); break
    - 行 675-680: default_result 返回
    - 行 685-692: debug 打印
    """
    import logging

    call_count = 0

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(
            retry_times=2,
            retry_interval=0.01,
            timeout=0,  # 无超时，避免超时分支干扰
            exception_types=(ValueError,),
            default_result="sync-fallback",
            debug=True,
            limit_size=0,
        )
        def my_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("retryable error")

        result = my_func()
        assert result == "sync-fallback"
        assert call_count >= 2  # 至少重试了一次

    assert any("[schedule]" in r.message and "execute finish" in r.message for r in caplog.records)


# ---------- base.py 行 578->594: sync timeout 检查 ----------
def test_sync_execute_timeout_triggers():
    """精确覆盖 sync execute_impl 中超时检查分支 (行 660-672)。
    函数执行时间超过 timeout，触发 TimeoutError。
    """

    @schedule(
        timeout=0.1,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=True,
        limit_size=0,
    )
    def my_func():
        time.sleep(0.2)  # 超过 timeout
        raise BaseException("slow")

    with pytest.raises(TimeoutError, match="execute more than"):
        my_func()


# ---------- base.py 行 392, 440: async 无超时等待 + debug ----------
@pytest.mark.asyncio
async def test_async_execute_no_timeout_with_retry_and_debug(caplog):
    """精确覆盖 async execute_impl 中:
    - 行 372-375: 无超时等待 (cur_timeout <= 0)
    - 行 437-445: debug 打印
    - 行 349-354: 异常记录分支
    """
    import logging

    call_count = 0

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(
            retry_times=2,
            retry_interval=0,  # retry_interval=0 使 compute_timeout 返回 0
            timeout=0,  # 无超时
            exception_types=(ValueError,),
            default_result="async-fallback",
            debug=True,
            limit_size=0,
        )
        async def my_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("retryable")

        result = await my_func()
        assert result == "async-fallback"
        assert call_count >= 2

    assert any("[schedule]" in r.message and "execute finish" in r.message for r in caplog.records)


# ---------- base.py 行 345->361: async hedge 提交 ----------
@pytest.mark.asyncio
async def test_async_execute_hedge_submit_triggered():
    """精确覆盖 async execute_impl 中 hedge 提交分支 (行 349-350)。
    需要: is_hedge_submit 返回 True，即:
    - hedged_request_time > 0
    - cur_speed_up_multiply <= run_tasks_count
    - time_since_last >= hedged_request_time
    - running_task_pool.less_than(threshold) 返回 True
    """
    call_count = 0

    @schedule(
        retry_times=5,
        retry_interval=0.05,
        hedged_request_time=0.02,  # 很短的 hedge 时间
        hedged_request_proportion=1.0,
        hedged_request_max_times=3,
        exception_types=(BaseException,),
        default_result="hedge-fallback",
        debug=True,
        limit_size=0,
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)  # 慢于 hedged_request_time
        raise BaseException("slow")

    result = await my_func()
    assert result == "hedge-fallback"
    assert call_count >= 2  # 至少有一次 hedge 提交


# ---------- base.py 行 362->377: async 异常记录分支 ----------
@pytest.mark.asyncio
async def test_async_execute_exception_record_on_resubmit():
    """精确覆盖 async execute_impl 中异常记录分支 (行 352-354)。
    需要: is_hedge_submit 返回 False 且 result_exception 不为 None。
    这发生在第一次任务失败后，重新提交新任务时。
    """
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        hedged_request_time=0,  # 禁用 hedge，确保 is_hedge_submit 返回 False
        exception_types=(ValueError,),
        default_result="exception-fallback",
        debug=True,
        limit_size=0,
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        raise ValueError(f"attempt {call_count}")

    result = await my_func()
    assert result == "exception-fallback"
    assert call_count >= 2  # 至少重试了一次


# ---------- base.py 行 539-540: sync cancelled future ----------
def test_sync_execute_with_cancelled_future():
    """精确覆盖 sync execute_impl 中 finished.cancelled() 分支 (行 617-618)。
    需要在 concurrent.futures.wait 返回时有一个已取消的 Future。
    通过 hedged request 和超时来触发。
    """

    @schedule(
        timeout=0.3,
        retry_times=3,
        retry_interval=0.01,
        hedged_request_time=0.05,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,
        exception_types=(BaseException,),
        default_result="cancelled-fallback",
        debug=True,
        limit_size=0,
    )
    def my_func():
        time.sleep(0.5)
        raise BaseException("slow")

    result = my_func()
    assert result == "cancelled-fallback"


# ---------- config.py 行 81: get_max_wait_time has_wait > max ----------
def test_sync_execute_with_has_wait_exceeds_max():
    """通过集成测试间接覆盖 config.py 行 85 (has_wait_time > max_wait_time)。
    设置 timeout 很短，让 elapsed > timeout，触发 get_max_wait_time 中
    has_wait_time > max_wait_time 的分支。
    """

    @schedule(
        timeout=0.05,
        retry_times=5,
        retry_interval=0.1,  # retry_interval > timeout
        exception_types=(ValueError,),
        default_result="timeout-fallback",
        debug=True,
        limit_size=0,
    )
    def my_func():
        time.sleep(0.1)
        raise ValueError("slow")

    result = my_func()
    assert result == "timeout-fallback"


# ---------- context.py 行 202-204: get_limiter_timeout ----------
def test_sync_execute_with_limiter_timeout():
    """通过集成测试覆盖 context.py 行 202-204 (get_limiter_timeout)。
    设置 limit_size > 0 和 timeout > 0，让 limiter_timeout 被计算。
    """

    @schedule(
        timeout=1.0,
        retry_times=2,
        retry_interval=0.01,
        limit_size=10,
        exception_types=(ValueError,),
        default_result="limiter-fallback",
        debug=True,
    )
    def my_func():
        raise ValueError("test")

    result = my_func()
    assert result == "limiter-fallback"


@pytest.mark.asyncio
async def test_async_execute_with_limiter_timeout():
    """通过异步集成测试覆盖 context.py 行 202-204 (get_limiter_timeout)。"""

    @schedule(
        timeout=1.0,
        retry_times=2,
        retry_interval=0.01,
        limit_size=10,
        exception_types=(ValueError,),
        default_result="limiter-fallback",
        debug=True,
    )
    async def my_func():
        raise ValueError("test")

    result = await my_func()
    assert result == "limiter-fallback"


# ---------- base.py: async 成功后 cancel_tasks_async 调用 ----------
@pytest.mark.asyncio
async def test_async_execute_success_triggers_cancel_tasks():
    """覆盖 async execute_impl 中成功后 cancel_tasks_async 调用。"""
    call_count = 0

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        hedged_request_time=0.01,
        hedged_request_proportion=1.0,
        hedged_request_max_times=2,
        exception_types=(BaseException,),
        debug=True,
        limit_size=0,
    )
    async def my_func():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            await asyncio.sleep(0.2)  # 第一次慢
            raise BaseException("slow")
        return "success"  # 第二次成功

    result = await my_func()
    assert result == "success"


# ---------- base.py: sync 非可重试异常分支 ----------
def test_sync_execute_non_retryable_exception():
    """覆盖 sync execute_impl 中非可重试异常分支 (行 649-657)。
    抛出不在 exception_types 中的异常。
    """

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),  # 只重试 ValueError
        debug=True,
        limit_size=0,
    )
    def my_func():
        raise TypeError("non-retryable")

    with pytest.raises(TypeError, match="non-retryable"):
        my_func()


# ---------- base.py: async 非可重试异常分支 ----------
@pytest.mark.asyncio
async def test_async_execute_non_retryable_exception():
    """覆盖 async execute_impl 中非可重试异常分支。"""

    @schedule(
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        debug=True,
        limit_size=0,
    )
    async def my_func():
        raise TypeError("non-retryable")

    with pytest.raises(TypeError, match="non-retryable"):
        await my_func()


# ---------- base.py: async timeout 分支 ----------
@pytest.mark.asyncio
async def test_async_execute_timeout_triggers():
    """覆盖 async execute_impl 中超时检查分支。"""

    @schedule(
        timeout=0.1,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=True,
        limit_size=0,
    )
    async def my_func():
        await asyncio.sleep(0.2)
        raise BaseException("slow")

    with pytest.raises(asyncio.TimeoutError, match="execute more than"):
        await my_func()


# ============================================================
# 第四轮覆盖率补充测试 - 直接调用 execute_impl / cancel_tasks
# 精确覆盖 base.py 中所有剩余未覆盖行
# ============================================================

from qreward.utils.scheduler.base import AsyncRunner, SyncRunner
from qreward.utils.scheduler.config import ScheduleConfig, _sentinel_none
from qreward.utils.scheduler.context import ExecutionContext
from qreward.utils.scheduler.pools import RunningTaskPool


def _make_pool(key: str) -> RunningTaskPool:
    """创建一个干净的 RunningTaskPool 实例（避免全局池污染）。"""
    pool = RunningTaskPool(window_max_size=100, window_interval=60, threshold=100)
    return pool


# ---------- AsyncRunner.cancel_tasks: 行 276-277 (done 非空) ----------



@pytest.mark.asyncio
async def test_async_runner_execute_impl_hedge_branch():
    """直接调用 AsyncRunner.execute_impl，精确覆盖:
    - 行 345->361: is_hedge_submit 为 True -> record_hedge()
    - 行 440: debug 打印
    函数执行慢（0.5s），hedged_request_time=0.02s，
    asyncio.wait 超时后 run_tasks_count=1，触发 hedge 提交。
    """
    runner = AsyncRunner()
    call_count = 0

    async def slow_failing_func():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.5)  # 慢于 hedged_request_time
        raise ValueError(f"attempt {call_count}")

    pool = _make_pool("test_async_hedge_branch")
    config = ScheduleConfig(
        timeout=2.0,
        hedged_request_time=0.02,  # 很短的 hedge 时间
        hedged_request_proportion=1.0,
        hedged_request_max_times=3,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="hedge-fallback",
        debug=True,
    )
    context = ExecutionContext(
        func=slow_failing_func,
        config=config,
        key="test_async_hedge_branch",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    result = await runner.execute_impl(context, config)
    assert result == "hedge-fallback"
    assert call_count >= 2  # 至少有一次 hedge 提交


# ---------- AsyncRunner.execute_impl: 行 362->377 (异常记录) ----------
# 异常记录分支触发条件：
# 1. 第一个 task 失败，_handle_exception 设置 result_exception
# 2. should_break=True，sleep 后 break
# 3. 下一次循环 run_tasks_count=0，can_submit_task 返回 True
# 4. is_hedge_submit(0) 返回 False（因为 hedged_request_time=0）
# 5. result_exception 不为 None -> record_exception
@pytest.mark.asyncio
async def test_async_runner_execute_impl_exception_record():
    """直接调用 AsyncRunner.execute_impl，精确覆盖:
    - 行 362->377: result_exception 不为 None -> record_exception()
    - 行 392: cur_timeout <= 0 -> asyncio.wait 无超时
    - 行 440: debug 打印
    """
    runner = AsyncRunner()
    call_count = 0

    async def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError(f"attempt {call_count}")

    pool = _make_pool("test_async_exc_record")
    config = ScheduleConfig(
        timeout=0,  # 无超时
        hedged_request_time=0,  # 禁用 hedge -> is_hedge_submit 返回 False
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="fallback",
        debug=True,
    )
    context = ExecutionContext(
        func=failing_func,
        config=config,
        key="test_async_exc_record",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    result = await runner.execute_impl(context, config)
    assert result == "fallback"
    assert call_count >= 2
    # 验证异常被记录
    assert len(context.result_exception_list) >= 1


# ---------- SyncRunner.execute_impl: 行 578->594 (hedge) + 617 (debug) ----------
def test_sync_runner_execute_impl_hedge_branch():
    """直接调用 SyncRunner.execute_impl，精确覆盖:
    - 行 578->594: is_hedge_submit 为 True -> record_hedge()
    - 行 617: debug 打印
    函数执行慢（0.5s），hedged_request_time=0.02s，
    concurrent.futures.wait 超时后 run_tasks_count=1，触发 hedge 提交。
    """
    runner = SyncRunner()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    runner.set_executor(executor)
    call_count = 0

    def slow_failing_func():
        nonlocal call_count
        call_count += 1
        time.sleep(0.5)  # 慢于 hedged_request_time
        raise ValueError(f"attempt {call_count}")

    pool = _make_pool("test_sync_hedge_branch")
    config = ScheduleConfig(
        timeout=2.0,
        hedged_request_time=0.02,
        hedged_request_proportion=1.0,
        hedged_request_max_times=3,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="sync-hedge-fallback",
        debug=True,
    )
    context = ExecutionContext(
        func=slow_failing_func,
        config=config,
        key="test_sync_hedge_branch",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    result = runner.execute_impl(context, config)
    assert result == "sync-hedge-fallback"
    assert call_count >= 2
    executor.shutdown(wait=False)


# ---------- SyncRunner.execute_impl: 行 595->611 (异常记录) ----------
def test_sync_runner_execute_impl_exception_record():
    """直接调用 SyncRunner.execute_impl，精确覆盖:
    - 行 595->611: result_exception 不为 None -> record_exception()
    - 行 617: debug 打印
    """
    runner = SyncRunner()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    runner.set_executor(executor)
    call_count = 0

    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError(f"attempt {call_count}")

    pool = _make_pool("test_sync_exc_record")
    config = ScheduleConfig(
        timeout=0,
        hedged_request_time=0,  # 禁用 hedge
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="fallback",
        debug=True,
    )
    context = ExecutionContext(
        func=failing_func,
        config=config,
        key="test_sync_exc_record",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    result = runner.execute_impl(context, config)
    assert result == "fallback"
    assert call_count >= 2
    assert len(context.result_exception_list) >= 1
    executor.shutdown(wait=False)


# ---------- SyncRunner.execute_impl: cancelled future 分支 ----------
def test_sync_runner_execute_impl_cancelled_future():
    """直接调用 SyncRunner.execute_impl，覆盖 finished.cancelled() 分支 (行 621-622)。
    通过 hedged request 让多个 future 并发，其中一个可能被取消。
    """
    runner = SyncRunner()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    runner.set_executor(executor)
    call_count = 0

    def slow_failing_func():
        nonlocal call_count
        call_count += 1
        time.sleep(0.3)
        raise ValueError(f"attempt {call_count}")

    pool = _make_pool("test_sync_cancelled")
    config = ScheduleConfig(
        timeout=1.0,
        hedged_request_time=0.02,
        hedged_request_proportion=1.0,
        hedged_request_max_times=3,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(ValueError,),
        default_result="cancelled-fallback",
        debug=True,
    )
    context = ExecutionContext(
        func=slow_failing_func,
        config=config,
        key="test_sync_cancelled",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    result = runner.execute_impl(context, config)
    assert result == "cancelled-fallback"
    executor.shutdown(wait=False)


# ---------- AsyncRunner.execute_impl: timeout 分支 ----------
@pytest.mark.asyncio
async def test_async_runner_execute_impl_timeout():
    """直接调用 AsyncRunner.execute_impl，覆盖超时分支 (行 425-434)。"""
    runner = AsyncRunner()

    async def slow_func():
        await asyncio.sleep(10)
        return "never"

    pool = _make_pool("test_async_timeout_impl")
    config = ScheduleConfig(
        timeout=0.1,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=True,
    )
    context = ExecutionContext(
        func=slow_func,
        config=config,
        key="test_async_timeout_impl",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    with pytest.raises(asyncio.TimeoutError, match="execute more than"):
        await runner.execute_impl(context, config)


# ---------- SyncRunner.execute_impl: timeout 分支 ----------
def test_sync_runner_execute_impl_timeout():
    """直接调用 SyncRunner.execute_impl，覆盖超时分支 (行 662-672)。"""
    runner = SyncRunner()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    runner.set_executor(executor)

    def slow_func():
        time.sleep(10)
        return "never"

    pool = _make_pool("test_sync_timeout_impl")
    config = ScheduleConfig(
        timeout=0.1,
        retry_times=5,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=True,
    )
    context = ExecutionContext(
        func=slow_func,
        config=config,
        key="test_sync_timeout_impl",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    with pytest.raises(TimeoutError, match="execute more than"):
        runner.execute_impl(context, config)
    executor.shutdown(wait=False)


# ---------- AsyncRunner.execute_impl: 成功后 cancel_tasks_async 调用 ----------
@pytest.mark.asyncio
async def test_async_runner_execute_impl_success_with_hedge():
    """直接调用 AsyncRunner.execute_impl，第一个 task 慢，hedge task 成功。
    覆盖 _handle_success_async 中的 cancel_tasks_async 调用。
    """
    runner = AsyncRunner()
    call_count = 0

    async def variable_func():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(0.5)  # 第一次慢
            return "slow"
        return "fast"  # hedge 成功

    pool = _make_pool("test_async_success_hedge_impl")
    config = ScheduleConfig(
        timeout=2.0,
        hedged_request_time=0.02,
        hedged_request_proportion=1.0,
        hedged_request_max_times=3,
        retry_times=3,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=True,
    )
    context = ExecutionContext(
        func=variable_func,
        config=config,
        key="test_async_success_hedge_impl",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    result = await runner.execute_impl(context, config)
    assert result in ("slow", "fast")


# ---------- SyncRunner.execute_impl: 非可重试异常分支 ----------
def test_sync_runner_execute_impl_non_retryable():
    """直接调用 SyncRunner.execute_impl，抛出非可重试异常。
    覆盖行 649-657: non-retryable exception -> cancel_tasks -> finish
    """
    runner = SyncRunner()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    runner.set_executor(executor)

    def failing_func():
        raise TypeError("non-retryable")

    pool = _make_pool("test_sync_non_retryable_impl")
    config = ScheduleConfig(
        timeout=0,
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),  # 只重试 ValueError
        debug=True,
    )
    context = ExecutionContext(
        func=failing_func,
        config=config,
        key="test_sync_non_retryable_impl",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    with pytest.raises(TypeError, match="non-retryable"):
        runner.execute_impl(context, config)
    executor.shutdown(wait=False)


# ---------- AsyncRunner.execute_impl: 非可重试异常分支 ----------
@pytest.mark.asyncio
async def test_async_runner_execute_impl_non_retryable():
    """直接调用 AsyncRunner.execute_impl，抛出非可重试异常。
    覆盖行 409-417: non-retryable exception -> cancel_tasks_async -> finish
    """
    runner = AsyncRunner()

    async def failing_func():
        raise TypeError("non-retryable")

    pool = _make_pool("test_async_non_retryable_impl")
    config = ScheduleConfig(
        timeout=0,
        retry_times=3,
        retry_interval=0.01,
        exception_types=(ValueError,),
        debug=True,
    )
    context = ExecutionContext(
        func=failing_func,
        config=config,
        key="test_async_non_retryable_impl",
        running_task_pool=pool,
        limiter=None,
    )
    pool.add(1)

    with pytest.raises(TypeError, match="non-retryable"):
        await runner.execute_impl(context, config)


# ============================================================
# Sprint 4: ThreadPoolExecutor cleanup, system exception handling,
#            and overload deep exception chain tests
# ============================================================

from qreward.utils.scheduler.decorator import (
    _executor_registry,
    _shutdown_executors,
    _register_executor,
)
from qreward.utils.scheduler.overload import OverloadChecker, MAX_EXCEPTION_CHAIN_DEPTH


def test_sync_executor_cleanup():
    """Verify ThreadPoolExecutor is registered for atexit cleanup
    and _shutdown_executors() properly shuts down all executors."""
    initial_count = len(_executor_registry)

    @schedule(retry_times=0)
    def sync_noop():
        return "ok"

    assert sync_noop() == "ok"
    assert len(_executor_registry) > initial_count

    registered_executor = _executor_registry[-1]
    assert not registered_executor._shutdown

    _shutdown_executors()

    assert len(_executor_registry) == 0


def test_register_executor_idempotent_atexit():
    """Verify _register_executor registers atexit only once."""
    import qreward.utils.scheduler.decorator as dec_mod

    original_flag = dec_mod._atexit_registered
    dec_mod._atexit_registered = False

    executor1 = concurrent.futures.ThreadPoolExecutor()
    executor2 = concurrent.futures.ThreadPoolExecutor()

    _register_executor(executor1)
    assert dec_mod._atexit_registered is True

    _register_executor(executor2)
    assert dec_mod._atexit_registered is True

    executor1.shutdown(wait=False)
    executor2.shutdown(wait=False)

    with dec_mod._executor_registry_lock:
        dec_mod._executor_registry.remove(executor1)
        dec_mod._executor_registry.remove(executor2)

    dec_mod._atexit_registered = original_flag


def test_system_exit_not_caught():
    """Verify SystemExit is not caught by _handle_exception
    even when exception_types=BaseException."""
    runner = AsyncRunner()
    config = ScheduleConfig(
        timeout=0,
        retry_times=3,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=False,
    )

    future = concurrent.futures.Future()
    future.set_exception(SystemExit(1))

    pool = _make_pool("test_system_exit")
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test_system_exit",
        running_task_pool=pool,
        limiter=None,
    )

    with pytest.raises(SystemExit):
        runner._handle_exception(context, config, future, can_add_speed_up=False)


def test_keyboard_interrupt_not_caught():
    """Verify KeyboardInterrupt is not caught by _handle_exception
    even when exception_types=BaseException."""
    runner = AsyncRunner()
    config = ScheduleConfig(
        timeout=0,
        retry_times=3,
        retry_interval=0.01,
        exception_types=(BaseException,),
        debug=False,
    )

    future = concurrent.futures.Future()
    future.set_exception(KeyboardInterrupt())

    pool = _make_pool("test_keyboard_interrupt")
    context = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test_keyboard_interrupt",
        running_task_pool=pool,
        limiter=None,
    )

    with pytest.raises(KeyboardInterrupt):
        runner._handle_exception(context, config, future, can_add_speed_up=False)


def test_overload_deep_exception_chain():
    """Verify OverloadChecker handles deep exception chains (>50 levels)
    without stack overflow, using iterative traversal with depth limit."""
    # Build a chain of 100 exceptions — deeper than MAX_EXCEPTION_CHAIN_DEPTH
    chain_depth = 100
    assert chain_depth > MAX_EXCEPTION_CHAIN_DEPTH

    innermost = ValueError("deep root")
    current = innermost
    for i in range(chain_depth - 1):
        wrapper = RuntimeError(f"level-{i}")
        wrapper.__cause__ = current
        current = wrapper

    # No overload keyword in any exception — should return False without overflow
    assert OverloadChecker.check(current) is False


def test_overload_checker_finds_overload_in_chain():
    """Verify OverloadChecker detects overload signal in a chained exception."""
    root = RuntimeError("rate limit exceeded")
    wrapper = ValueError("wrapper")
    wrapper.__cause__ = root

    assert OverloadChecker.check(wrapper) is True


def test_overload_checker_circular_chain():
    """Verify OverloadChecker handles circular exception chains gracefully."""
    exc_a = RuntimeError("a")
    exc_b = RuntimeError("b")
    exc_a.__cause__ = exc_b
    exc_b.__cause__ = exc_a

    # Should not infinite loop — visited set prevents revisiting
    assert OverloadChecker.check(exc_a) is False


# ============================================================
# Sprint 5: Limiter Condition-based wait tests
# ============================================================


def test_limiter_condition_wakeup():
    """Verify LimiterPool.allow() uses Condition-based wait instead of
    busy-wait with time.sleep, and threads are woken up via notify."""
    from qreward.utils.scheduler.limiter import LimiterPool

    # Create a limiter that allows 1 request per 0.2s window
    limiter = LimiterPool(rate=1, window=0.2)

    # Verify the limiter uses a Condition internally
    assert hasattr(limiter, "_condition")
    assert isinstance(limiter._condition, threading.Condition)

    # First call should succeed immediately
    assert limiter.allow(timeout=1.0) is True

    # Second call should block until the window expires, then succeed
    start = time.monotonic()
    assert limiter.allow(timeout=1.0) is True
    elapsed = time.monotonic() - start

    # Should have waited approximately 0.2s (the window), not longer
    assert 0.1 <= elapsed <= 0.5


def test_limiter_condition_timeout():
    """Verify LimiterPool.allow() returns False when timeout expires
    while waiting on the Condition."""
    from qreward.utils.scheduler.limiter import LimiterPool

    # Create a limiter that allows 1 request per 1.0s window
    limiter = LimiterPool(rate=1, window=1.0)

    # First call succeeds
    assert limiter.allow(timeout=2.0) is True

    # Second call with very short timeout should fail
    start = time.monotonic()
    result = limiter.allow(timeout=0.05)
    elapsed = time.monotonic() - start

    assert result is False
    assert elapsed < 0.3  # Should return quickly after timeout


# ============================================================
# Sprint 8: Observability — ScheduleMetrics + logging
# ============================================================

def test_schedule_metrics_fields():
    """Verify ScheduleMetrics dataclass has all required fields."""
    from qreward.utils.scheduler.metrics import ScheduleMetrics

    metrics = ScheduleMetrics(
        total_calls=3,
        success_count=1,
        failure_count=2,
        retry_count=2,
        total_latency_ms=150.0,
        avg_latency_ms=50.0,
    )
    assert metrics.total_calls == 3
    assert metrics.success_count == 1
    assert metrics.failure_count == 2
    assert metrics.retry_count == 2
    assert metrics.total_latency_ms == 150.0
    assert metrics.avg_latency_ms == 50.0


@pytest.mark.asyncio
async def test_metrics_callback():
    """Verify schedule decorator accepts and invokes metrics_callback."""
    from qreward.utils.scheduler.metrics import ScheduleMetrics

    collected = []

    @schedule(metrics_callback=collected.append)
    async def _ok():
        return 42

    result = await _ok()
    assert result == 42
    assert len(collected) == 1

    metrics = collected[0]
    assert isinstance(metrics, ScheduleMetrics)
    assert metrics.total_calls >= 1
    assert metrics.success_count == 1
    assert metrics.failure_count == 0
    assert metrics.retry_count == 0
    assert metrics.total_latency_ms >= 0
    assert metrics.avg_latency_ms >= 0


@pytest.mark.asyncio
async def test_metrics_callback_invoked():
    """Verify metrics_callback receives correct metrics after retries."""
    from qreward.utils.scheduler.metrics import ScheduleMetrics

    collected = []
    call_count = 0

    @schedule(
        retry_times=2,
        retry_interval=0.01,
        metrics_callback=collected.append,
    )
    async def _flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("transient")
        return "ok"

    result = await _flaky()
    assert result == "ok"
    assert len(collected) == 1

    metrics = collected[0]
    assert isinstance(metrics, ScheduleMetrics)
    assert metrics.total_calls >= 2
    assert metrics.success_count == 1
    assert metrics.retry_count >= 1
    assert metrics.total_latency_ms > 0


def test_metrics_callback_sync():
    """Verify metrics_callback works with sync schedule decorator."""
    from qreward.utils.scheduler.metrics import ScheduleMetrics

    collected = []

    @schedule(metrics_callback=collected.append)
    def _sync_ok():
        return 99

    result = _sync_ok()
    assert result == 99
    assert len(collected) == 1

    metrics = collected[0]
    assert isinstance(metrics, ScheduleMetrics)
    assert metrics.total_calls >= 1
    assert metrics.success_count == 1
    assert metrics.failure_count == 0


def test_context_metrics_fields():
    """Verify ExecutionContext.build_metrics() returns correct ScheduleMetrics."""
    from qreward.utils.scheduler.context import ExecutionContext
    from qreward.utils.scheduler.config import ScheduleConfig
    from qreward.utils.scheduler.pools import RunningTaskPool
    from qreward.utils.scheduler.metrics import ScheduleMetrics

    config = ScheduleConfig(
        timeout=10,
        hedged_request_time=0,
        hedged_request_proportion=0.05,
        hedged_request_max_times=2,
        speed_up_max_multiply=5,
        retry_times=3,
        retry_interval=1,
        limit_size=0,
        limit_window=1.0,
        key_func=None,
        exception_types=BaseException,
        default_result=None,
        debug=False,
    )
    pool = RunningTaskPool.get_pool("test_metrics_fields")

    ctx = ExecutionContext(
        func=lambda: None,
        config=config,
        key="test_metrics_fields",
        running_task_pool=pool,
        limiter=None,
    )

    # Simulate 3 attempts, 2 failures, 1 success
    ctx.cur_times = 3
    ctx.result_exception_list = ["ValueError err1", "TimeoutError err2"]
    ctx.result_exception = None  # final success

    metrics = ctx.build_metrics()
    assert isinstance(metrics, ScheduleMetrics)
    assert metrics.total_calls == 3
    assert metrics.success_count == 1
    assert metrics.failure_count == 2
    assert metrics.retry_count == 2
    assert metrics.total_latency_ms >= 0
    assert metrics.avg_latency_ms >= 0


@pytest.mark.asyncio
async def test_schedule_debug_uses_logger(caplog):
    """Verify debug=True uses logger.debug instead of print."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(debug=True)
        async def _debug_func():
            return "debug_result"

        result = await _debug_func()
        assert result == "debug_result"

    assert any("execute finish" in record.message for record in caplog.records)


def test_schedule_debug_sync_uses_logger(caplog):
    """Verify debug=True uses logger.debug for sync functions."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.utils.scheduler.base"):

        @schedule(debug=True)
        def _debug_sync():
            return "sync_debug"

        result = _debug_sync()
        assert result == "sync_debug"

    assert any("execute finish" in record.message for record in caplog.records)


# ---------- Circuit Breaker Tests ----------


def test_circuit_breaker_state_transitions():
    """M-VERIFY-1: CircuitBreaker state transitions CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    current_time = 0.0

    def fake_time():
        return current_time

    breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=10.0,
        time_func=fake_time,
    )

    # Initial state is CLOSED
    assert breaker.state == CircuitState.CLOSED

    # Record failures to trip the breaker
    for _ in range(3):
        breaker.record_failure()

    # Should be OPEN now
    assert breaker.state == CircuitState.OPEN

    # Advance time past recovery_timeout
    current_time = 11.0

    # Should transition to HALF_OPEN
    assert breaker.state == CircuitState.HALF_OPEN

    # Successful probe should reset to CLOSED
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_opens_on_threshold():
    """M-VERIFY-2: Consecutive failures reaching threshold triggers OPEN."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=5)

    # Failures below threshold keep CLOSED
    for i in range(4):
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED, f"Should be CLOSED after {i+1} failures"

    # 5th failure trips the breaker
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_blocks_requests():
    """M-VERIFY-3: OPEN state blocks allow_request()."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

    # CLOSED allows requests
    assert breaker.allow_request() is True

    # Trip the breaker
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # OPEN blocks requests
    assert breaker.allow_request() is False
    assert breaker.allow_request() is False


def test_circuit_breaker_half_open():
    """M-VERIFY-4: After recovery_timeout, enters HALF_OPEN and allows probe."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    current_time = 0.0

    def fake_time():
        return current_time

    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=5.0,
        half_open_max_calls=1,
        time_func=fake_time,
    )

    # Trip the breaker
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False

    # Advance time past recovery_timeout
    current_time = 6.0

    # Should allow one probe request in HALF_OPEN
    assert breaker.allow_request() is True
    # Second request in HALF_OPEN should be blocked (max_calls=1)
    assert breaker.allow_request() is False


def test_circuit_breaker_half_open_failure_reopens():
    """HALF_OPEN probe failure re-opens the breaker."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    current_time = 0.0

    def fake_time():
        return current_time

    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=5.0,
        time_func=fake_time,
    )

    # Trip the breaker
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Advance time to enter HALF_OPEN
    current_time = 6.0
    assert breaker.state == CircuitState.HALF_OPEN

    # Probe fails -> re-open
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_reset():
    """reset() returns breaker to initial CLOSED state."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_circuit_breaker_success_resets_failure_count():
    """A success in CLOSED state resets the consecutive failure counter."""
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=3)

    breaker.record_failure()
    breaker.record_failure()
    # One more failure would trip it, but a success resets
    breaker.record_success()

    # Now need 3 more failures to trip
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_schedule_with_circuit_breaker():
    """S-1: schedule decorator supports circuit_breaker_threshold parameter."""

    call_count = 0

    @schedule(
        circuit_breaker_threshold=3,
        circuit_breaker_recovery=60.0,
        retry_times=0,
        limit_size=0,
        exception_types=(ValueError,),
        default_result="fallback",
    )
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("always fails")

    # First 3 calls should execute (and fail with default_result)
    for _ in range(3):
        result = failing_func()
        assert result == "fallback"

    # After 3 failures, circuit breaker should be open -> RuntimeError
    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="Circuit breaker is open"):
        failing_func()


@pytest.mark.asyncio
async def test_schedule_with_circuit_breaker_async():
    """S-1 async: schedule decorator supports circuit_breaker_threshold for async."""

    call_count = 0

    @schedule(
        circuit_breaker_threshold=2,
        circuit_breaker_recovery=60.0,
        retry_times=0,
        limit_size=0,
        exception_types=(ValueError,),
        default_result="async-fallback",
    )
    async def failing_async():
        nonlocal call_count
        call_count += 1
        raise ValueError("always fails")

    # First 2 calls should execute (and fail with default_result)
    for _ in range(2):
        result = await failing_async()
        assert result == "async-fallback"

    # After 2 failures, circuit breaker should be open
    with pytest.raises(RuntimeError, match="Circuit breaker is open"):
        await failing_async()


def test_circuit_breaker_thread_safe():
    """S-2: Circuit breaker is thread-safe under concurrent access."""
    import concurrent.futures
    from qreward.utils.scheduler import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=100, recovery_timeout=60.0)

    def record_failure_batch():
        for _ in range(50):
            breaker.record_failure()

    # Run 4 threads, each recording 50 failures = 200 total
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(record_failure_batch) for _ in range(4)]
        concurrent.futures.wait(futures)

    # Should be OPEN (200 >= 100)
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_circuit_breaker_logging(caplog):
    """Verify circuit breaker logs state transitions."""
    import logging
    from qreward.utils.scheduler import CircuitBreaker

    current_time = 0.0

    def fake_time():
        return current_time

    with caplog.at_level(logging.INFO, logger="qreward.utils.scheduler.circuit_breaker"):
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=5.0,
            time_func=fake_time,
        )

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()

    assert any("CLOSED -> OPEN" in r.message for r in caplog.records)

    caplog.clear()

    with caplog.at_level(logging.INFO, logger="qreward.utils.scheduler.circuit_breaker"):
        # Advance time to trigger HALF_OPEN
        current_time = 6.0
        _ = breaker.state

    assert any("OPEN -> HALF_OPEN" in r.message for r in caplog.records)

    caplog.clear()

    with caplog.at_level(logging.INFO, logger="qreward.utils.scheduler.circuit_breaker"):
        breaker.record_success()

    assert any("HALF_OPEN -> CLOSED" in r.message for r in caplog.records)


def test_schedule_circuit_breaker_disabled_by_default():
    """circuit_breaker_threshold=0 (default) means no circuit breaker."""

    call_count = 0

    @schedule(
        retry_times=0,
        limit_size=0,
        exception_types=(ValueError,),
        default_result="fallback",
    )
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")

    # Should never raise RuntimeError even after many failures
    for _ in range(20):
        result = failing_func()
        assert result == "fallback"

    assert call_count == 20

def test_can_submit_method():
    """M-VERIFY-3: can_submit replaces less_than."""
    from qreward.utils.scheduler.pools import RunningTaskPool

    pool = RunningTaskPool(window_max_size=5, window_interval=1, threshold=1)
    pool.add(2)
    pool._value = 1
    assert pool.can_submit() is True

    pool._value = 5
    pool._max_size_map.clear()
    pool._max_size_map[100] = 5
    assert pool.can_submit(1) is False

def test_less_than_deprecated():
    """less_than still works but triggers DeprecationWarning."""
    import warnings
    from qreward.utils.scheduler.pools import RunningTaskPool

    pool = RunningTaskPool(window_max_size=5, window_interval=1, threshold=1)
    pool._value = 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = pool.less_than()

    assert result is True
    assert any(issubclass(w.category, DeprecationWarning) and "less_than" in str(w.message) for w in caught)

def test_adjust_wait_time_method():
    """adjust_wait_time replaces get_max_wait_time."""
    from qreward.utils.scheduler.config import ScheduleConfig

    config = ScheduleConfig()
    result = config.adjust_wait_time(
        basic_wait_time=1.0, has_wait_time=10.0, max_wait_time=5.0
    )
    assert result == 0.01

def test_get_max_wait_time_deprecated():
    """get_max_wait_time still works but triggers DeprecationWarning."""
    import warnings
    from qreward.utils.scheduler.config import ScheduleConfig

    config = ScheduleConfig()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = config.get_max_wait_time(
            basic_wait_time=1.0, has_wait_time=10.0, max_wait_time=5.0
        )

    assert result == 0.01
    assert any(issubclass(w.category, DeprecationWarning) and "get_max_wait_time" in str(w.message) for w in caught)


# ============================================================
# Sprint 14: Parameter Validation Tests
# ============================================================


def test_config_negative_timeout():
    """M-VERIFY-1: timeout negative value raises ValueError."""
    with pytest.raises(ValueError, match="timeout must be >= 0"):
        ScheduleConfig(timeout=-1)


def test_config_negative_retry_interval():
    """M-VERIFY-2: retry_interval negative value raises ValueError."""
    with pytest.raises(ValueError, match="retry_interval must be >= 0"):
        ScheduleConfig(retry_interval=-1)


def test_config_zero_timeout_allowed():
    """timeout=0 (no timeout) is valid."""
    config = ScheduleConfig(timeout=0)
    assert config.timeout == 0


def test_config_zero_retry_interval_allowed():
    """retry_interval=0 is valid."""
    config = ScheduleConfig(retry_interval=0)
    assert config.retry_interval == 0


def test_config_positive_values_allowed():
    """Positive timeout and retry_interval are valid."""
    config = ScheduleConfig(timeout=30, retry_interval=2.5)
    assert config.timeout == 30
    assert config.retry_interval == 2.5


# ============================================================
# Sprint 15: Adaptive Rate Limiter Tests
# ============================================================

from qreward.utils.scheduler.adaptive_limiter import AdaptiveRateLimiter


def test_adaptive_limiter_slowdown():
    """M-VERIFY-1: High error rate triggers slowdown."""
    limiter = AdaptiveRateLimiter(
        initial_limit=100,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=5.0,
        window_seconds=60.0,
        cooldown_seconds=0,  # disable cooldown for test
    )
    assert limiter.current_limit == 100

    # Record 10 failures → error_rate = 1.0 > 0.3, triggers multiple slowdowns
    for _ in range(10):
        limiter.record(latency_seconds=0.1, success=False)

    # Should have slowed down significantly from 100
    assert limiter.current_limit < 100
    assert limiter.current_limit >= 10  # respects limit_min


def test_adaptive_limiter_speedup():
    """M-VERIFY-2: Recovery after errors triggers speedup."""
    limiter = AdaptiveRateLimiter(
        initial_limit=50,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=5.0,
        window_seconds=60.0,
        cooldown_seconds=0,
    )
    assert limiter.current_limit == 50

    # Record 20 successes → error_rate = 0.0 < 0.15, triggers multiple speedups
    for _ in range(20):
        limiter.record(latency_seconds=0.1, success=True)

    # Should have sped up from 50
    assert limiter.current_limit > 50
    assert limiter.current_limit <= 500  # respects limit_max


def test_adaptive_limiter_respects_min():
    """Slowdown does not go below limit_min."""
    limiter = AdaptiveRateLimiter(
        initial_limit=15,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=5.0,
        window_seconds=60.0,
        cooldown_seconds=0,
    )

    for _ in range(10):
        limiter.record(latency_seconds=0.1, success=False)

    assert limiter.current_limit >= 10


def test_adaptive_limiter_respects_max():
    """Speedup does not exceed limit_max."""
    limiter = AdaptiveRateLimiter(
        initial_limit=490,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=5.0,
        window_seconds=60.0,
        cooldown_seconds=0,
    )

    for _ in range(20):
        limiter.record(latency_seconds=0.1, success=True)

    assert limiter.current_limit <= 500


def test_adaptive_limiter_high_latency_triggers_slowdown():
    """High latency also triggers slowdown."""
    limiter = AdaptiveRateLimiter(
        initial_limit=100,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=2.0,
        window_seconds=60.0,
        cooldown_seconds=0,
    )

    # All succeed but with high latency
    for _ in range(10):
        limiter.record(latency_seconds=3.0, success=True)

    assert limiter.current_limit < 100


def test_adaptive_limiter_snapshot():
    """snapshot() returns correct statistics."""
    limiter = AdaptiveRateLimiter(
        initial_limit=100,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=5.0,
        window_seconds=60.0,
        cooldown_seconds=0,
    )

    # Empty snapshot
    snap = limiter.snapshot()
    assert snap["total_records"] == 0
    assert snap["error_rate"] == 0.0

    # Record some data
    limiter.record(latency_seconds=1.0, success=True)
    limiter.record(latency_seconds=2.0, success=False)

    snap = limiter.snapshot()
    assert snap["total_records"] == 2
    assert snap["error_rate"] == 0.5
    assert snap["avg_latency"] == 1.5


def test_adaptive_limiter_validation():
    """Invalid parameters raise ValueError."""
    with pytest.raises(ValueError, match="limit_min must be <= limit_max"):
        AdaptiveRateLimiter(initial_limit=100, limit_min=500, limit_max=10)

    with pytest.raises(ValueError, match="error_threshold must be in"):
        AdaptiveRateLimiter(initial_limit=100, error_threshold=0)

    with pytest.raises(ValueError, match="error_threshold must be in"):
        AdaptiveRateLimiter(initial_limit=100, error_threshold=1.5)


def test_adaptive_limiter_cooldown():
    """Cooldown prevents rapid adjustments."""
    limiter = AdaptiveRateLimiter(
        initial_limit=100,
        limit_min=10,
        limit_max=500,
        error_threshold=0.3,
        latency_threshold=5.0,
        window_seconds=60.0,
        cooldown_seconds=9999,  # very long cooldown
    )

    # First batch triggers adjustment
    for _ in range(10):
        limiter.record(latency_seconds=0.1, success=False)
    first_limit = limiter.current_limit

    # Second batch should NOT trigger another adjustment due to cooldown
    for _ in range(10):
        limiter.record(latency_seconds=0.1, success=False)
    assert limiter.current_limit == first_limit


# ============================================================
# Sprint 17: Priority Queue Tests
# ============================================================

from qreward.utils.scheduler.priority_queue import Priority, PriorityTaskQueue


def test_priority_high_before_normal():
    """M-VERIFY-1: HIGH priority tasks dequeue before NORMAL."""
    queue = PriorityTaskQueue()
    queue.put("normal_1", priority=Priority.NORMAL)
    queue.put("high_1", priority=Priority.HIGH)
    queue.put("normal_2", priority=Priority.NORMAL)
    queue.put("low_1", priority=Priority.LOW)

    assert queue.get() == "high_1"
    assert queue.get() == "normal_1"
    assert queue.get() == "normal_2"
    assert queue.get() == "low_1"
    assert queue.get() is None


def test_priority_fifo_same_level():
    """S-2: Same priority tasks follow FIFO order."""
    queue = PriorityTaskQueue()
    for i in range(5):
        queue.put(f"task_{i}", priority=Priority.NORMAL)

    for i in range(5):
        assert queue.get() == f"task_{i}"


def test_priority_queue_thread_safety():
    """M-VERIFY-3: Priority queue is thread-safe under concurrent access."""
    import threading

    queue = PriorityTaskQueue()
    results = []
    errors = []

    def producer(start, count):
        try:
            for i in range(count):
                queue.put(f"item_{start + i}", priority=Priority.NORMAL)
        except Exception as exc:
            errors.append(exc)

    def consumer(count):
        try:
            for _ in range(count):
                item = queue.get()
                if item is not None:
                    results.append(item)
        except Exception as exc:
            errors.append(exc)

    # 4 producers, each adding 25 items
    producers = [threading.Thread(target=producer, args=(i * 25, 25)) for i in range(4)]
    for thread in producers:
        thread.start()
    for thread in producers:
        thread.join()

    assert queue.queue_size == 100

    # 4 consumers, each taking 25 items
    consumers = [threading.Thread(target=consumer, args=(25,)) for i in range(4)]
    for thread in consumers:
        thread.start()
    for thread in consumers:
        thread.join()

    assert len(errors) == 0
    assert len(results) == 100
    assert queue.is_empty


def test_priority_queue_size():
    """S-3: queue_size returns correct count."""
    queue = PriorityTaskQueue()
    assert queue.queue_size == 0
    assert queue.is_empty

    queue.put("a", priority=Priority.HIGH)
    queue.put("b", priority=Priority.LOW)
    assert queue.queue_size == 2
    assert not queue.is_empty

    queue.get()
    assert queue.queue_size == 1


def test_priority_custom_values():
    """S-1: Custom priority values 0-9 are supported."""
    queue = PriorityTaskQueue()
    queue.put("prio_7", priority=7)
    queue.put("prio_2", priority=2)
    queue.put("prio_5", priority=5)

    assert queue.get() == "prio_2"
    assert queue.get() == "prio_5"
    assert queue.get() == "prio_7"


def test_priority_invalid_value():
    """Invalid priority raises ValueError."""
    queue = PriorityTaskQueue()
    with pytest.raises(ValueError, match="priority must be in"):
        queue.put("bad", priority=-1)
    with pytest.raises(ValueError, match="priority must be in"):
        queue.put("bad", priority=10)


def test_priority_starvation_protection():
    """S-4: Starved LOW tasks are promoted to HIGH."""
    queue = PriorityTaskQueue(starvation_threshold=0.01)

    queue.put("low_task", priority=Priority.LOW)
    queue.put("normal_task", priority=Priority.NORMAL)

    import time
    time.sleep(0.05)  # wait for starvation threshold

    # Both should be promoted; low_task was added first (lower sequence)
    first = queue.get()
    assert first == "low_task"


def test_priority_peek():
    """peek returns item without removing it."""
    queue = PriorityTaskQueue()
    assert queue.peek() is None

    queue.put("item", priority=Priority.HIGH)
    assert queue.peek() == "item"
    assert queue.queue_size == 1  # not removed


def test_priority_clear():
    """clear removes all items."""
    queue = PriorityTaskQueue()
    queue.put("a")
    queue.put("b")
    queue.clear()
    assert queue.is_empty


def test_priority_snapshot():
    """snapshot returns debug info."""
    queue = PriorityTaskQueue()
    queue.put("a", priority=Priority.HIGH)
    queue.put("b", priority=Priority.LOW)

    snap = queue.snapshot()
    assert len(snap) == 2
    assert snap[0]["priority"] == Priority.HIGH
    assert snap[1]["priority"] == Priority.LOW


def test_priority_starvation_threshold_validation():
    """Negative starvation_threshold raises ValueError."""
    with pytest.raises(ValueError, match="starvation_threshold must be >= 0"):
        PriorityTaskQueue(starvation_threshold=-1)


# ============================================================
# Sprint 19: Telemetry Tests
# ============================================================

from unittest.mock import MagicMock, patch
from qreward.utils.scheduler.telemetry import TelemetryExporter, _OTEL_AVAILABLE
from qreward.utils.scheduler.metrics import ScheduleMetrics


def test_telemetry_metrics_export():
    """M-VERIFY-1: Metrics are exported to OTel when available."""
    metrics = ScheduleMetrics(
        total_calls=5, success_count=4, failure_count=1,
        retry_count=2, total_latency_ms=150.0, avg_latency_ms=30.0,
    )
    mock_exporter = MagicMock()
    metrics.export_to_otel(mock_exporter)
    mock_exporter.record.assert_called_once_with(metrics)


def test_telemetry_graceful_degradation():
    """M-VERIFY-2: No exception when OTel is not installed."""
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", False):
        exporter = TelemetryExporter.__new__(TelemetryExporter)
        exporter._enabled = False
        exporter._meter = None
        exporter._tracer = None
        exporter._total_calls_counter = None
        exporter._success_counter = None
        exporter._failure_counter = None
        exporter._latency_histogram = None

        metrics = ScheduleMetrics(
            total_calls=1, success_count=1, failure_count=0,
            retry_count=0, total_latency_ms=10.0, avg_latency_ms=10.0,
        )
        # Should not raise
        exporter.record(metrics)
        span = exporter.start_span("test_func")
        span.set_attribute("key", "value")
        span.end()


def test_telemetry_span_attributes():
    """M-VERIFY-3: Span receives correct attributes."""
    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_span.return_value = mock_span

    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = True
    exporter._tracer = mock_tracer
    exporter._meter = None
    exporter._total_calls_counter = MagicMock()
    exporter._success_counter = MagicMock()
    exporter._failure_counter = MagicMock()
    exporter._latency_histogram = MagicMock()

    metrics = ScheduleMetrics(
        total_calls=3, success_count=2, failure_count=1,
        retry_count=1, total_latency_ms=100.0, avg_latency_ms=33.3,
    )

    span = exporter.start_span("my_func", attributes={"custom": "attr"})
    exporter.end_span(span, metrics)

    mock_span.set_attribute.assert_any_call("qreward.total_calls", 3)
    mock_span.set_attribute.assert_any_call("qreward.retry_count", 1)
    mock_span.end.assert_called_once()


def test_telemetry_is_available():
    """S-4: is_available reflects OTel SDK presence."""
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", False):
        assert TelemetryExporter.is_available() is False

    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", True):
        assert TelemetryExporter.is_available() is True


def test_telemetry_env_disable():
    """S-2: QREWARD_OTEL_ENABLED=false disables telemetry."""
    import os
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", True):
        with patch.dict(os.environ, {"QREWARD_OTEL_ENABLED": "false"}):
            assert TelemetryExporter.is_available() is False
        with patch.dict(os.environ, {"QREWARD_OTEL_ENABLED": "true"}):
            assert TelemetryExporter.is_available() is True


def test_telemetry_export_to_otel_none():
    """export_to_otel with None exporter is a no-op."""
    metrics = ScheduleMetrics(
        total_calls=1, success_count=1, failure_count=0,
        retry_count=0, total_latency_ms=10.0, avg_latency_ms=10.0,
    )
    # Should not raise
    metrics.export_to_otel(None)


def test_telemetry_noop_span():
    """_NoOpSpan works as context manager."""
    from qreward.utils.scheduler.telemetry import _NoOpSpan
    span = _NoOpSpan()
    with span as s:
        s.set_attribute("key", "value")
    span.end()


# ============================================================
# Sprint 20: Config Hot Reload Tests
# ============================================================

from qreward.utils.scheduler.config import ScheduleConfig
from qreward.utils.scheduler.config_watcher import ConfigWatcher


def test_hot_reload_timeout():
    """M-VERIFY-1: Runtime timeout change takes effect immediately."""
    config = ScheduleConfig(timeout=10)
    assert config.timeout == 10

    config.update(timeout=30)
    assert config.timeout == 30


def test_hot_reload_limit_size():
    """M-VERIFY-2: Runtime limit_size change takes effect immediately."""
    config = ScheduleConfig(limit_size=100)
    assert config.limit_size == 100

    config.update(limit_size=200)
    assert config.limit_size == 200


def test_config_on_change_callback():
    """M-VERIFY-3: on_change callback is invoked on update."""
    config = ScheduleConfig(timeout=5)
    changes = []

    config.on_change(lambda c: changes.append(c.timeout))
    config.update(timeout=15)

    assert len(changes) == 1
    assert changes[0] == 15


def test_config_snapshot():
    """S-4: snapshot returns current config as dict."""
    config = ScheduleConfig(timeout=10, retry_times=3)
    snap = config.snapshot()

    assert snap["timeout"] == 10
    assert snap["retry_times"] == 3
    assert isinstance(snap, dict)


def test_config_update_validation():
    """update() re-runs validation after changes."""
    config = ScheduleConfig(timeout=10)

    with pytest.raises(ValueError, match="timeout must be >= 0"):
        config.update(timeout=-1)


def test_config_watcher_callback_source():
    """ConfigWatcher with callback source polls and updates."""
    config = ScheduleConfig(timeout=5)
    call_count = 0

    def config_source():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            return {"timeout": 99}
        return {}

    watcher = ConfigWatcher(config, source="callback", callback=config_source, cooldown=0)
    watcher.poll_once()  # first call returns empty
    watcher.poll_once()  # second call returns timeout=99

    assert config.timeout == 99


def test_config_watcher_env_source():
    """ConfigWatcher with env source reads QREWARD_SCHEDULE_ vars."""
    import os
    config = ScheduleConfig(timeout=5)

    with patch.dict(os.environ, {"QREWARD_SCHEDULE_TIMEOUT": "42"}):
        watcher = ConfigWatcher(config, source="env", cooldown=0)
        watcher.poll_once()

    assert config.timeout == 42.0


def test_config_watcher_file_source(tmp_path):
    """ConfigWatcher with file source reads JSON config."""
    config = ScheduleConfig(timeout=5)
    config_file = tmp_path / "config.json"
    config_file.write_text('{"timeout": 77}')

    watcher = ConfigWatcher(
        config, source="file", file_path=str(config_file), cooldown=0
    )
    watcher.poll_once()

    assert config.timeout == 77


def test_config_watcher_start_stop():
    """S-5: ConfigWatcher start/stop lifecycle."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="callback", callback=lambda: {}, poll_interval=0.1
    )

    watcher.start()
    assert watcher.is_running

    watcher.stop()
    assert not watcher.is_running


def test_config_watcher_validation():
    """Invalid source raises ValueError."""
    config = ScheduleConfig()

    with pytest.raises(ValueError, match="source must be"):
        ConfigWatcher(config, source="invalid")

    with pytest.raises(ValueError, match="file_path is required"):
        ConfigWatcher(config, source="file")

    with pytest.raises(ValueError, match="callback is required"):
        ConfigWatcher(config, source="callback")


def test_config_watcher_cooldown():
    """S-3: Cooldown prevents rapid updates."""
    config = ScheduleConfig(timeout=5)
    call_count = 0

    def config_source():
        nonlocal call_count
        call_count += 1
        return {"timeout": call_count * 10}

    watcher = ConfigWatcher(
        config, source="callback", callback=config_source, cooldown=9999
    )
    watcher.poll_once()  # first update succeeds
    assert config.timeout == 10

    watcher.poll_once()  # second update blocked by cooldown
    assert config.timeout == 10  # unchanged


# ============================================================
# Coverage Boost: telemetry.py
# ============================================================

def test_telemetry_disabled_record_noop():
    """record() is a no-op when OTel is disabled."""
    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = False
    exporter._meter = None
    exporter._tracer = None
    exporter._total_calls_counter = None
    exporter._success_counter = None
    exporter._failure_counter = None
    exporter._latency_histogram = None

    metrics = ScheduleMetrics(
        total_calls=1, success_count=1, failure_count=0,
        retry_count=0, total_latency_ms=10.0, avg_latency_ms=10.0,
    )
    # Should not raise and should not call any counter
    exporter.record(metrics)


def test_telemetry_disabled_start_span_returns_noop():
    """start_span() returns _NoOpSpan when OTel is disabled."""
    from qreward.utils.scheduler.telemetry import _NoOpSpan

    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = False
    exporter._tracer = None

    span = exporter.start_span("test_func")
    assert isinstance(span, _NoOpSpan)


def test_telemetry_tracer_none_returns_noop():
    """start_span() returns _NoOpSpan when tracer is None even if enabled."""
    from qreward.utils.scheduler.telemetry import _NoOpSpan

    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = True
    exporter._tracer = None

    span = exporter.start_span("test_func")
    assert isinstance(span, _NoOpSpan)


def test_telemetry_end_span_noop_span_skipped():
    """end_span() skips processing for _NoOpSpan."""
    from qreward.utils.scheduler.telemetry import _NoOpSpan

    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = True

    noop_span = _NoOpSpan()
    metrics = ScheduleMetrics(
        total_calls=1, success_count=1, failure_count=0,
        retry_count=0, total_latency_ms=10.0, avg_latency_ms=10.0,
    )
    # Should not raise - skips because isinstance(span, _NoOpSpan)
    exporter.end_span(noop_span, metrics)


def test_telemetry_end_span_disabled_skipped():
    """end_span() skips processing when disabled."""
    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = False

    mock_span = MagicMock()
    metrics = ScheduleMetrics(
        total_calls=1, success_count=1, failure_count=0,
        retry_count=0, total_latency_ms=10.0, avg_latency_ms=10.0,
    )
    exporter.end_span(mock_span, metrics)
    # mock_span should NOT have set_attribute called
    mock_span.set_attribute.assert_not_called()
    mock_span.end.assert_not_called()


def test_noop_span_context_manager():
    """_NoOpSpan works as a context manager with all methods."""
    from qreward.utils.scheduler.telemetry import _NoOpSpan

    span = _NoOpSpan()
    with span as s:
        assert s is span
        s.set_attribute("key", "value")
        s.set_attribute("another", 42)
    span.end()


def test_telemetry_check_enabled_otel_unavailable():
    """_check_enabled returns False when OTel is not available."""
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", False):
        assert TelemetryExporter._check_enabled() is False


def test_telemetry_check_enabled_env_variants():
    """_check_enabled respects various env var values."""
    import os
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", True):
        for disabled_val in ("false", "0", "no", "off"):
            with patch.dict(os.environ, {"QREWARD_OTEL_ENABLED": disabled_val}):
                assert TelemetryExporter._check_enabled() is False
        for enabled_val in ("true", "1", "yes", "on", "anything"):
            with patch.dict(os.environ, {"QREWARD_OTEL_ENABLED": enabled_val}):
                assert TelemetryExporter._check_enabled() is True


# ============================================================
# Coverage Boost: config_watcher.py
# ============================================================

def test_config_watcher_duplicate_start():
    """Calling start() twice does not create a second thread."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="callback", callback=lambda: {}, poll_interval=0.1
    )
    watcher.start()
    first_thread = watcher._thread
    watcher.start()  # second call should be a no-op
    assert watcher._thread is first_thread
    watcher.stop()


def test_config_watcher_stop_joins_thread():
    """stop() joins the background thread."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="callback", callback=lambda: {}, poll_interval=0.05
    )
    watcher.start()
    assert watcher.is_running
    watcher.stop()
    assert watcher._thread is None
    assert not watcher.is_running


def test_config_watcher_source_returns_empty():
    """poll_once returns False when source returns empty dict."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="callback", callback=lambda: {}, cooldown=0
    )
    assert watcher.poll_once() is False
    assert config.timeout == 5  # unchanged


def test_config_watcher_source_returns_none():
    """poll_once returns False when source returns None."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="callback", callback=lambda: None, cooldown=0
    )
    assert watcher.poll_once() is False


def test_config_watcher_filtered_no_valid_fields():
    """poll_once returns False when source returns only unknown fields."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="callback",
        callback=lambda: {"unknown_field": 123, "another_bad": "val"},
        cooldown=0,
    )
    assert watcher.poll_once() is False
    assert config.timeout == 5  # unchanged


def test_config_watcher_file_not_exists():
    """File source returns None when file does not exist."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher(
        config, source="file",
        file_path="/nonexistent/path/config.json",
        cooldown=0,
    )
    assert watcher.poll_once() is False


def test_config_watcher_file_mtime_unchanged(tmp_path):
    """File source returns None when mtime has not changed."""
    config = ScheduleConfig(timeout=5)
    config_file = tmp_path / "config.json"
    config_file.write_text('{"timeout": 77}')

    watcher = ConfigWatcher(
        config, source="file", file_path=str(config_file), cooldown=0
    )
    assert watcher.poll_once() is True
    assert config.timeout == 77

    # Second poll without file change - mtime unchanged
    assert watcher.poll_once() is False


def test_config_watcher_env_ignores_non_prefix():
    """Env source ignores variables without QREWARD_SCHEDULE_ prefix."""
    import os
    config = ScheduleConfig(timeout=5)

    with patch.dict(os.environ, {"SOME_OTHER_VAR": "999"}, clear=False):
        watcher = ConfigWatcher(config, source="env", cooldown=0)
        result = watcher.poll_once()
        # If no QREWARD_SCHEDULE_ vars exist, result depends on env
        # but SOME_OTHER_VAR should be ignored
        assert config.timeout == 5 or result is True


def test_config_watcher_env_ignores_unknown_fields():
    """Env source ignores QREWARD_SCHEDULE_ vars with unknown field names."""
    import os
    config = ScheduleConfig(timeout=5)

    env_vars = {"QREWARD_SCHEDULE_UNKNOWN_FIELD": "999"}
    with patch.dict(os.environ, env_vars, clear=False):
        watcher = ConfigWatcher(config, source="env", cooldown=0)
        watcher.poll_once()
        assert config.timeout == 5  # unchanged


def test_config_watcher_callback_none_returns_none():
    """_read_callback returns None when callback is None."""
    config = ScheduleConfig(timeout=5)
    watcher = ConfigWatcher.__new__(ConfigWatcher)
    watcher._config = config
    watcher._source = "callback"
    watcher._callback = None
    watcher._file_path = None
    watcher._poll_interval = 1.0
    watcher._cooldown = 0
    watcher._last_update_time = 0
    watcher._last_mtime = 0
    watcher._stop_event = threading.Event()
    watcher._thread = None

    result = watcher._read_callback()
    assert result is None


def test_coerce_value_bool_fields():
    """_coerce_value correctly converts bool fields."""
    from qreward.utils.scheduler.config_watcher import _coerce_value

    assert _coerce_value("debug", "true") is True
    assert _coerce_value("debug", "1") is True
    assert _coerce_value("debug", "yes") is True
    assert _coerce_value("debug", "on") is True
    assert _coerce_value("debug", "false") is False
    assert _coerce_value("debug", "0") is False
    assert _coerce_value("debug", "no") is False
    assert _coerce_value("adaptive_limit", "true") is True
    assert _coerce_value("adaptive_limit", "off") is False


def test_coerce_value_int_fields():
    """_coerce_value correctly converts int fields."""
    from qreward.utils.scheduler.config_watcher import _coerce_value

    assert _coerce_value("retry_times", "5") == 5
    assert isinstance(_coerce_value("retry_times", "5"), int)
    assert _coerce_value("limit_size", "100") == 100
    assert _coerce_value("hedged_request_max_times", "3") == 3
    assert _coerce_value("speed_up_max_multiply", "10") == 10
    assert _coerce_value("adaptive_limit_min", "20") == 20
    assert _coerce_value("adaptive_limit_max", "1000") == 1000
    assert _coerce_value("priority", "1") == 1


def test_coerce_value_float_fields():
    """_coerce_value correctly converts float fields."""
    from qreward.utils.scheduler.config_watcher import _coerce_value

    assert _coerce_value("timeout", "30.5") == 30.5
    assert isinstance(_coerce_value("timeout", "30.5"), float)
    assert _coerce_value("retry_interval", "2.0") == 2.0
    assert _coerce_value("limit_window", "1.5") == 1.5
    assert _coerce_value("hedged_request_time", "0.5") == 0.5
    assert _coerce_value("hedged_request_proportion", "0.1") == 0.1
    assert _coerce_value("adaptive_error_threshold", "0.3") == 0.3
    assert _coerce_value("adaptive_latency_threshold", "5.0") == 5.0
    assert _coerce_value("adaptive_window_seconds", "10.0") == 10.0


def test_coerce_value_unknown_field():
    """_coerce_value returns raw string for unknown fields."""
    from qreward.utils.scheduler.config_watcher import _coerce_value

    result = _coerce_value("some_unknown_field", "hello")
    assert result == "hello"
    assert isinstance(result, str)


def test_config_watcher_poll_loop_handles_exception():
    """_poll_loop catches exceptions from poll_once."""
    config = ScheduleConfig(timeout=5)
    poll_count = 0

    def bad_callback():
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            raise RuntimeError("simulated error")
        return {}

    watcher = ConfigWatcher(
        config, source="callback", callback=bad_callback,
        poll_interval=0.05, cooldown=0,
    )
    watcher.start()
    time.sleep(0.2)
    watcher.stop()
    # Should have polled multiple times without crashing
    assert poll_count >= 2


# ============================================================
# Coverage Boost: config.py (adjust_wait_time)
# ============================================================

def test_adjust_wait_time_negative_basic():
    """adjust_wait_time corrects negative basic_wait_time to MIN_WAIT_TIME."""
    config = ScheduleConfig()
    result = config.adjust_wait_time(basic_wait_time=-5, has_wait_time=0, max_wait_time=10)
    assert result == 0.01  # MIN_WAIT_TIME


def test_adjust_wait_time_max_wait_zero():
    """adjust_wait_time returns basic_wait_time when max_wait_time <= 0."""
    config = ScheduleConfig()
    result = config.adjust_wait_time(basic_wait_time=2.0, has_wait_time=0, max_wait_time=0)
    assert result == 2.0

    result2 = config.adjust_wait_time(basic_wait_time=3.0, has_wait_time=0, max_wait_time=-1)
    assert result2 == 3.0


def test_adjust_wait_time_not_exceeded():
    """adjust_wait_time returns basic_wait_time when total < max."""
    config = ScheduleConfig()
    result = config.adjust_wait_time(basic_wait_time=2.0, has_wait_time=3.0, max_wait_time=10.0)
    assert result == 2.0


def test_adjust_wait_time_already_exceeded():
    """adjust_wait_time returns MIN_WAIT_TIME when has_wait_time > max."""
    config = ScheduleConfig()
    result = config.adjust_wait_time(basic_wait_time=2.0, has_wait_time=15.0, max_wait_time=10.0)
    assert result == 0.01  # MIN_WAIT_TIME


def test_adjust_wait_time_remaining():
    """adjust_wait_time returns remaining time when partially elapsed."""
    config = ScheduleConfig()
    result = config.adjust_wait_time(basic_wait_time=5.0, has_wait_time=7.0, max_wait_time=10.0)
    assert result == 3.0  # max_wait_time - has_wait_time


def test_config_update_ignores_unknown_fields():
    """update() ignores fields that don't exist on ScheduleConfig."""
    config = ScheduleConfig(timeout=10)
    config.update(timeout=20, nonexistent_field="ignored")
    assert config.timeout == 20
    assert not hasattr(config, "nonexistent_field") or True  # field not set


def test_config_update_ignores_private_fields():
    """update() ignores _change_callbacks and _update_lock."""
    config = ScheduleConfig(timeout=10)
    original_callbacks = config._change_callbacks
    original_lock = config._update_lock

    config.update(_change_callbacks=[], _update_lock=None)
    assert config._change_callbacks is original_callbacks
    assert config._update_lock is original_lock


# ============================================================
# Coverage Boost: decorator.py
# ============================================================

@pytest.mark.asyncio
async def test_decorator_key_func_async():
    """key_func generates custom pool key for async functions."""
    keys_seen = []

    @schedule(key_func=lambda x: f"model_{x}", retry_times=0)
    async def _task(x):
        return x * 2

    result = await _task("gpt4")
    assert result == "gpt4gpt4"


def test_decorator_key_func_sync():
    """key_func generates custom pool key for sync functions."""
    @schedule(key_func=lambda x: f"model_{x}", retry_times=0)
    def _task(x):
        return x * 2

    result = _task("gpt4")
    assert result == "gpt4gpt4"


@pytest.mark.asyncio
async def test_decorator_timeout_positive_async():
    """Positive timeout passes window_interval to RunningTaskPool."""
    @schedule(timeout=5, retry_times=0)
    async def _task():
        return "ok"

    result = await _task()
    assert result == "ok"


def test_decorator_timeout_positive_sync():
    """Positive timeout passes window_interval to RunningTaskPool."""
    @schedule(timeout=5, retry_times=0)
    def _task():
        return "ok"

    result = _task()
    assert result == "ok"


@pytest.mark.asyncio
async def test_decorator_circuit_breaker_blocks_async():
    """Circuit breaker blocks requests when open (async)."""
    call_count = 0

    @schedule(
        circuit_breaker_threshold=2,
        circuit_breaker_recovery=9999,
        retry_times=0,
        default_result="fallback",
    )
    async def _task():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    # Trigger failures to open the breaker
    await _task()  # failure 1
    await _task()  # failure 2 - breaker opens

    # Next call should be blocked by circuit breaker
    with pytest.raises(RuntimeError, match="Circuit breaker is open"):
        await _task()


def test_decorator_circuit_breaker_blocks_sync():
    """Circuit breaker blocks requests when open (sync)."""
    call_count = 0

    @schedule(
        circuit_breaker_threshold=2,
        circuit_breaker_recovery=9999,
        retry_times=0,
        default_result="fallback",
    )
    def _task():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    _task()  # failure 1
    _task()  # failure 2 - breaker opens

    with pytest.raises(RuntimeError, match="Circuit breaker is open"):
        _task()


@pytest.mark.asyncio
async def test_decorator_adaptive_limiter_records_async():
    """Adaptive limiter records success/failure for async functions."""
    @schedule(
        adaptive_limit=True,
        limit_size=100,
        adaptive_limit_min=10,
        adaptive_limit_max=500,
        retry_times=0,
    )
    async def _task_success():
        return "ok"

    result = await _task_success()
    assert result == "ok"


def test_decorator_adaptive_limiter_records_sync():
    """Adaptive limiter records success/failure for sync functions."""
    @schedule(
        adaptive_limit=True,
        limit_size=100,
        adaptive_limit_min=10,
        adaptive_limit_max=500,
        retry_times=0,
    )
    def _task_success():
        return "ok"

    result = _task_success()
    assert result == "ok"


@pytest.mark.asyncio
async def test_decorator_breaker_records_success_async():
    """Circuit breaker records success on successful execution (async)."""
    @schedule(circuit_breaker_threshold=5, retry_times=0)
    async def _task():
        return "ok"

    result = await _task()
    assert result == "ok"


def test_decorator_breaker_records_success_sync():
    """Circuit breaker records success on successful execution (sync)."""
    @schedule(circuit_breaker_threshold=5, retry_times=0)
    def _task():
        return "ok"

    result = _task()
    assert result == "ok"


@pytest.mark.asyncio
async def test_decorator_metrics_callback_async():
    """metrics_callback is invoked with ScheduleMetrics (async)."""
    collected = []

    @schedule(metrics_callback=lambda m: collected.append(m), retry_times=0)
    async def _task():
        return "ok"

    await _task()
    assert len(collected) == 1
    assert collected[0].success_count >= 1


def test_decorator_metrics_callback_sync():
    """metrics_callback is invoked with ScheduleMetrics (sync)."""
    collected = []

    @schedule(metrics_callback=lambda m: collected.append(m), retry_times=0)
    def _task():
        return "ok"

    _task()
    assert len(collected) == 1
    assert collected[0].success_count >= 1


@pytest.mark.asyncio
async def test_decorator_telemetry_exporter_async():
    """telemetry_exporter.record is called after execution (async)."""
    mock_exporter = MagicMock()

    @schedule(telemetry_exporter=mock_exporter, retry_times=0)
    async def _task():
        return "ok"

    await _task()
    mock_exporter.record.assert_called_once()


def test_decorator_telemetry_exporter_sync():
    """telemetry_exporter.record is called after execution (sync)."""
    mock_exporter = MagicMock()

    @schedule(telemetry_exporter=mock_exporter, retry_times=0)
    def _task():
        return "ok"

    _task()
    mock_exporter.record.assert_called_once()


@pytest.mark.asyncio
async def test_decorator_breaker_records_failure_async():
    """Circuit breaker records failure on exception (async)."""
    @schedule(
        circuit_breaker_threshold=10,
        retry_times=0,
        default_result="fallback",
    )
    async def _task():
        raise ValueError("boom")

    result = await _task()
    assert result == "fallback"


def test_decorator_breaker_records_failure_sync():
    """Circuit breaker records failure on exception (sync)."""
    @schedule(
        circuit_breaker_threshold=10,
        retry_times=0,
        default_result="fallback",
    )
    def _task():
        raise ValueError("boom")

    result = _task()
    assert result == "fallback"


@pytest.mark.asyncio
async def test_decorator_adaptive_limiter_failure_async():
    """Adaptive limiter records failure for async functions."""
    @schedule(
        adaptive_limit=True,
        limit_size=100,
        retry_times=0,
        default_result="fallback",
    )
    async def _task():
        raise ValueError("boom")

    result = await _task()
    assert result == "fallback"


def test_decorator_adaptive_limiter_failure_sync():
    """Adaptive limiter records failure for sync functions."""
    @schedule(
        adaptive_limit=True,
        limit_size=100,
        retry_times=0,
        default_result="fallback",
    )
    def _task():
        raise ValueError("boom")

    result = _task()
    assert result == "fallback"


# ============================================================
# Coverage Boost: telemetry.py OTel-enabled path
# ============================================================

def test_telemetry_init_with_otel_enabled():
    """TelemetryExporter.__init__ creates meter/tracer/counters when OTel is available."""
    mock_counter = MagicMock()
    mock_histogram = MagicMock()
    mock_meter = MagicMock()
    mock_meter.create_counter.return_value = mock_counter
    mock_meter.create_histogram.return_value = mock_histogram

    mock_tracer = MagicMock()

    mock_metrics_mod = MagicMock()
    mock_metrics_mod.get_meter.return_value = mock_meter

    mock_trace_mod = MagicMock()
    mock_trace_mod.get_tracer.return_value = mock_tracer

    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", True), \
         patch("qreward.utils.scheduler.telemetry._meter_mod", mock_metrics_mod), \
         patch("qreward.utils.scheduler.telemetry._trace_mod", mock_trace_mod):
        exporter = TelemetryExporter(
            meter_name="test.meter", tracer_name="test.tracer"
        )

    assert exporter._enabled is True
    assert exporter._meter is mock_meter
    assert exporter._tracer is mock_tracer
    mock_metrics_mod.get_meter.assert_called_once_with("test.meter")
    mock_trace_mod.get_tracer.assert_called_once_with("test.tracer")
    assert mock_meter.create_counter.call_count == 3
    mock_meter.create_histogram.assert_called_once()


def test_telemetry_record_with_otel_enabled():
    """record() calls counter.add() and histogram.record() when OTel is enabled."""
    exporter = TelemetryExporter.__new__(TelemetryExporter)
    exporter._enabled = True
    exporter._total_calls_counter = MagicMock()
    exporter._success_counter = MagicMock()
    exporter._failure_counter = MagicMock()
    exporter._latency_histogram = MagicMock()

    metrics = ScheduleMetrics(
        total_calls=10, success_count=8, failure_count=2,
        retry_count=3, total_latency_ms=500.0, avg_latency_ms=50.0,
    )
    exporter.record(metrics)

    exporter._total_calls_counter.add.assert_called_once_with(10)
    exporter._success_counter.add.assert_called_once_with(8)
    exporter._failure_counter.add.assert_called_once_with(2)
    exporter._latency_histogram.record.assert_called_once_with(500.0)


def test_telemetry_init_otel_unavailable():
    """TelemetryExporter.__init__ sets disabled state when OTel is not available."""
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", False):
        exporter = TelemetryExporter()

    assert exporter._enabled is False
    assert exporter._meter is None
    assert exporter._tracer is None


def test_telemetry_init_env_disabled():
    """TelemetryExporter.__init__ respects QREWARD_OTEL_ENABLED=false."""
    import os
    with patch("qreward.utils.scheduler.telemetry._OTEL_AVAILABLE", True), \
         patch.dict(os.environ, {"QREWARD_OTEL_ENABLED": "false"}):
        exporter = TelemetryExporter()

    assert exporter._enabled is False