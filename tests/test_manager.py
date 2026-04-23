"""Tests for OpenAIChatProxyManager module."""

import pytest
from unittest.mock import MagicMock

from qreward.client.load_balancer import LoadBalanceStrategy
from qreward.client.manager import OpenAIChatProxyManager
from qreward.client.openai import OpenAIChatProxy


class TestManagerSelectProxyLeastConnections:
    """Test select_proxy with LEAST_CONNECTIONS strategy."""

    def test_select_proxy_least_connections(self):
        """Test that LEAST_CONNECTIONS strategy uses round-robin selector."""
        manager = OpenAIChatProxyManager(
            strategy=LoadBalanceStrategy.LEAST_CONNECTIONS,
        )
        mock_proxy = MagicMock(spec=OpenAIChatProxy)
        manager.add_proxy("k1", mock_proxy)
        result = manager.select_proxy()
        assert result is mock_proxy


class TestManagerSelectProxyModelRouter:
    """Test select_proxy with model router."""

    def test_select_proxy_model_router_resolve_none(self):
        """Test fallback to normal strategy
        when model_router.resolve returns None."""
        manager = OpenAIChatProxyManager()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)
        manager.add_proxy("k1", mock_proxy)
        mock_router = MagicMock()
        mock_router.resolve.return_value = None
        manager._model_router = mock_router
        result = manager.select_proxy(model="gpt-4")
        assert result is mock_proxy  # fallback to normal strategy


class TestManagerBatchStreamChatCompletion:
    """Test batch_stream_chat_completion method."""

    @pytest.mark.asyncio
    async def test_batch_stream_chat_completion(self):
        """Test batch_stream_chat_completion yields items from proxy."""
        manager = OpenAIChatProxyManager()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        # Create async generator for mock
        async def mock_stream(*args, **kwargs):
            yield (0, "hello")
            yield (1, "world")

        mock_proxy.batch_stream_chat_completion = mock_stream
        manager.add_proxy("k1", mock_proxy)

        results = []
        async for item in manager.batch_stream_chat_completion(
            batch_messages=[[{"role": "user", "content": "hi"}]],
            model="gpt-4",
        ):
            results.append(item)

        assert results == [(0, "hello"), (1, "world")]


class TestManagerSelectProxyWeightedRoundRobin:
    """Test select_proxy with WEIGHTED_ROUND_ROBIN strategy."""

    def test_select_proxy_weighted_round_robin(self):
        """Test that WRR strategy selects proxy correctly."""
        manager = OpenAIChatProxyManager(
            strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN,
        )
        mock_proxy1 = MagicMock(spec=OpenAIChatProxy)
        mock_proxy2 = MagicMock(spec=OpenAIChatProxy)
        manager.add_proxy("k1", mock_proxy1, weight=3)
        manager.add_proxy("k2", mock_proxy2, weight=1)

        result = manager.select_proxy()
        assert result in [mock_proxy1, mock_proxy2]

    def test_select_proxy_wrr_weighted_distribution(self):
        """Test that WRR distributes according to weights."""
        manager = OpenAIChatProxyManager(
            strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN,
        )
        mock_proxy1 = MagicMock(spec=OpenAIChatProxy)
        mock_proxy2 = MagicMock(spec=OpenAIChatProxy)
        manager.add_proxy("k1", mock_proxy1, weight=3)
        manager.add_proxy("k2", mock_proxy2, weight=1)

        selections = [manager.select_proxy() for _ in range(8)]
        count_p1 = selections.count(mock_proxy1)
        count_p2 = selections.count(mock_proxy2)
        assert count_p1 > count_p2
