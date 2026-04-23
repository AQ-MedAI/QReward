"""Streaming Response Example

Demonstrates how to use stream_chat_completion() for real-time token-by-token
response streaming. This is useful for chat applications where you want to
display tokens as they arrive rather than waiting for the full response.

Prerequisites:
  export OPENAI_API_BASE="https://your-api-endpoint/v1"
  export OPENAI_API_KEY="sk-your-key"

NOTE: This example requires a valid API endpoint and key to run.
Without them, the code serves as a reference for the streaming API.
"""

import asyncio
import os
import sys

from qreward.client import OpenAIChatProxy


_messages = [
    {"role": "system", "content": "You are a helpful assistant. Keep answers brief."},
    {"role": "user", "content": "Explain what a neural network is in 2 sentences."},
]


# --- Example 1: Basic streaming ---
async def demo_basic_streaming():
    print("=== Basic Streaming ===\n")

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
    ) as proxy:
        print("  Response: ", end="", flush=True)
        async for token in proxy.stream_chat_completion(
            messages=_messages,
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        ):
            print(token, end="", flush=True)
        print("\n")


# --- Example 2: Collecting streamed tokens ---
async def demo_collect_tokens():
    print("=== Collect Streamed Tokens ===\n")

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
    ) as proxy:
        tokens = []
        async for token in proxy.stream_chat_completion(
            messages=_messages,
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        ):
            tokens.append(token)

        full_response = "".join(tokens)
        print(f"  Total tokens received: {len(tokens)}")
        print(f"  Full response: {full_response[:100]}...")
        print()


# --- Example 3: Streaming with custom parameters ---
async def demo_streaming_with_params():
    print("=== Streaming with Custom Parameters ===\n")

    async with OpenAIChatProxy(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
    ) as proxy:
        print("  Response: ", end="", flush=True)
        async for token in proxy.stream_chat_completion(
            messages=[
                {"role": "user", "content": "Count from 1 to 5."},
            ],
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            temperature=0.0,
            max_tokens=50,
        ):
            print(token, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_BASE"):
        print("⚠️  OPENAI_API_BASE not set. Set environment variables to run:")
        print("   export OPENAI_API_BASE='https://your-api/v1'")
        print("   export OPENAI_API_KEY='sk-your-key'")
        print("   export OPENAI_MODEL='gpt-3.5-turbo'  # optional")
        print()
        print("Showing code structure only. See source for usage patterns.")
        sys.exit(0)

    asyncio.run(demo_basic_streaming())
    asyncio.run(demo_collect_tokens())
    asyncio.run(demo_streaming_with_params())
