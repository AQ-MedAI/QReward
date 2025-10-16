import random
import time

import asyncio

from qreward.utils import schedule


# 对冲请求，当执行耗时大于 5 秒后会再调用 1 次，2 次调用哪 1 次调用先返回就返回，用于解决长尾调用问题
# 6 秒能执行完毕
@schedule(hedged_request_time=5, retry_times=1)
async def basic_hedged_request(st: float = 0):
    if time.time() < st + 5:
        await asyncio.sleep(10)
    else:
        await asyncio.sleep(1)
    return 0


# 对冲请求，主要用于解决调用长尾问题，比如大部分请求能在 3 秒内调用完，但部分请求耗时会到 30 秒(偶发性)
@schedule(debug=True, hedged_request_time=3, retry_times=100)
async def basic_batch_hedged_request(num: int = 0):
    if random.randint(0, 10000) < 9900:
        await asyncio.sleep(2.5)
    else:
        await asyncio.sleep(30)
        raise TimeoutError("timeout error")
    return num


async def batch_run():
    task_list = []
    for n in range(25000):
        task_list.append(asyncio.create_task(basic_batch_hedged_request(n)))
    await asyncio.gather(*task_list)


if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(basic_hedged_request(start_time))
    print(time.time() - start_time)

    start_time = time.time()
    asyncio.run(batch_run())
    print(time.time() - start_time)
