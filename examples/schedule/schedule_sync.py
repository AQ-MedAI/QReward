import random
import time

from qreward.utils import schedule


# 遇到任意异常都会重试，最大重试次数为 5，最多调度 1 + 5 次
# 同步异步都支持
@schedule(retry_times=5)
def basic_retry(num: int = 0):
    time.sleep(1.5)
    if random.random() < 0.5:
        raise BaseException("random error")
    return num


if __name__ == "__main__":
    print(basic_retry(5))
