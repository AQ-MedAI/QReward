import asyncio
import threading
from typing import Any, AsyncIterator, Optional

from qreward.client.load_balancer import (
    LoadBalanceStrategy,
    RoundRobinSelector,
    WeightedRoundRobinSelector,
)
from qreward.client.model_router import ModelRouter
from qreward.client.openai import OpenAIChatProxy


class OpenAIChatProxyManager:
    """管理多个 key -> OpenAIChatProxy 的映射。

    提供代理的增删查改、负载均衡和故障转移功能，支持链式调用。

    Example:
        manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.ROUND_ROBIN)
        manager.add_proxy_with_default("key1", "http://api1.example.com", "sk-xxx")
        manager.add_proxy_with_default("key2", "http://api2.example.com", "sk-yyy")
        proxy = manager.select_proxy()  # round-robin selection
    """

    def __init__(
        self,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN,
    ) -> None:
        self._proxies: dict[str, OpenAIChatProxy] = {}
        self._insertion_order: list[str] = []
        self._healthy_keys: set[str] = set()
        self._weights: dict[str, int] = {}
        self._strategy = strategy
        self._lock = asyncio.Lock()
        self._health_lock = threading.Lock()

        self._rr_selector = RoundRobinSelector()
        self._wrr_selector = WeightedRoundRobinSelector()
        self._model_router: Optional[ModelRouter] = None

    def add_proxy_with_default(
        self, key: str, base_url: str, api_key: str
    ) -> "OpenAIChatProxyManager":
        """添加一个使用默认配置的代理。

        Args:
            key: 代理标识
            base_url: OpenAI API 基础 URL
            api_key: OpenAI API 密钥

        Returns:
            self，支持链式调用
        """
        self.add_proxy(
            key=key,
            proxy=OpenAIChatProxy(
                base_url=base_url,
                api_key=api_key,
            ),
        )
        return self

    def add_proxies_with_default(
        self, proxies: dict[str, tuple[str, str]]
    ) -> "OpenAIChatProxyManager":
        """批量添加使用默认配置的代理。

        Args:
            proxies: 代理映射，key 为代理标识，value 为 (base_url, api_key) 元组

        Returns:
            self，支持链式调用
        """
        for key, (base_url, api_key) in proxies.items():
            self.add_proxy_with_default(
                key=key,
                base_url=base_url,
                api_key=api_key,
            )
        return self

    def add_proxy(
        self,
        key: str,
        proxy: OpenAIChatProxy,
        weight: int = 1,
    ) -> "OpenAIChatProxyManager":
        """添加一个自定义配置的代理。

        Args:
            key: 代理标识
            proxy: OpenAIChatProxy 实例
            weight: 权重（用于加权轮询策略），默认为 1

        Returns:
            self，支持链式调用

        Raises:
            ValueError: 当 key 已存在时
        """
        if key in self._proxies:
            raise ValueError(f"Proxy with key={key!r} already exists.")
        self._proxies[key] = proxy
        self._insertion_order.append(key)
        self._weights[key] = max(1, weight)
        with self._health_lock:
            self._healthy_keys.add(key)
        self._wrr_selector.update_weights(self._weights)
        return self

    def proxy(self, key: str) -> OpenAIChatProxy:
        """获取指定 key 的代理。

        Args:
            key: 代理标识

        Returns:
            对应的 OpenAIChatProxy 实例

        Raises:
            KeyError: 当 key 不存在时
        """
        try:
            return self._proxies[key]
        except KeyError:
            raise KeyError(f"Proxy with key={key!r} does not exist.")

    def exist_proxy(self, key: str) -> bool:
        """检查指定 key 的代理是否存在。

        Args:
            key: 代理标识

        Returns:
            True 如果存在，否则 False
        """
        return key in self._proxies

    def proxies(self) -> dict[str, OpenAIChatProxy]:
        """获取所有代理的字典副本。

        返回副本以防止外部修改内部状态。

        Returns:
            key -> OpenAIChatProxy 的映射副本
        """
        return dict(self._proxies)

    def register_model_route(
        self,
        pattern: str,
        proxy_map: dict[str, OpenAIChatProxy],
        weights: Optional[dict[str, int]] = None,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN,
    ) -> "OpenAIChatProxyManager":
        """Register a model route for model-based proxy selection.

        Args:
            pattern: Model name or glob pattern (e.g. "gpt-4" or "gpt-*").
            proxy_map: Mapping of key → OpenAIChatProxy for this model.
            weights: Optional per-key weights for weighted round-robin.
            strategy: Load balancing strategy for this model group.

        Returns:
            self, for chaining.
        """
        if self._model_router is None:
            self._model_router = ModelRouter()
        self._model_router.register(pattern, proxy_map, weights, strategy)
        return self

    def list_routes(self) -> list[dict]:
        """List all registered model routes.

        Returns:
            List of route info dicts, or empty list if no router configured.
        """
        if self._model_router is None:
            return []
        return self._model_router.list_routes()

    def select_proxy(self, model: Optional[str] = None) -> OpenAIChatProxy:
        """根据负载均衡策略选择一个可用代理。

        Args:
            model: Optional model name for model-based routing.

        Returns:
            选中的 OpenAIChatProxy 实例。

        Raises:
            RuntimeError: 当没有可用的健康代理时。
        """
        if model and self._model_router is not None:
            group = self._model_router.resolve(model)
            if group is not None:
                return self._model_router.select_from_group(group)

        with self._health_lock:
            healthy_snapshot = set(self._healthy_keys)

        selected_key: str | None = None

        if self._strategy == LoadBalanceStrategy.ROUND_ROBIN:
            selected_key = self._rr_selector.select(
                self._insertion_order, healthy_snapshot
            )
        elif self._strategy == LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN:
            selected_key = self._wrr_selector.select(
                self._insertion_order, healthy_snapshot, self._weights
            )
        elif self._strategy == LoadBalanceStrategy.LEAST_CONNECTIONS:
            selected_key = self._rr_selector.select(
                self._insertion_order, healthy_snapshot
            )

        if selected_key is None:
            raise RuntimeError("No healthy proxy available.")

        return self._proxies[selected_key]

    def mark_unhealthy(self, key: str) -> None:
        """标记代理为不健康状态。

        Args:
            key: 代理标识。

        Raises:
            KeyError: 当 key 不存在时。
        """
        if key not in self._proxies:
            raise KeyError(f"Proxy with key={key!r} does not exist.")
        with self._health_lock:
            self._healthy_keys.discard(key)

    def mark_healthy(self, key: str) -> None:
        """标记代理为健康状态。

        Args:
            key: 代理标识。

        Raises:
            KeyError: 当 key 不存在时。
        """
        if key not in self._proxies:
            raise KeyError(f"Proxy with key={key!r} does not exist.")
        with self._health_lock:
            self._healthy_keys.add(key)

    def healthy_proxies(self) -> dict[str, OpenAIChatProxy]:
        """获取所有健康代理的字典副本。

        Returns:
            key -> OpenAIChatProxy 的映射副本（仅健康代理）。
        """
        with self._health_lock:
            healthy_snapshot = set(self._healthy_keys)
        return {k: v for k, v in self._proxies.items() if k in healthy_snapshot}

    async def remove_proxy(self, key: str) -> None:
        """移除并关闭指定 key 的代理。

        Args:
            key: 代理标识
        """
        async with self._lock:
            proxy = self._proxies.pop(key, None)
            if key in self._insertion_order:
                self._insertion_order.remove(key)
            self._weights.pop(key, None)
            with self._health_lock:
                self._healthy_keys.discard(key)
        if proxy:
            await proxy.client.close()

    async def batch_stream_chat_completion(
        self, batch_messages: list[list[dict[str, Any]]],
        model: str, **kwargs: Any,
    ) -> "AsyncIterator[tuple[int, str]]":
        """通过负载均衡选择代理并执行批量流式聊天补全。"""
        proxy = self.select_proxy(model=model)
        async for item in proxy.batch_stream_chat_completion(
            batch_messages, model, **kwargs
        ):
            yield item

    async def close(self) -> None:
        """关闭所有代理并清空映射。"""
        async with self._lock:
            proxies_to_close = list(self._proxies.values())
            self._proxies.clear()
            self._insertion_order.clear()
            self._weights.clear()
            with self._health_lock:
                self._healthy_keys.clear()
        for proxy in proxies_to_close:
            await proxy.client.close()
