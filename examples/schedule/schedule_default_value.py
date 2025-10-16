import random
import asyncio

from qreward.utils import schedule


# 有默认值，调度都失败后会返回这个默认值，比如重试 10 次都失败就会返回 0
@schedule(retry_times=10, default_result=0)
async def basic_default_value(num: int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.9999:
        raise asyncio.TimeoutError("timeout error")
    return num


# 有默认值，但默认值为 None，调度都失败后会返回这个默认值
@schedule(retry_times=10, default_result=None)
async def basic_default_none_value(num: int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.9999:
        raise asyncio.TimeoutError("timeout error")
    return num


# 有默认值构造函数，调度都失败后会将函数参数传递个默认值构造函数生成默认值并返回，比如 basic_default_fn_retry(5) 调度都失败后会返回 5
@schedule(retry_times=10, default_result=lambda num: num)
async def basic_default_fn(num: int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.9999:
        raise asyncio.TimeoutError("timeout error")
    return num


# 调度失败包括所有没调度成功的异常场景，包括超时、重试全失败、遇到不可捕获异常等
@schedule(retry_times=10, timeout=5, default_result=0)
async def basic_timeout_default_value(num: int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.9999:
        raise asyncio.TimeoutError("timeout error")
    return num


# 遇到不可捕获异常，也会返回默认值 0
@schedule(retry_times=10, timeout=5, default_result=0, exception_types=(TimeoutError,))
async def basic_exception_default_value(num: int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.9999:
        raise asyncio.TimeoutError("timeout error")
    return num


if __name__ == "__main__":
    print(asyncio.run(basic_default_value(3)))
    print(asyncio.run(basic_default_none_value(4)))
    print(asyncio.run(basic_default_fn(5)))
    print(asyncio.run(basic_timeout_default_value(6)))
    print(asyncio.run(basic_exception_default_value(7)))
