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


async def call_single_embedding_with_custom_path_and_input():
    sentences = ["你好", "再见"]

    def update_path(request) -> None:
        # CH: 默认 OpenAI 是 /embeddings 路径，这里重写为 /embed
        # EN: default OpenAI is /embeddings path, here rewrite to /embed
        if request.url.path in ["/embeddings"]:
            request.url = request.url.copy_with(path="/embed")

    async with OpenAIChatProxy(
        base_url="http://custom_url:8000",
        api_key=os.getenv("OPENAI_API_KEY"),
        **{"request_hook": update_path}
    ) as proxy:
        embedding_result = await proxy.embeddings(
            model="embedding-model",
            sentences=[],
            extra_body={"sentences":  sentences},
            # CH: 上面这么写是因为 OpenAI 默认 key 是 input 而不是 sentences
            # EN: above is because OpenAI default key is input instead of sentences

            # CH: 如果用户自己自定义了 key，那么需要使用 extra_body 参数传递
            # EN: if user custom key, need to pass through extra_body parameter
        )
        print(embedding_result)


if __name__ == "__main__":
    asyncio.run(simple_call())
    asyncio.run(simple_call_by_context())
    asyncio.run(call_single_with_proxy_manager())
