import asyncio
import os
from collections.abc import Callable
from datetime import datetime
from typing import (
    Any,
    Dict,
    List,
    Tuple,
    Union,
    Optional,
    Sequence,
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


# Hard code here: 最大重试次数
MAX_RETRIES = 10

# Hard code for patch:
patch_httpx()

# 错误组
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
        max_concurrent: int = 1024,
        chat_process_fuc: Callable | None = None,
        error_process_fuc: Callable | None = None,
        timeout: float | Timeout = None,
        rate_limiter_bucket_size: float = 50.0,
        rate_limiter_bucket_period: float = 1.0,
        httpx_request_hook: RequestHook | None = None,
        httpx_response_hook: ResponseHook | None = None,
        is_hack_embedding_method: bool = False,
    ):
        """初始化 OpenAI Chat 代理

        Args:
            base_url: OpenAI API 的地址
            api_key: API密钥（默认尝试从环境变量 OPENAI_API_KEY 中获取）
            debug: 是否开启调试模式（默认是: False）
            max_concurrent: 最大并发请求数（默认是: 1024）
            chat_process_fuc: 对话处理函数
            error_process_fuc: 错误处理函数
            timeout: 超时时间（默认是: None）
            rate_limiter_bucket_size: 令牌桶大小（默认是: 50.0）
            rate_limiter_bucket_period: 令牌桶刷新时间（默认是: 1.0）
            httpx_request_hook: httpx 请求钩子函数（默认是: None）
            httpx_response_hook: httpx 响应钩子函数（默认是: None）
            is_hack_embedding_method: 是否开启 Hack Embedding 方法（默认是: False）
        ):
        """
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
        self._default_chat_process_fuc = chat_process_fuc
        self._default_error_process_fuc = error_process_fuc

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
    ) -> DefaultAioHttpClient:
        _http_client = DefaultAioHttpClient(
            verify=False,
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

    def with_error_process_fuc(self, error_process_fuc: Callable):
        self._default_error_process_fuc = error_process_fuc
        return self

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
        messages: list,
        model: str,
        **kwargs,
    ) -> str:
        """调用 OpenAI Chat 接口

        Args:
            model: 使用的模型
            messages: 消息
            **kwargs: 其他参数

        Returns:
            API响应结果
        """
        if self.debug:
            print(f"[time: {datetime.now()}] - [Begin] - Call model: {model}")

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
                    # TODO 其他扩展参数
                ),
                timeout=kwargs.get("timeout", self._default_timeout),
            )
            if self.debug:
                print(
                    f"[time: {datetime.now()}] - [End] - "
                    f"Call model: {model} success!",
                )

            if self._default_chat_process_fuc:
                completion = self._default_chat_process_fuc(completion)

            return self._default_chat_completion_func(completion=completion)

    async def batch_chat_completion(
        self,
        batch_messages: list,
        model: str,
        **kwargs,
    ) -> list[Any]:
        """批量调用 OpenAI Chat 接口

        Args:
            batch_messages: 批量消息
            model: 使用的模型
            **kwargs: 其他参数

        Returns:
            API响应结果列表
        """
        tasks = []
        for i in range(len(batch_messages)):
            # 插入任务
            tasks.append(
                asyncio.create_task(
                    self.chat_completion(
                        model=model,
                        messages=batch_messages[i],
                        **kwargs,
                    ),
                ),
            )

        # 返回
        results = await asyncio.gather(*tasks)

        # 处理异常
        processed_results = []
        for result in results:
            if (self._default_error_process_fuc
                    and isinstance(result, Exception)):
                result = self._default_error_process_fuc(result)

            processed_results.append(result)

        return processed_results

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
        **kwargs,
    ) -> list:
        """调用 OpenAI Embeddings 接口

        Args:
            sentences: 句子列表
            model: 使用的模型
            extra_body: 额外的请求体参数
                        （如果接口参数不同，建议通过 extra_body 传）
            **kwargs: 其他参数

        Returns:
            API响应结果
        """
        try:
            if self.debug:
                print(
                    f"[INFO] - [time: {datetime.now()}] - "
                    f"[Begin] - Call embedding: {model}",
                )

            # typing: from openai.types import CreateEmbeddingResponse
            embedding_resp = await asyncio.wait_for(
                self.client.embeddings.create(
                    input=sentences,
                    model=model,
                    extra_body=extra_body,
                ),
                timeout=kwargs.get("timeout", self._default_timeout),
            )

            if self.debug:
                print(
                    f"[INFO] - [time: {datetime.now()}] - [End] - "
                    f"Call embedding: {model} success!",
                )

            return embedding_resp.embeddings if self._is_hack_embedding \
                else embedding_resp.data
        except Exception as e:
            print(
                f"[time: {datetime.now()}] - "
                f"[Error] - Call embedding: {model}, "
                f"error: {e!s}, error type: {type(e)}",
            )

            if isinstance(e, (asyncio.exceptions.TimeoutError, TimeoutError)):
                print(
                    f"[time: {datetime.now()}] - "
                    f"[Retry-Timeout] - Call model: {model}",
                )
                raise TimeoutError

            return []

    async def batch_embeddings(
        self,
        *,
        batch_sentences: List[Union[str, Sequence]],
        model: str | None = None,
        extra_bodies: List[object] | None = None,
        **kwargs,
    ) -> list[list]:
        """批量调用 OpenAI Embeddings 接口

        Args:
            batch_sentences: 多个句子列表
            model: 使用的模型
            extra_bodies: 额外的请求体参数列表
            **kwargs: 其他参数

        Returns:
            API响应结果
        """
        tasks = []
        for i in range(len(batch_sentences)):
            # 插入任务
            tasks.append(
                asyncio.create_task(
                    self.embeddings(
                        model=model,
                        sentences=batch_sentences[i],
                        extra_body=extra_bodies[i] if extra_bodies else None,
                        **kwargs,
                    ),
                ),
            )

        # 返回
        return await asyncio.gather(*tasks)


