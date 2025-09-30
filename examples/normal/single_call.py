import os
import asyncio
from datetime import datetime

from qreward.client import OpenAIChatProxy, OpenAIChatProxyManager


_messages = [{"role": "user", "content": "Hello, how are you?"}]


async def simple_call():
    start_time = datetime.now()
    proxy = OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    call_result = await proxy.chat_completion(
        messages=_messages,
        model="DeepSeek-R1",
    )

    print(
        f"{(datetime.now() - start_time).seconds} secs, " f"task result: {call_result}"
    )


async def simple_call_by_context():
    start_time = datetime.now()

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    ) as proxy:
        call_result = await proxy.chat_completion(
            messages=_messages,
            model="DeepSeek-R1",
        )

    print(
        f"{(datetime.now() - start_time).seconds} secs, " f"task result: {call_result}"
    )


async def call_single_with_proxy_manager():
    start_time = datetime.now()

    proxy_manager = OpenAIChatProxyManager()
    proxy_manager.add_proxy(
        "default",
        OpenAIChatProxy(
            base_url=os.getenv("OPENAI_API_BASE"),
            api_key=os.getenv("OPENAI_API_KEY"),
        ),
    )
    # you can add more proxy with different base_url and api_key

    # single call
    call_result = await proxy_manager.proxy("default").chat_completion(
        messages=_messages,
        model="DeepSeek-R1",
    )

    print(
        f"{(datetime.now() - start_time).seconds} secs, " f"task result: {call_result}"
    )


if __name__ == "__main__":
    asyncio.run(simple_call())
    asyncio.run(simple_call_by_context())
    asyncio.run(call_single_with_proxy_manager())
