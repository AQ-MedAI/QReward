import asyncio
import time

from qreward.utils import schedule


# 限流，默认窗口为 1 秒，所以限流为 2 QPS
# 打印记录如下
# 0 0 1 1 2 2 3 3 4 4 5 5 6 6 7 7 8 8 9 9
@schedule(limit_size=2)
async def basic_limit(start_time: float = 0):
    await asyncio.sleep(0.5)
    print(f"{int(time.time() - start_time)}")
    return 0


# 限流，基于参数给不同的限流值，'a' 组与 'b' 组各限流 2
# 打印记录如下，各组都被限流了 1
# a-0 a-0 b-0 b-0 a-1 a-1 b-1 b-1 ....
@schedule(limit_size=2, key_func=lambda group, start_time: str(group))
async def basic_group_limit(group: str = "none", start_time: float = 0):
    await asyncio.sleep(0.5)
    print(f"{group}-{int(time.time() - start_time)}")
    return 0


async def run_basic():
    task_list = []
    start_time = time.time()
    for _ in range(20):
        task = asyncio.create_task(basic_limit(start_time))
        task_list.append(task)
    await asyncio.gather(*task_list)


async def run_basic_group():
    task_list = []
    start_time = time.time()
    for idx in range(20):
        task = asyncio.create_task(
            basic_group_limit("a" if idx % 2 == 0 else "b", start_time)
        )
        task_list.append(task)
    await asyncio.gather(*task_list)


if __name__ == "__main__":
    asyncio.run(run_basic())
    asyncio.run(run_basic_group())