class OpenAIChatProxyManager:
    """管理多个 key -> OpenAIChatProxy 的映射"""

    def __init__(self):
        self._proxies: Dict[str, OpenAIChatProxy] = {}

    def add_proxy_with_default(self, key: str, base_url: str, api_key: str):
        """添加一个默认代理

        Args:
            key: 代理标识
            base_url: OpenAI API 基础 URL
            api_key: OpenAI API 密钥
        """
        self.add_proxy(
            key=key,
            proxy=OpenAIChatProxy(
                base_url=base_url,
                api_key=api_key,
            ),
        )
        return self

    def add_proxies_with_default(self, proxies: Dict[str, Tuple[str, str]]):
        """添加多个默认代理

        Args:
            proxies: 多个代理的映射，key 为代理标识，value 为 (base_url, api_key) 元组
        """
        for key, (base_url, api_key) in proxies.items():
            self.add_proxy_with_default(
                key=key,
                base_url=base_url,
                api_key=api_key,
            )
        return self

    def add_proxy(self, key: str, proxy: OpenAIChatProxy):
        """添加一个代理（配置自定义参数的都走这个）

        Args:
            key: 代理标识
            proxy: OpenAIChatProxy 实例
        """
        if key in self._proxies:
            raise ValueError(f"Proxy with key={key!r} already exists.")
        self._proxies[key] = proxy
        return self

    def proxy(self, key: str) -> OpenAIChatProxy:
        """获取一个代理

        Args:
            key: 代理标识
        """
        try:
            return self._proxies[key]
        except KeyError:
            raise KeyError(f"Proxy with key={key!r} does not exist.")

    def exist_proxy(self, key: str) -> bool:
        """检查是否存在代理

        Args:
            key: 代理标识
        """
        return key in self._proxies

    def proxies(self) -> Dict[str, OpenAIChatProxy]:
        """获取所有代理"""
        return self._proxies

    async def remove_proxy(self, key: str):
        """移除并关闭代理

        Args:
            key: 代理标识
        """
        proxy = self._proxies.pop(key, None)
        if proxy:
            await proxy.client.close()

    async def close(self):
        """关闭所有代理"""
        for proxy in self._proxies.values():
            await proxy.client.close()
        self._proxies.clear()
