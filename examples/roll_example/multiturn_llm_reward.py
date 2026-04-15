"""ROLL Framework Integration — LLM-as-Judge Reward with QReward

This module provides a custom Reward Worker for the ROLL (Reinforcement Learning
Optimization for Large-Scale Learning) framework. It uses QReward's OpenAIChatProxy
to efficiently call a remote LLM Judge API for reward computation.

When to use this instead of ROLL's built-in LLMJudgeRewardWorker:
  - Your Judge model is deployed as a remote OpenAI-compatible API service
    (not on local GPUs managed by ROLL)
  - You need high-concurrency async calls with automatic retry, rate limiting,
    circuit breaker, and load balancing
  - You want to use multiple Judge API endpoints with failover

Architecture:
  ROLL Training Loop
    └── Reward Worker (this module)
          └── QReward OpenAIChatProxy
                └── Remote LLM Judge API (e.g., DeepSeek-R1, GPT-4, Qwen)

Prerequisites:
  pip install qreward
  export OPENAI_API_BASE="https://your-judge-api/v1"
  export OPENAI_API_KEY="sk-your-key"

ROLL YAML configuration (rewards section):
  rewards:
    llm_judge:
      worker_cls: multiturn_llm_reward.QRewardLLMJudgeWorker
      tag_included: [RLVR]
      judge_prompt: your-prompt-template
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from qreward.client import OpenAIChatProxy, OpenAIChatProxyManager, LoadBalanceStrategy

logger = logging.getLogger(__name__)


class RewardCalculator:
    """Encapsulates LLM-as-Judge reward computation using QReward.

    Supports single-endpoint and multi-endpoint (load-balanced) configurations.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        judge_model: str = "DeepSeek-R1",
        max_concurrent: int = 64,
        extra_base_urls: Optional[List[str]] = None,
        extra_api_keys: Optional[List[str]] = None,
    ):
        self._judge_model = judge_model

        if extra_base_urls:
            # Multi-endpoint mode with load balancing
            self._manager = OpenAIChatProxyManager(
                strategy=LoadBalanceStrategy.ROUND_ROBIN,
            )
            self._manager.add_proxy(
                key="primary",
                proxy=OpenAIChatProxy(
                    base_url=base_url,
                    api_key=api_key,
                    max_concurrent=max_concurrent,
                ),
            )
            keys = extra_api_keys or [api_key] * len(extra_base_urls)
            for idx, (url, key) in enumerate(zip(extra_base_urls, keys)):
                self._manager.add_proxy(
                    key=f"secondary_{idx}",
                    proxy=OpenAIChatProxy(
                        base_url=url,
                        api_key=key,
                        max_concurrent=max_concurrent,
                    ),
                )
            self._proxy = None
        else:
            # Single-endpoint mode
            self._proxy = OpenAIChatProxy(
                base_url=base_url,
                api_key=api_key,
                max_concurrent=max_concurrent,
            )
            self._manager = None

    def _get_proxy(self) -> OpenAIChatProxy:
        if self._manager is not None:
            return self._manager.select_proxy()
        return self._proxy

    async def call_judge_model(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        request_timeout: int = 300,
    ) -> tuple[str, str]:
        """Call the Judge LLM and return (thinking, answer) tuple."""
        proxy = self._get_proxy()
        response = await proxy.chat_completion(
            model=self._judge_model,
            messages=messages,
            temperature=temperature,
            timeout=request_timeout,
            stream=False,
        )

        if "</think>" in response:
            think, answer = response.split("</think>", 1)
            think += "</think>"
            answer = answer.strip()
        else:
            think = ""
            answer = response.strip()

        return think, answer

    @staticmethod
    def convert_messages_to_dialogue(messages: List[Dict[str, str]]) -> str:
        """Convert a list of chat messages into a formatted dialogue string."""
        lines = []
        for item in messages:
            role = item["role"]
            content = item["content"]
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "system":
                lines.append(f"System: {content}")
            else:
                raise ValueError(f"Unsupported role: {role!r}")
        return "\n".join(lines)

    async def compute_single_reward(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 5,
    ) -> float:
        """Compute reward score for a single conversation, with retries."""
        remaining = max_retries
        while remaining > 0:
            try:
                if isinstance(messages, list):
                    dialogue = self.convert_messages_to_dialogue(messages)
                elif isinstance(messages, str):
                    dialogue = messages
                else:
                    raise TypeError(f"Expected list or str, got {type(messages)}")

                think, response = await self.call_judge_model(
                    messages=[{"role": "user", "content": dialogue}],
                )

                parsed = json.loads(
                    response.replace("json", "").replace("```", "")
                )
                score_list = [item["score"] for item in parsed.values()]

                # Example scoring formula — customize for your task
                return score_list[0] / 4 + score_list[1] / 2 + score_list[2] / 10
            except Exception as exc:
                remaining -= 1
                logger.warning(
                    "Reward computation failed (retries left: %d): %s",
                    remaining, exc,
                )
        return 0.0

    async def compute_batch_rewards(
        self,
        batch_messages: List[List[Dict[str, str]]],
    ) -> List[float]:
        """Compute rewards for a batch of conversations concurrently."""
        tasks = [
            asyncio.create_task(self.compute_single_reward(msgs))
            for msgs in batch_messages
        ]
        return list(await asyncio.gather(*tasks))


