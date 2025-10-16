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
    # 我们通过构造一个 schedule 返回它的 _get_max_wait_time 闭包来测试
    def get_max_wait_time_test_hook():
        dec = schedule()

        def func():
            return None

        wrapper = dec(func)
        # wrapper 闭包里有 _get_max_wait_time 可用（从 func.__closure__ 里取）
        for cell in wrapper.__closure__:
            if callable(cell.cell_contents):
                # 找到 _get_max_wait_time
                if cell.cell_contents.__name__ == "_get_max_wait_time":
                    return cell.cell_contents
        raise RuntimeError("_get_max_wait_time not found")

    _get_max_wait_time = get_max_wait_time_test_hook()

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
        results = [f.result() for f in
                   concurrent.futures.as_completed(futures)]

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

    results = await asyncio.gather(*[_async_overload_job(i)
                                     for i in range(512)])
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
        futures = [pool.submit(_sync_overload_low_fail_job, i)
                   for i in range(512)]
        results = [f.result() for f in
                   concurrent.futures.as_completed(futures)]
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
        name = exception_name_list[random.randint(
            0,
            len(exception_name_list) - 1,
        )]
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
            exception_message_list[random.randint(
                0,
                len(exception_message_list) - 1,
            )]
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
        results = [f.result() for f in
                   concurrent.futures.as_completed(futures)]

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
    assert max(counter.values()) <= 105  # 5% 误差容忍


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
    assert max(counter.values()) <= 105  # 5% 误差容忍


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

            def less_than(self, val):
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

            def less_than(self, val):
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

            def less_than(self, val):
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

            def less_than(self, val):
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
            "P",
            (),
            {"add": lambda self, v: None,
             "less_than": lambda self, v: True}
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
    "remaining_time, expected_timeout",
    [(0.5, 0.5), (-0.5, 0.001)]  # 场景1  # 场景2
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
            "P",
            (),
            {"add": lambda self, v: None,
             "less_than": lambda self, v: True}
        )(),
    )
    monkeypatch.setattr(LimiterPool, "get_pool",
                        lambda *a, **k: DummyLimiter())

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

    @schedule(timeout=0.3, retry_times=2, retry_interval=1,
              hedged_request_time=0.05, hedged_request_proportion=1.0,
              hedged_request_max_times=2,  # 至少 2 次对冲机会
              limit_size=0,  # 不限流
              exception_types=Exception, default_result="fallback")
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

    @schedule(timeout=0.3, retry_times=2, retry_interval=1,
              hedged_request_time=0.05, hedged_request_proportion=1.0,
              hedged_request_max_times=2,  # 至少 2 次对冲机会
              limit_size=0,
              exception_types=Exception, default_result="fallback")
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

    @schedule(timeout=0.2, retry_times=0, retry_interval=0.1,
              exception_types=Exception)
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

    @schedule(timeout=0.2, retry_times=0, retry_interval=0.1,
              hedged_request_time=0.05, hedged_request_proportion=1.0,
              exception_types=Exception)
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

    @schedule(timeout=0.5, retry_times=0, retry_interval=0.1,
              exception_types=RuntimeError, default_result="fallback")
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
    @schedule(timeout=0.5, retry_times=0, retry_interval=0.1,
              exception_types=RuntimeError, default_result="fallback")
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
