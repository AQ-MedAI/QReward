"""Batch Streaming Response Example

Demonstrates how to use batch_stream_chat_completion() to concurrently stream
multiple chat completions. Each yielded item is a (batch_index, token) tuple,
allowing you to track which stream each token belongs to.

Features:
  - Concurrent execution of multiple streaming requests
  - Per-stream identification via batch_index
  - Configurable max_concurrent_streams
  - Optional on_stream_error callback for partial failure handling

Prerequisites:
  export OPENAI_API_BASE="https://your-api-endpoint/v1"
  export OPENAI_API_KEY="sk-your-key"

NOTE: This example requires a valid API endpoint and key to run.
Without them, the code serves as a reference for the batch streaming API.
"""

import asyncio
import os
import sys
from collections import defaultdict

from qreward.client import OpenAIChatProxy


# --- Example 1: Basic batch streaming ---
async def demo_basic_batch_streaming():
    print("=== Basic Batch Streaming ===\n")

    batch_messages = [
        [{"role": "user", "content": "Say 'hello' in French."}],
        [{"role": "user", "content": "Say 'hello' in Spanish."}],
        [{"role": "user", "content": "Say 'hello' in Japanese."}],
    ]

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
    ) as proxy:
        # Collect tokens per stream
        streams: dict[int, list[str]] = defaultdict(list)

        async for batch_idx, token in proxy.batch_stream_chat_completion(
            batch_messages=batch_messages,
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        ):
            streams[batch_idx].append(token)

        for idx in sorted(streams.keys()):
            response = "".join(streams[idx])
            print(f"  Stream {idx}: {response}")
        print()


# --- Example 2: Concurrency control ---
async def demo_concurrency_control():
    print("=== Batch Streaming with Concurrency Control ===\n")

    # 5 requests but only 2 concurrent streams at a time
    batch_messages = [
        [{"role": "user", "content": f"Count to {i + 1}."}]
        for i in range(5)
    ]

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
    ) as proxy:
        streams: dict[int, list[str]] = defaultdict(list)

        async for batch_idx, token in proxy.batch_stream_chat_completion(
            batch_messages=batch_messages,
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            max_concurrent_streams=2,  # Only 2 streams at a time
        ):
            streams[batch_idx].append(token)

        print(f"  Completed {len(streams)} streams (max 2 concurrent)")
        for idx in sorted(streams.keys()):
            response = "".join(streams[idx])
            print(f"  Stream {idx}: {response[:60]}...")
        print()


# --- Example 3: Error handling ---
async def demo_error_handling():
    print("=== Batch Streaming with Error Handling ===\n")

    errors: list[tuple[int, str]] = []

    def on_error(batch_idx: int, exc: Exception):
        errors.append((batch_idx, str(exc)))
        print(f"  ⚠️  Stream {batch_idx} error: {exc}")

    batch_messages = [
        [{"role": "user", "content": "Say hello."}],
        [{"role": "user", "content": "Say goodbye."}],
    ]

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
    ) as proxy:
        streams: dict[int, list[str]] = defaultdict(list)

        async for batch_idx, token in proxy.batch_stream_chat_completion(
            batch_messages=batch_messages,
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            on_stream_error=on_error,
        ):
            streams[batch_idx].append(token)

        print(f"\n  Completed streams: {len(streams)}")
        print(f"  Errors: {len(errors)}\n")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_BASE"):
        print("⚠️  OPENAI_API_BASE not set. Set environment variables to run:")
        print("   export OPENAI_API_BASE='https://your-api/v1'")
        print("   export OPENAI_API_KEY='sk-your-key'")
        print("   export OPENAI_MODEL='gpt-3.5-turbo'  # optional")
        print()
        print("Showing code structure only. See source for usage patterns.")
        sys.exit(0)

    asyncio.run(demo_basic_batch_streaming())
    asyncio.run(demo_concurrency_control())
    asyncio.run(demo_error_handling())
