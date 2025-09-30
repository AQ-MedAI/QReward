import asyncio
import concurrent.futures
import functools
import inspect
import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from http import HTTPStatus
from typing import (
    Any,
    List,
    Type,
    Tuple,
    Union,
    Optional,
    Iterable,
    Sequence,
)

from qreward.globals import (
    LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING,
    OVERLOAD_EXCEPTIONS,
    OVERLOAD_KEYWORDS,
    SYSTEM_OVERLOAD_INDICATORS,
)
from qreward.types import RetryPredicate


def retry(
    *,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on: Union[
        type[Exception],
        Iterable[type[Exception]],
        RetryPredicate,
    ] = Exception,
    check_exception: RetryPredicate | None = None,
):
    """重试装饰器, 支持同步和异步函数。

    参数:
        max_retries: 最大重试次数(不包括首次调用)
        delay: 初始延迟时间(单位: 秒)
        backoff_factor: 指数退避因子
        jitter: 是否添加随机抖动(0~1倍delay的随机值)
        retry_on: 指定要重试的异常类型或异常判断函数
        check_exception: 自定义异常判断函数, 接收异常实例, 返回是否重试

    示例:
        @retry(
            max_retries=3,
            delay=0.1,
            retry_on=(ValueError, ConnectionError),
        )
        async def fetch_data():
            ...

        @retry(check_exception=lambda e: isinstance(e, ValueError)
            and "retry" in str(e))
        def unreliable_func():
            ...
    """

    def should_retry(exception: Exception) -> bool:
        # 检查 retry_on
        if callable(retry_on):
            if not retry_on(exception):
                return False
        elif not isinstance(exception,
                            tuple(retry_on)
                            if isinstance(retry_on, (list, tuple))
                            else (retry_on,)):
            return False

        # 检查 check_exception
        if check_exception is not None:
            return check_exception(exception)

        return True

    def exponential_backoff(attempt: int) -> float:
        # 计算指数退避时间
        exp_delay = delay * (backoff_factor ** (attempt - 1))
        if jitter:
            exp_delay += random.uniform(0, delay)
        return exp_delay

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        is_coroutine = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 2):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt >= max_retries + 1 or not should_retry(e):
                        break
                    wait_time = exponential_backoff(attempt)
                    await asyncio.sleep(wait_time)
            raise last_exc

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 2):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt >= max_retries + 1 or not should_retry(e):
                        break
                    wait_time = exponential_backoff(attempt)
                    time.sleep(wait_time)
            raise last_exc

        # 根据函数类型返回对应的包装器
        return async_wrapper if is_coroutine else sync_wrapper

    return decorator


class RunningTaskPool:
    global_lock = threading.Lock()
    global_task_pool = dict()

    @classmethod
    def get_pool(cls, func_name: str, *args, **kwargs):
        with cls.global_lock:
            if func_name not in cls.global_task_pool:
                cls.global_task_pool[func_name] = cls(*args, **kwargs)
            return cls.global_task_pool[func_name]

    def __init__(
        self,
        window_max_size: int = 12,
        window_interval: int = 60,
        threshold: int = 3,
    ):
        """
        初始化 RunningTaskPool 对象

        Args:
            window_max_size: 窗口最大大小
            window_interval: 窗口间隔时间，单位秒
            threshold: 阈值
        """
        self._value = 0
        self._max_size_map = OrderedDict()
        self._window_max_size = window_max_size
        self._window_interval = window_interval
        self._threshold = threshold
        self._lock = threading.Lock()

    def add(self, value: int = 1) -> int:
        with self._lock:
            self._value += value
            key = int(time.time()) // self._window_interval
            if key in self._max_size_map:
                if self._max_size_map[key] < self._value:
                    self._max_size_map[key] = self._value
            else:
                while len(self._max_size_map) >= self._window_max_size:
                    self._max_size_map.popitem(last=False)
                self._max_size_map[key] = self._value
            return self._value

    def less_than(self, multiply: float = 1) -> bool:
        with self._lock:
            if self._value < self._threshold:
                return True
            max_value = 0
            for v in self._max_size_map.values():
                if v > max_value:
                    max_value = v
            if max_value > self._value * multiply:
                return True
            return False


# 异步任务取消异常组
_CancelledErrorGroups = (
    asyncio.CancelledError,
    concurrent.futures.CancelledError,
    TimeoutError,
)


