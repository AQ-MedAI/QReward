import asyncio
import functools
import random
import time
from collections.abc import Callable
from typing import (
    Any,
    Union,
    Iterable,
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
