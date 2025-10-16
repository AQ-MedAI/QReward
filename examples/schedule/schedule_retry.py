import asyncio
import random
import time

from qreward.utils import schedule


# 遇到任意异常都会重试，最大重试次数为 5，最多调度 1 + 5 次
@schedule(retry_times=5)
async def basic_retry(num: int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.5:
        raise BaseException("random error")
    return num


# 遇到 TimeoutError 会重试，最大重试次数为 5
@schedule(
    retry_times=30,
    exception_types=(
        asyncio.TimeoutError,
        TimeoutError,
    ),
)
async def basic_err_retry(num: int = 0):
    await asyncio.sleep(5)
    if random.random() < 0.8:
        raise asyncio.TimeoutError("timeout error")
    return num


# 加速重试，没重试失败一次重试并行度都会扩大 1，直至达到 speed_up_max_multiply
# 实际重试会检查检测过往并行度，保证并行度捕获大于过往并行度，并且也会做负载检查
# 要关闭加速可将 speed_up_max_multiply 设置为 0 即可
# 如下是加速示例
# 1                 -> 第一次调度
# 2                 -> 第一次重试，失败后重试并行度扩大至 2
# 3 3               -> 第二、三次重试，都失败后重试并行度扩大至 4
# 4 4 4 4           -> 第四、五、六、七次重试，失败后重试并行度扩大至 5(speed_up_max_multiply 默认值为 5)
# 5 5 5 5 5
# 6 6 6 6 6
# 7 7 7 7 7
# 8 8 8 8 8
# 9 9 9
@schedule(retry_times=30, default_result=0, retry_interval=0.01)
async def basic_speed_up_retry(start_time: float = 0):
    await asyncio.sleep(3)
    print(f"{int(time.time() - start_time)//3}")
    raise BaseException("random error")


if __name__ == "__main__":
    print(asyncio.run(basic_retry(1)))
    print(asyncio.run(basic_err_retry(2)))
    print(asyncio.run(basic_speed_up_retry(time.time())))