async def _cancel_async_task(
    pending: Sequence[asyncio.Task],
    done: List[asyncio.Task],
    retry_interval: Optional[float],
):
    """
    取消剩余异步任务

    Args:
        pending: 未完成的异步任务列表
        done: 已完成的异步任务列表
        retry_interval: 重试间隔时间，单位秒
    """
    while len(done) > 0:
        try:
            _ = done.pop()
        except _CancelledErrorGroups:
            pass
    if len(pending) > 0:
        for task in pending:
            if not task.done():
                task.cancel()
        try:
            await asyncio.wait_for(
                fut=asyncio.gather(*pending, return_exceptions=True),
                timeout=retry_interval,
            )
        except _CancelledErrorGroups:
            pass


def _cancel_sync_task(
    not_done: Sequence[concurrent.futures.Future],
    done: List,
    retry_interval: Optional[float],
):
    """
    取消剩余同步任务

    Args:
        not_done: 未完成的异步任务列表
        done: 已完成的异步任务列表
        retry_interval: 重试间隔时间，单位秒
    """
    while len(done) > 0:
        try:
            _ = done.pop()
        except _CancelledErrorGroups:
            pass
    for task in not_done:
        if not task.done():
            task.cancel()
    if len(not_done) > 0:
        try:
            concurrent.futures.wait(
                not_done,
                timeout=retry_interval,
                return_when=concurrent.futures.ALL_COMPLETED,
            )
        except _CancelledErrorGroups:
            pass


def _overload_check(exception: BaseException) -> bool:
    """
    判断服务端是否过载的函数

    Args:
        exception: 异常对象

    Returns:
        bool: True表示服务端过载，False表示不是过载
    """

    # 1. HTTP状态码相关过载判断
    if hasattr(exception, "status_code"):
        status_code = exception.status_code
        # 503 Service Unavailable - 服务不可用，典型过载表现
        # 429 Too Many Requests - 请求过多，限流
        # 502 Bad Gateway - 网关错误，可能后端过载
        # 504 Gateway Timeout - 网关超时，可能后端过载
        if status_code in [
            HTTPStatus.SERVICE_UNAVAILABLE.value,
            HTTPStatus.TOO_MANY_REQUESTS.value,
            HTTPStatus.BAD_GATEWAY.value,
            HTTPStatus.GATEWAY_TIMEOUT.value,
        ]:
            return True

    # 2. 异常类型判断（完整的模块路径）
    exception_type_full = (f"{type(exception).__module__}."
                           f"{type(exception).__name__}")
    exception_type_name = type(exception).__name__
    if (
        exception_type_full in OVERLOAD_EXCEPTIONS
        or exception_type_name in OVERLOAD_EXCEPTIONS
    ):
        return True

    # 3. 特定库异常处理
    for lib_name, exceptions in LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING.items():
        if lib_name in exception_type_full and any(
            exc in exception_type_name for exc in exceptions
        ):
            return True

    # 4. 异常消息内容判断
    error_message = str(exception).lower()
    for keyword in OVERLOAD_KEYWORDS:
        if keyword in error_message:
            return True

    # 5. 系统级异常判断（errno）
    for indicator in SYSTEM_OVERLOAD_INDICATORS:
        if indicator in error_message:
            return True

    # 6. 特殊情况：递归检查异常链
    for attr_name in ('__cause__', '__context__'):
        chained_exception = getattr(exception, attr_name, None)
        if chained_exception and _overload_check(chained_exception):
            return True

    # 7. 检查异常的args属性
    if hasattr(exception, "args") and exception.args:
        if any(
            isinstance(arg, str) and
            any(keyword in arg.lower() for keyword in OVERLOAD_KEYWORDS)
            for arg in exception.args
        ):
            return True

    return False


