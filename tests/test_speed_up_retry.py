import asyncio
import concurrent.futures
import random
import time

import pytest

from qreward.utils import speed_up_retry


# ---------- 1. 默认值兜底 ----------
@pytest.mark.asyncio
async def test_default_value():
    @speed_up_retry(debug=True, default_result=5)
    async def _fail():
        raise TimeoutError("timeout")

    assert await _fail() == 5


# ---------- 2. 时间加速 ----------
@pytest.mark.asyncio
async def test_speed_up_time():
    start = time.perf_counter()
    calls = 0

    @speed_up_retry(debug=True, retry_times=5, hedged_request_time=1.5)
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
    assert 3 <= elapsed < 3.1


# ---------- 3. 超时异常 ----------
@pytest.mark.asyncio
async def test_timeout():
    @speed_up_retry(debug=True, retry_times=5, timeout=3)
    async def _sleep():
        await asyncio.sleep(2.5)
        raise BaseException("test")

    t0 = time.perf_counter()
    with pytest.raises(asyncio.TimeoutError):
        await _sleep()
    assert 3 <= time.perf_counter() - t0 < 3.1


# ---------- 4. 同步函数 + 线程池 ----------
def test_sync_func():
    @speed_up_retry(debug=True, retry_times=5, default_result=0)
    def _sync_job(n: int) -> int:
        time.sleep(0.1)
        if n % 10 == 0 and random.randint(0, 10_000) < 8_500:
            raise BaseException("test")
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        futures = [pool.submit(_sync_job, i) for i in range(128)]
        results = [
            f.result() for f in concurrent.futures.as_completed(futures)
        ]

    assert len(results) == 128


# ---------- 5. 异步函数 + gather ----------
@pytest.mark.asyncio
async def test_async_func():
    @speed_up_retry(debug=True, retry_times=5, default_result=0)
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

    @speed_up_retry(
        debug=True, retry_times=20, hedged_request_time=20, default_result=0
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

    results = await asyncio.gather(
        *[_async_overload_job(i) for i in range(512)]
    )
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

    @speed_up_retry(
        debug=True, retry_times=20, hedged_request_time=20, default_result=0
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

    @speed_up_retry(
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
        futures = [
            pool.submit(_sync_overload_low_fail_job, i) for i in range(512)
        ]
        results = [
            f.result() for f in concurrent.futures.as_completed(futures)
        ]
    print(overload_size)
    print(total_size)
    assert overload_size < 50
    assert total_size < 650
    assert len(results) == 512


# ---------- 9. 异步各类熔断异常 + gather ----------
@pytest.mark.asyncio
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
            random.randint(0, len(exception_name_list) - 1)
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
                random.randint(0, len(exception_message_list) - 1)
            ]
        )
        return e

    @speed_up_retry(
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
    @speed_up_retry(debug=True, retry_times=5, default_result=0)
    def _sync_job(n: int) -> int:
        time.sleep(3)
        if random.randint(0, 10000) < 5000:
            raise BaseException("test")
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        futures = [
            pool.submit(_sync_job, i) for i in range(128)
        ]
        results = [
            f.result() for f in concurrent.futures.as_completed(futures)
        ]

    assert len(results) == 128
