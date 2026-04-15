import asyncio
import logging
import os
import warnings
from collections.abc import Callable
from datetime import datetime
from typing import (
    Any,
    AsyncIterator,
    Optional,
    Sequence,
    Union,
)

from aiolimiter import AsyncLimiter
from httpx import Limits, Timeout, TimeoutException
from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    DefaultAioHttpClient,
    RateLimitError,
)
from openai.types.chat import ChatCompletion
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from qreward.client.patch_openai import patch_openai_embeddings
from qreward.types import RequestHook, ResponseHook
from qreward.utils import patch_httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
_ERROR_GROUP = (
    TimeoutError,
    asyncio.TimeoutError,
    TimeoutException,
    RateLimitError,
    APIStatusError,
    APITimeoutError,
    APIConnectionError,
)


class OpenAIChatProxy:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        debug: bool = False,
        max_concurrent: int = 64,
        chat_process_func: Callable | None = None,
        error_process_func: Callable | None = None,
        chat_process_fuc: Callable | None = None,
        error_process_fuc: Callable | None = None,
        timeout: float | Timeout = None,
        rate_limiter_bucket_size: float = 50.0,
        rate_limiter_bucket_period: float = 1.0,
        httpx_request_hook: RequestHook | None = None,
        httpx_response_hook: ResponseHook | None = None,
        is_hack_embedding_method: bool = False,
        verify_ssl: bool = False,
    ):
        """初始化 OpenAI Chat 代理。"""
        # Lazy patch: apply httpx JSON optimization on first proxy creation
        patch_httpx()

        # Handle deprecated parameters
        if chat_process_fuc is not None:
            warnings.warn(
                "chat_process_fuc is deprecated, use chat_process_func instead",
                DeprecationWarning,
                stacklevel=2,
            )
            if chat_process_func is None:
                chat_process_func = chat_process_fuc
        
        if error_process_fuc is not None:
            warnings.warn(
                "error_process_fuc is deprecated, use error_process_func instead",
                DeprecationWarning,
                stacklevel=2,
            )
            if error_process_func is None:
                error_process_func = error_process_fuc

        self.debug = debug
        self._max_concurrent = max_concurrent
        self._api_key = api_key or self.get_openai_key()
        self.client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
            http_client=self._default_http_client(
                request_hook=httpx_request_hook,
                response_hook=httpx_response_hook,
                verify=verify_ssl,
            ),
        )

        self.semaphore = asyncio.Semaphore(value=self._max_concurrent)

        # default token bucket size is 50 QPS
        self.rate_limiter = AsyncLimiter(
            max_rate=rate_limiter_bucket_size,
            time_period=rate_limiter_bucket_period,
        )

        self._default_temperature = 0.0
        self._default_timeout = 60
        self._default_chat_process_func = chat_process_func
        self._default_error_process_func = error_process_func

        # for hacking embedding
        self._is_hack_embedding = is_hack_embedding_method
        if self._is_hack_embedding:
            patch_openai_embeddings()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()

    def _default_http_client(
        self,
        request_hook: RequestHook | None = None,
        response_hook: ResponseHook | None = None,
        verify: bool = False,
    ) -> DefaultAioHttpClient:
        _http_client = DefaultAioHttpClient(
            verify=verify,
            # 默认值是 100 / 20，现在需要根据 self._max_concurrent 的值来调整配比
            limits=Limits(
                max_connections=self._max_concurrent,
                max_keepalive_connections=self._max_concurrent,
            ),
        )

        if request_hook and isinstance(request_hook, Callable):
            _http_client.event_hooks.get("request").append(request_hook)

        if response_hook and isinstance(response_hook, Callable):
            _http_client.event_hooks.get("response").append(response_hook)

        return _http_client

    @staticmethod
    def get_openai_key() -> str | None:
        return os.getenv("OPENAI_API_KEY")

    def with_max_concurrent(self, max_concurrent: int):
        self._max_concurrent = max_concurrent
        return self

    def with_temperature(self, temperature: float):
        self._default_temperature = temperature
        return self

    def with_timeout(self, timeout: int):
        self.client.timeout = timeout
        self._default_timeout = timeout
        return self

    def with_error_process_func(self, error_process_func: Callable):
        self._default_error_process_func = error_process_func
        return self

    def with_error_process_fuc(self, error_process_fuc: Callable):
        warnings.warn(
            "with_error_process_fuc is deprecated, use with_error_process_func instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.with_error_process_func(error_process_fuc)

    @staticmethod
    def _default_chat_completion_func(completion: ChatCompletion):
        return completion.choices[0].message.content

    @retry(
        retry=retry_if_exception_type(exception_types=_ERROR_GROUP),
        wait=wait_exponential(multiplier=1, min=2, max=4),
        stop=stop_after_attempt(max_attempt_number=MAX_RETRIES),
        reraise=True,
    )
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> str:
        """调用 OpenAI Chat 接口。"""
        if self.debug:
            logger.debug("[time: %s] - [Begin] - Call model: %s", datetime.now(), model)

        async with self.semaphore, self.rate_limiter:
            completion: ChatCompletion = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=kwargs.get(
                        "temperature",
                        self._default_temperature,
                    ),
                    stream=kwargs.get("stream"),
                ),
                timeout=kwargs.get("timeout", self._default_timeout),
            )
            if self.debug:
                logger.debug(
                    "[time: %s] - [End] - Call model: %s success!",
                    datetime.now(),
                    model,
                )

            if self._default_chat_process_func:
                completion = self._default_chat_process_func(completion)

            return self._default_chat_completion_func(completion=completion)

    async def batch_chat_completion(
        self,
        batch_messages: list[list[dict[str, Any]]],
        model: str,
        **kwargs: Any,
    ) -> list[Any]:
        """批量调用 OpenAI Chat 接口。"""
        tasks = []
        for i in range(len(batch_messages)):
            tasks.append(
                asyncio.create_task(
                    self.chat_completion(
                        model=model,
                        messages=batch_messages[i],
                        **kwargs,
                    ),
                ),
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "batch_chat_completion task %d/%d failed: %s: %s",
                    index + 1,
                    len(results),
                    type(result).__name__,
                    result,
                )
                if self._default_error_process_func:
                    result = self._default_error_process_func(result)

            processed_results.append(result)

        return processed_results

    async def stream_chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式聊天补全，逐 token 返回内容。

        Args:
            messages: 消息列表
            model: 使用的模型
            **kwargs: 其他参数，支持 temperature / timeout 等

        Yields:
            每个 chunk 的文本内容
        """
        if self.debug:
            logger.debug("[time: %s] - [Begin] - Stream model: %s", datetime.now(), model)

        async with self.semaphore, self.rate_limiter:
            stream = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=kwargs.get("temperature", self._default_temperature),
                stream=True,
                timeout=kwargs.get("timeout", self._default_timeout),
            )
            try:
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content
            finally:
                await stream.close()

        if self.debug:
            logger.debug("[time: %s] - [End] - Stream model: %s done!", datetime.now(), model)

    @retry(
        retry=retry_if_exception_type(exception_types=_ERROR_GROUP),
        wait=wait_exponential(multiplier=1, min=2, max=4),
        stop=stop_after_attempt(max_attempt_number=MAX_RETRIES),
        reraise=True,
    )
    async def embeddings(
        self,
        *,
        sentences: Optional[Union[str, Sequence]] = None,
        model: str | None = None,
        extra_body: object | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        """调用 OpenAI Embeddings 接口。"""
        if self.debug:
            logger.debug(
                "[time: %s] - [Begin] - Call embedding: %s",
                datetime.now(),
                model,
            )

        embedding_resp = await asyncio.wait_for(
            self.client.embeddings.create(
                input=sentences,
                model=model,
                extra_body=extra_body,
            ),
            timeout=kwargs.get("timeout", self._default_timeout),
        )

        if self.debug:
            logger.debug(
                "[time: %s] - [End] - Call embedding: %s success!",
                datetime.now(),
                model,
            )

        return (
            embedding_resp.embeddings
            if self._is_hack_embedding
            else embedding_resp.data
        )

    async def batch_stream_chat_completion(
        self, batch_messages: list[list[dict[str, Any]]], model: str,
        max_concurrent_streams: int = 0,
        on_stream_error: Callable[[int, Exception], None] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[int, str]]:
        """并发多个流式请求，yield (batch_index, token) 元组。"""
        if not batch_messages:
            return
        queue: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue()
        sem = asyncio.Semaphore(max_concurrent_streams) if max_concurrent_streams > 0 else None
        async def _run(idx: int, msgs: list[dict[str, Any]]) -> None:
            try:
                if sem:
                    await sem.acquire()
                async for tok in self.stream_chat_completion(msgs, model, **kwargs):
                    await queue.put((idx, tok))
            except Exception as exc:
                if on_stream_error:
                    on_stream_error(idx, exc)
            finally:
                if sem:
                    sem.release()
        tasks = [asyncio.create_task(_run(i, m)) for i, m in enumerate(batch_messages)]
        async def _drain() -> None:
            await asyncio.gather(*tasks, return_exceptions=True)
            await queue.put(None)
        sentinel = asyncio.create_task(_drain())
        while (item := await queue.get()) is not None:
            yield item
        await sentinel

    async def batch_embeddings(
        self, *, batch_sentences: list[Union[str, Sequence]],
        model: str | None = None, extra_bodies: list[object] | None = None,
        **kwargs: Any,
    ) -> list[list[Any]]:
        """批量调用 OpenAI Embeddings 接口。"""
        tasks = [
            asyncio.create_task(self.embeddings(
                model=model, sentences=batch_sentences[i],
                extra_body=extra_bodies[i] if extra_bodies else None, **kwargs,
            ))
            for i in range(len(batch_sentences))
        ]
        return await asyncio.gather(*tasks)