def speed_up_retry(
    timeout: int = 0,
    hedged_request_time: float = 0,
    hedged_request_proportion: float = 0.025,
    speed_up_max_multiply: int = 5,
    retry_times: int = 0,
    retry_interval: float = 1,
    exception_types: Union[
        Type[BaseException],
        Tuple[Type[BaseException], ...],
    ] = BaseException,
    default_result=None,
    debug: bool = False,
):
    """
    重试装饰器，支持异步和同步函数，具备并行加速的重试机制

    参数:
        timeout (int): 超时时间，单位秒
        hedged_request_time (float): 触发请求对冲的时间，最多触发一次对冲
        hedged_request_proportion (float): 触发请求对冲的最大比例
        speed_up_max_multiply (int): 最大加速倍率
        retry_times (int): 最大重试次数，不包括首次调用
        retry_interval (float): 重试间隔，单位秒
        exception_types (Union[Type, Tuple[Type]]): 需要捕获并重试的异常类型
        default_result (Any): 默认返回值，可以是一个可调用的函数
        debug (bool): 是否打印调试日志

    实例:
        @retry(retry_times=5, default_result=0)
        def func1() -> int:
            ...同步方法，最多重试 5 次，都失败时返回 0...

        @retry(timeout=10, retry_times=5, default_result=0)
        async def func2() -> int:
            ...异步方法，重试达到 5 次或执行总耗时超过 10 秒时都会认为流程失败，返回默认值 0...

        @retry(timeout=10, retry_times=5, default_result=0)
        async def func3() -> int:
            ... 每一轮重试失败都会将并发数扩大 1 ...
            ......................................................
            ... 全失败场景 ...
            ... 第一次执行 ... ❌
            ... 第一次重试 ... ❌
            ... 第二次重试 ... ❌ ... 第三次重试 ...⏳
            ... 第三次重试 ... ❌ ... 第四次重试 ...⏳ ... 第五次重试 ...⏳
            ... 第四次重试 ... ❌ ... 第五次重试 ...⏳
            ... 第五次重试 ... ❌
            ......................................................
            ... 普通场景一 ...
            ... 第一次执行 ... ✅
            ......................................................
            ... 普通场景二 ...
            ... 第一次执行 ... ❌
            ... 第二次重试 ... ❌
            ... 第二次重试 ... ✅ ... 第三次重试 ...🚫
            ......................................................

        @retry(timeout=50, retry_times=30, default_result=0, hedged_request_time=5)
        async def func3() -> int:
            ... 每一轮重试失败都会将并发数扩大 1，...
            ......................................................
            <00秒> ... 全失败场景 ...
            <00秒> ... 第一次执行 ...⏳
            <05秒> ... 第一次执行 ...⏳ ... 第一次对冲 ...⏳                         触发对冲，算一次重试，并发数不变
            <10秒> ... 第一次执行 ...❌ ... 第一次对冲 ...⏳                         执行失败，并发数增加 1，为 1
            <11秒> ... 第二次重试 ...⏳ ... 第一次对冲 ...⏳                         间隔一秒重试
            <15秒> ... 第二次重试 ...⏳ ... 第一次对冲 ...❌                         执行失败，并发数增加 1，为 2
            <16秒> ... 第二次重试 ...⏳ ... 第三次重试 ...⏳                         间隔一秒重试
            <21秒> ... 第二次重试 ...❌ ... 第三次重试 ...⏳                         执行失败，并发数增加 1，为 3，达到最大值
            <22秒> ... 第三次重试 ...⏳ ... 第四次重试 ...⏳                         间隔一秒重试
            <23秒> ... 第三次重试 ...⏳ ... 第四次重试 ...⏳ ... 第五次重试 ...⏳      间隔一秒重试
            <26秒> ... 第三次重试 ...❌ ... 第四次重试 ...⏳ ... 第五次重试 ...⏳      执行失败，窗口不增加
            <27秒> ... 第四次重试 ...⏳ ... 第五次重试 ...⏳ ... 第六次重试 ...⏳      间隔一秒重试
            <50秒> ... 第六次重试 ...🚫 ... 第七次重试 ...🚫 ... 第八次重试 ...🚫      到达超时时间，任务取消
            ......................................................
    # noqa: E501
    """

    if exception_types is None:
        exception_types = (BaseException,)
    elif not isinstance(exception_types, tuple):
        exception_types = (exception_types,)
    if hedged_request_time > 0 and (
        hedged_request_proportion <= 0.000001 or
        hedged_request_proportion > 1.0
    ):
        raise BaseException(
            "hedged_request_proportion must be in [0.000001, 1]"
        )
    hedged_request_multiply = 0
    if hedged_request_time > 0 and hedged_request_proportion > 0:
        hedged_request_multiply = 1 / hedged_request_proportion - 1

    def _get_max_wait_time(
        basic_wait_time: float, has_wait_time: float, max_wait_time: int
    ) -> float:
        if basic_wait_time < 0:
            basic_wait_time = 0.01
        if (max_wait_time <= 0 or
                basic_wait_time + has_wait_time < max_wait_time):
            return basic_wait_time
        if has_wait_time > max_wait_time:
            return 0.01
        return max_wait_time - has_wait_time

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # 0. 定义初始变量
                cur_running_task = RunningTaskPool.get_pool(func.__qualname__)
                if timeout > 0:
                    cur_running_task._window_interval = timeout
                cur_times = 0
                start_time = time.perf_counter()
                cur_speed_up_multiply = 0
                run_tasks = []
                result_exception = None
                result = None
                finish = False
                can_hedged_request = True
                last_submit_time = start_time
                result_exception_list = []
                cur_running_task.add(1)

                try:
                    while not finish and (
                        cur_times <= retry_times or len(run_tasks) > 0
                    ):
                        # 1 判断是否可以提交任务
                        #   * 运行中的任务小于 1 则可以提交
                        #   * 小于当前加速倍率
                        #   * 小于最大加速倍率且满足请求对冲要求
                        if cur_times <= retry_times and (
                            len(run_tasks) <= 0
                            or (
                                len(run_tasks) < cur_speed_up_multiply
                                and cur_running_task.less_than(len(run_tasks) + 1)
                            )
                            or (
                                0
                                < hedged_request_time
                                < min(
                                    time.perf_counter() - start_time,
                                    2 * (time.perf_counter() - last_submit_time),
                                )
                                and can_hedged_request
                                and cur_running_task.less_than(
                                    len(run_tasks) + hedged_request_multiply
                                )
                            )
                        ):
                            if (
                                cur_speed_up_multiply <= len(run_tasks)
                                and 0
                                < hedged_request_time
                                < min(
                                    time.perf_counter() - start_time,
                                    2 * (time.perf_counter() - last_submit_time),
                                )
                                and can_hedged_request
                                and cur_running_task.less_than(
                                    len(run_tasks) + hedged_request_multiply
                                )
                            ):
                                result_exception_list.append(
                                    f"hedged_request: {time.perf_counter() - start_time}"
                                )
                                can_hedged_request = False
                            elif result_exception is not None:
                                result_exception_list.append(
                                    f"{type(result_exception).__name__} "
                                    f"{str(result_exception)}"
                                )
                            run_tasks.append(asyncio.create_task(func(*args, **kwargs)))
                            cur_times += 1
                            last_submit_time = time.perf_counter()

                        # 2 执行
                        done, pending = [], []
                        if len(run_tasks) > 0:
                            # 2.1 获取超时时间，取 timeout、hedged_request_time、当前可加速情况的最小值
                            cur_timeout = 0
                            if timeout > 0:
                                cur_timeout = start_time + timeout - time.perf_counter()
                            if (
                                can_hedged_request
                                and hedged_request_time > 0
                                and (
                                    start_time
                                    + hedged_request_time
                                    - time.perf_counter()
                                    < cur_timeout
                                    or cur_timeout == 0
                                )
                            ):
                                cur_timeout = (
                                    start_time
                                    + hedged_request_time
                                    - time.perf_counter()
                                )
                            if (
                                len(run_tasks) < cur_speed_up_multiply
                                and cur_times < retry_times
                                and (cur_timeout > retry_interval or cur_timeout == 0)
                                or cur_timeout < 0
                            ):
                                cur_timeout = retry_interval

                            #  2.2 执行
                            if cur_timeout > 0:
                                done, pending = await asyncio.wait(
                                    run_tasks,
                                    timeout=cur_timeout,
                                    return_when=asyncio.FIRST_COMPLETED,
                                )
                            else:
                                done, pending = await asyncio.wait(
                                    run_tasks, return_when=asyncio.FIRST_COMPLETED
                                )

                        # 3 处理结果
                        # 3.1 处理执行成功的结果
                        can_add_speed_up_multiply = (
                            cur_speed_up_multiply < speed_up_max_multiply
                        )
                        while len(done) > 0:
                            try:
                                finished = done.pop()
                                run_tasks.remove(finished)
                                if finished.cancelled():
                                    continue

                                if finished.exception() is None:
                                    await _cancel_async_task(
                                        pending,
                                        done,
                                        _get_max_wait_time(
                                            retry_interval,
                                            time.perf_counter() - start_time,
                                            timeout,
                                        ),
                                    )
                                    result = finished.result()
                                    result_exception = None
                                    finish = True
                                    break

                                # 3.2 处理可捕获异常，有过载保护
                                result_exception = finished.exception()
                                if any(
                                    isinstance(result_exception, t)
                                    for t in exception_types
                                ):
                                    if can_add_speed_up_multiply:
                                        cur_speed_up_multiply += 1
                                        can_add_speed_up_multiply = False
                                    if _overload_check(result_exception):
                                        cur_speed_up_multiply = 0
                                    await asyncio.sleep(
                                        _get_max_wait_time(
                                            retry_interval,
                                            time.perf_counter() - start_time,
                                            timeout,
                                        )
                                    )
                                    break

                                # 3.3 处理不可捕获异常
                                await _cancel_async_task(
                                    pending,
                                    done,
                                    _get_max_wait_time(
                                        retry_interval,
                                        time.perf_counter() - start_time,
                                        timeout,
                                    ),
                                )
                                finish = True
                                break
                            except asyncio.CancelledError:
                                continue

                        # 3.4 处理超时情况
                        if 0 < timeout < time.perf_counter() - start_time:
                            result_exception = asyncio.TimeoutError
                            await _cancel_async_task(
                                pending,
                                done,
                                _get_max_wait_time(
                                    retry_interval,
                                    time.perf_counter() - start_time,
                                    timeout,
                                ),
                            )
                            finish = True

                    # 4. 返回结果
                    if result_exception is not None:
                        if default_result is not None:
                            if callable(default_result):
                                return default_result(*args, **kwargs)
                            else:
                                return default_result
                        raise result_exception
                    return result
                finally:
                    cur_running_task.add(-1)
                    if debug:
                        print(
                            f"[retry] {func.__qualname__} execute finish, "
                            f"executeTimes: {cur_times}, "
                            f"speedUpMultiply: {cur_speed_up_multiply}, "
                            f"consumeTime: {time.perf_counter() - start_time}, "
                            f"exceptions: {result_exception_list}"
                        )

            return wrapper

        else:

            def wrapper(*args, **kwargs):
                # 0. 定义初始变量
                cur_running_task = RunningTaskPool.get_pool(func.__qualname__)
                cur_times = 0
                start_time = time.perf_counter()
                cur_speed_up_multiply = 0
                run_tasks = []
                result_exception = None
                result = None
                finish = False
                can_hedged_request = True
                last_submit_time = start_time
                result_exception_list = []
                cur_running_task.add(1)
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        while not finish and (
                            cur_times <= retry_times or len(run_tasks) > 0
                        ):
                            # 1 判断是否可以提交任务
                            #   * 运行中的任务小于 1 则可以提交
                            #   * 小于当前加速倍率
                            #   * 小于最大加速倍率且满足请求对冲要求
                            if cur_times <= retry_times and (
                                len(run_tasks) <= 0
                                or (
                                    len(run_tasks) < cur_speed_up_multiply
                                    and cur_running_task.less_than(len(run_tasks) + 1)
                                )
                                or (
                                    0
                                    < hedged_request_time
                                    < min(
                                        time.perf_counter() - start_time,
                                        2 * (time.perf_counter() - last_submit_time),
                                    )
                                    and can_hedged_request
                                    and cur_running_task.less_than(
                                        len(run_tasks) + hedged_request_multiply
                                    )
                                )
                            ):
                                if (
                                    cur_speed_up_multiply <= len(run_tasks)
                                    and 0
                                    < hedged_request_time
                                    < min(
                                        time.perf_counter() - start_time,
                                        2 * (time.perf_counter() - last_submit_time),
                                    )
                                    and can_hedged_request
                                    and cur_running_task.less_than(
                                        len(run_tasks) + hedged_request_multiply
                                    )
                                ):
                                    result_exception_list.append(
                                        f"hedged_request: {time.perf_counter() - start_time}"
                                    )
                                    can_hedged_request = False
                                elif result_exception is not None:
                                    result_exception_list.append(
                                        f"{type(result_exception).__name__} "
                                        f"{str(result_exception)}"
                                    )
                                run_tasks.append(executor.submit(func, *args, **kwargs))
                                cur_times += 1
                                last_submit_time = time.perf_counter()

                            # 2 执行
                            done, pending = [], []
                            if len(run_tasks) > 0:
                                # 2.1 获取超时时间，取 timeout、hedged_request_time、当前可加速情况的最小值
                                cur_timeout = 0
                                if timeout > 0:
                                    cur_timeout = (
                                        start_time + timeout - time.perf_counter()
                                    )
                                if (
                                    can_hedged_request
                                    and hedged_request_time > 0
                                    and (
                                        start_time
                                        + hedged_request_time
                                        - time.perf_counter()
                                        < cur_timeout
                                        or cur_timeout == 0
                                    )
                                ):
                                    cur_timeout = (
                                        start_time
                                        + hedged_request_time
                                        - time.perf_counter()
                                    )
                                if (
                                    len(run_tasks) < cur_speed_up_multiply
                                    and cur_times < retry_times
                                    and (
                                        cur_timeout > retry_interval or cur_timeout == 0
                                    )
                                    or cur_timeout < 0
                                ):
                                    cur_timeout = retry_interval

                                # 2.2 执行
                                if cur_timeout > 0:
                                    done, pending = concurrent.futures.wait(
                                        run_tasks,
                                        timeout=cur_timeout,
                                        return_when=concurrent.futures.FIRST_COMPLETED,
                                    )
                                else:
                                    done, pending = concurrent.futures.wait(
                                        run_tasks,
                                        return_when=concurrent.futures.FIRST_COMPLETED,
                                    )

                            # 3 处理结果
                            # 3.1 处理执行成功的结果
                            can_add_speed_up_multiply = (
                                cur_speed_up_multiply < speed_up_max_multiply
                            )
                            while len(done) > 0:
                                try:
                                    finished = done.pop()
                                    run_tasks.remove(finished)
                                    if finished.cancelled():
                                        continue

                                    if finished.exception() is None:
                                        _cancel_sync_task(
                                            pending,
                                            done,
                                            _get_max_wait_time(
                                                retry_interval,
                                                time.perf_counter() - start_time,
                                                timeout,
                                            ),
                                        )
                                        result = finished.result()
                                        result_exception = None
                                        finish = True
                                        break

                                    # 3.2 处理可捕获异常，有过载保护
                                    result_exception = finished.exception()
                                    result_exception_list.append(
                                        f"{type(result_exception).__name__} "
                                        f"{str(result_exception)}"
                                    )
                                    if any(
                                        isinstance(result_exception, t)
                                        for t in exception_types
                                    ):
                                        if can_add_speed_up_multiply:
                                            cur_speed_up_multiply += 1
                                            can_add_speed_up_multiply = False
                                        if _overload_check(result_exception):
                                            cur_speed_up_multiply = 0
                                            time.sleep(
                                                _get_max_wait_time(
                                                    retry_interval,
                                                    time.perf_counter() - start_time,
                                                    timeout,
                                                )
                                            )
                                        time.sleep(
                                            _get_max_wait_time(
                                                retry_interval,
                                                time.perf_counter() - start_time,
                                                timeout,
                                            )
                                        )
                                        break

                                    # 3.3 处理不可捕获异常
                                    _cancel_sync_task(
                                        pending,
                                        done,
                                        _get_max_wait_time(
                                            retry_interval,
                                            time.perf_counter() - start_time,
                                            timeout,
                                        ),
                                    )
                                    finish = True
                                    break
                                except concurrent.futures.CancelledError:
                                    continue

                            # 3.4 处理超时情况
                            if 0 < timeout < time.perf_counter() - start_time:
                                result_exception = TimeoutError
                                _cancel_async_task(
                                    pending,
                                    done,
                                    _get_max_wait_time(
                                        retry_interval,
                                        time.perf_counter() - start_time,
                                        timeout,
                                    ),
                                )
                                finish = True

                        # 4. 返回结果
                        if result_exception is not None:
                            if default_result is not None:
                                if callable(default_result):
                                    return default_result(*args, **kwargs)
                                else:
                                    return default_result
                            raise result_exception
                        return result
                finally:
                    cur_running_task.add(-1)
                    if debug:
                        print(
                            f"[retry] {func.__qualname__} execute finish, "
                            f"executeTimes: {cur_times}, "
                            f"speedUpMultiply: {cur_speed_up_multiply}, "
                            f"consumeTime: {time.perf_counter() - start_time}, "
                            f"exceptions: {result_exception_list}"
                        )

            return wrapper

    return decorator
