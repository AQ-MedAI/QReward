import os
import asyncio
from datetime import datetime

from qreward.client import OpenAIChatProxy


task_size = 2048
_example_messages = [
    {
        "role": "system",
        "content": "You are a knowledgeable and helpful AI assistant.",
    },
    {
        "role": "user",
        "content": "Hi, can you explain quantum mechanics to me?",
    },
    {
        "role": "assistant",
        "content": "Quantum mechanics is a branch of physics that "
                   "describes the behavior of particles at "
                   "microscopic scales, introducing concepts such as "
                   "wave-particle duality and the uncertainty principle.",
    },
    {
        "role": "user",
        "content": "That sounds fascinating. Are there any classic "
                   "experiments that confirm these theories?",
    },
    {
        "role": "assistant",
        "content": "Yes, the double-slit experiment is one of the most "
                   "famous demonstrations of wave-particle duality, "
                   "showing that particles can exhibit wave-like "
                   "interference when not observed.",
    },
    {
        "role": "user",
        "content": "Can you describe the process of the "
                   "double-slit experiment in more detail?",
    },
]
BATCH_MESSAGES = [_example_messages * task_size]


async def simple_call_batch():
    start_time = datetime.now()
    proxy = OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    batch_call_result = await proxy.batch_chat_completion(
        batch_messages=_example_messages,
        model="DeepSeek-R1",
    )

    print(
        f"{(datetime.now() - start_time).seconds} secs, "
        f"task len: {len(batch_call_result)}"
    )


async def simple_call_batch_by_context():
    start_time = datetime.now()

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    ) as proxy:
        batch_call_result = await proxy.batch_chat_completion(
            batch_messages=_example_messages,
            model="DeepSeek-R1",
        )

    print(
        f"{(datetime.now() - start_time).seconds} secs, "
        f"task len: {len(batch_call_result)}"
    )


async def call_batch_embedding():
    start_time = datetime.now()

    proxy = OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    batch_embedding_result = await proxy.batch_embeddings(
        batch_sentences=[["123", "456"], ["456", "789"]],
        model="embedding-model",
    )
    print(
        f"{(datetime.now() - start_time).seconds} secs, "
        f"task len: {len(batch_embedding_result)}"
    )


async def call_batch_embedding_by_context():
    start_time = datetime.now()

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE"),
        api_key=os.getenv("OPENAI_API_KEY"),
    ) as proxy:
        batch_embedding_result = await proxy.batch_embeddings(
            batch_sentences=[["123", "456"], ["456", "789"]],
            model="embedding-model",
        )

    print(
        f"{(datetime.now() - start_time).seconds} secs, "
        f"task len: {len(batch_embedding_result)}"
    )


if __name__ == "__main__":
    asyncio.run(simple_call_batch())
    asyncio.run(simple_call_batch_by_context())
    asyncio.run(call_batch_embedding())
    asyncio.run(call_batch_embedding_by_context())