# ---------------------------------------------------------------------------
# ROLL custom reward entry point
# ---------------------------------------------------------------------------
# ROLL discovers this class via the YAML config:
#   rewards:
#     llm_judge:
#       worker_cls: multiturn_llm_reward.QRewardLLMJudgeWorker
#
# The class must implement compute_reward(prompts, responses, ...) which
# ROLL calls during the reward computation phase of the training loop.
# ---------------------------------------------------------------------------

class QRewardLLMJudgeWorker:
    """Custom ROLL Reward Worker that uses QReward for LLM-as-Judge scoring.

    This worker replaces ROLL's built-in LLMJudgeRewardWorker when the Judge
    model is deployed as a remote API service rather than on local GPUs.

    Environment variables:
      OPENAI_API_BASE:       Primary Judge API endpoint
      OPENAI_API_KEY:        Primary API key
      JUDGE_MODEL:           Model name (default: DeepSeek-R1)
      JUDGE_MAX_CONCURRENT:  Max concurrent requests (default: 64)
      JUDGE_EXTRA_URLS:      Comma-separated extra endpoints for load balancing
      JUDGE_EXTRA_KEYS:      Comma-separated extra API keys
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}

        base_url = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
        api_key = os.getenv("OPENAI_API_KEY", "")
        judge_model = os.getenv("JUDGE_MODEL", "DeepSeek-R1")
        max_concurrent = int(os.getenv("JUDGE_MAX_CONCURRENT", "64"))

        extra_urls_raw = os.getenv("JUDGE_EXTRA_URLS", "")
        extra_urls = [u.strip() for u in extra_urls_raw.split(",") if u.strip()]
        extra_keys_raw = os.getenv("JUDGE_EXTRA_KEYS", "")
        extra_keys = [k.strip() for k in extra_keys_raw.split(",") if k.strip()] or None

        self._calculator = RewardCalculator(
            base_url=base_url,
            api_key=api_key,
            judge_model=judge_model,
            max_concurrent=max_concurrent,
            extra_base_urls=extra_urls if extra_urls else None,
            extra_api_keys=extra_keys,
        )

    def compute_reward(
        self,
        prompts: List[str],
        responses: List[str],
        **kwargs: Any,
    ) -> List[float]:
        """Compute rewards for a batch of prompt-response pairs.

        This is the main entry point called by ROLL's reward computation phase.

        Args:
            prompts: List of prompt strings.
            responses: List of response strings.
            **kwargs: Additional arguments from ROLL (e.g., ground_truth).

        Returns:
            List of reward scores (one per prompt-response pair).
        """
        batch_messages = []
        for prompt, response in zip(prompts, responses):
            batch_messages.append([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ])

        start_time = datetime.now().strftime("%H:%M:%S")

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                results = pool.submit(
                    asyncio.run,
                    self._calculator.compute_batch_rewards(batch_messages),
                ).result()
        else:
            results = asyncio.run(
                self._calculator.compute_batch_rewards(batch_messages)
            )

        end_time = datetime.now().strftime("%H:%M:%S")
        logger.info(
            "QReward LLM Judge: start=%s end=%s batch_size=%d",
            start_time, end_time, len(batch_messages),
        )
        return results


# ---------------------------------------------------------------------------
# Standalone compute_score function (verl-compatible interface)
# ---------------------------------------------------------------------------
# If your ROLL setup uses a function-based reward interface (similar to verl),
# you can use this function directly.
# ---------------------------------------------------------------------------

async def compute_score(
    messages: List[List[Dict[str, str]]],
    ground_truth: Optional[List[str]] = None,
    extra_info: Optional[Dict[str, Any]] = None,
) -> List[float]:
    """Compute reward scores for a batch of multi-turn conversations.

    This function provides a verl/slime-compatible interface that can also
    be used with ROLL's function-based reward configuration.

    Args:
        messages: Batch of conversations, each is a list of message dicts.
        ground_truth: Optional ground truth answers.
        extra_info: Optional extra information.

    Returns:
        List of reward scores.
    """
    start_time = datetime.now().strftime("%H:%M:%S")

    calculator = RewardCalculator(
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        judge_model=os.getenv("JUDGE_MODEL", "DeepSeek-R1"),
        max_concurrent=int(os.getenv("JUDGE_MAX_CONCURRENT", "64")),
    )

    results = await calculator.compute_batch_rewards(messages)

    end_time = datetime.now().strftime("%H:%M:%S")
    logger.info(
        "compute_score: start=%s end=%s batch_size=%d completed=%d",
        start_time, end_time, len(messages), len(results),
    )
    return results
