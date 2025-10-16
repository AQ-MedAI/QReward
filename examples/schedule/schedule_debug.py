import asyncio
import random

from qreward.utils import schedule


# 遇到任意异常都会重试，最大重试次数为 5，最多调度 1 + 5 次，打印调度信息
@schedule(debug=True, retry_times=5)
async def basic_time_out(num:int = 0):
    await asyncio.sleep(1.5)
    if random.random() < 0.5:
        raise BaseException("random error")
    return num


if __name__ == '__main__':
    asyncio.run(basic_time_out(6))