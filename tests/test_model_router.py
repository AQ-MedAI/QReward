"""Tests for ModelRouter class."""

from unittest.mock import MagicMock

import pytest

from qreward.client.load_balancer import LoadBalanceStrategy
from qreward.client.model_router import ModelRouter
from qreward.client.openai import OpenAIChatProxy


class TestModelRouterSelectFromGroup:
    """Tests for select_from_group method."""

    def test_select_weighted_round_robin_strategy(self):
        """Test WEIGHTED_ROUND_ROBIN strategy selection."""
        router = ModelRouter()
        mock_proxy1 = MagicMock(spec=OpenAIChatProxy)
        mock_proxy2 = MagicMock(spec=OpenAIChatProxy)

        proxy_map = {"k1": mock_proxy1, "k2": mock_proxy2}
        weights = {"k1": 3, "k2": 1}

        router.register(
            "gpt-4",
            proxy_map,
            weights=weights,
            strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN,
        )

        group = router.resolve("gpt-4")
        selected = router.select_from_group(group)

        assert selected in [mock_proxy1, mock_proxy2]
        # Verify weighted selection by calling multiple times
        selections = [router.select_from_group(group) for _ in range(10)]
        assert selections.count(mock_proxy1) > selections.count(mock_proxy2)

    def test_select_least_connections_strategy(self):
        """Test LEAST_CONNECTIONS strategy selection (covers lines 130-131)."""
        router = ModelRouter()
        mock_proxy1 = MagicMock(spec=OpenAIChatProxy)
        mock_proxy2 = MagicMock(spec=OpenAIChatProxy)

        proxy_map = {"k1": mock_proxy1, "k2": mock_proxy2}

        router.register(
            "gpt-4",
            proxy_map,
            strategy=LoadBalanceStrategy.LEAST_CONNECTIONS,
        )

        group = router.resolve("gpt-4")
        selected = router.select_from_group(group)

        assert selected in [mock_proxy1, mock_proxy2]

    def test_select_from_group_no_healthy_proxies(self):
        """Test select_from_group raises RuntimeError
        when no healthy proxies."""
        router = ModelRouter()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        router.register("gpt-4", {"k1": mock_proxy})
        group = router.resolve("gpt-4")

        # Mark all proxies as unhealthy
        group.healthy_keys.clear()

        with pytest.raises(RuntimeError, match="No healthy proxy"):
            router.select_from_group(group)


class TestModelRouterMarkUnhealthy:
    """Tests for mark_unhealthy method."""

    def test_mark_unhealthy_existing_key(self):
        """Test marking an existing key as unhealthy."""
        router = ModelRouter()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        router.register("gpt-4", {"k1": mock_proxy})
        router.mark_unhealthy("gpt-4", "k1")

        group = router.resolve("gpt-4")
        assert "k1" not in group.healthy_keys

    def test_mark_unhealthy_nonexistent_pattern(self):
        """Test mark_unhealthy with nonexistent pattern (no error)."""
        router = ModelRouter()
        # Should not raise an error
        router.mark_unhealthy("nonexistent-model", "k1")

    def test_mark_unhealthy_nonexistent_key(self):
        """Test mark_unhealthy with nonexistent key in group (no error)."""
        router = ModelRouter()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        router.register("gpt-4", {"k1": mock_proxy})
        # Should not raise an error
        router.mark_unhealthy("gpt-4", "nonexistent_key")

        group = router.resolve("gpt-4")
        assert "k1" in group.healthy_keys


class TestModelRouterMarkHealthy:
    """Tests for mark_healthy method."""

    def test_mark_healthy_existing_key(self):
        """Test marking an existing key as healthy (covers lines 159-161)."""
        router = ModelRouter()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        router.register("gpt-4", {"k1": mock_proxy})

        # First mark as unhealthy
        router.mark_unhealthy("gpt-4", "k1")
        group = router.resolve("gpt-4")
        assert "k1" not in group.healthy_keys

        # Then mark as healthy
        router.mark_healthy("gpt-4", "k1")
        group = router.resolve("gpt-4")
        assert "k1" in group.healthy_keys

    def test_mark_healthy_nonexistent_pattern(self):
        """Test mark_healthy with nonexistent pattern (no error)."""
        router = ModelRouter()
        # Should not raise an error
        router.mark_healthy("nonexistent-model", "k1")

    def test_mark_healthy_nonexistent_key(self):
        """Test mark_healthy with nonexistent key in group (no error)."""
        router = ModelRouter()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        router.register("gpt-4", {"k1": mock_proxy})
        # Should not raise an error
        router.mark_healthy("gpt-4", "nonexistent_key")

        group = router.resolve("gpt-4")
        assert "k1" in group.healthy_keys


class TestModelRouterListRoutes:
    """Tests for list_routes method."""

    def test_list_routes_exact_and_wildcard(self):
        """Test list_routes with both exact and wildcard routes."""
        router = ModelRouter()
        mock_proxy1 = MagicMock(spec=OpenAIChatProxy)
        mock_proxy2 = MagicMock(spec=OpenAIChatProxy)

        # Register exact route
        router.register("gpt-4", {"k1": mock_proxy1})

        # Register wildcard route
        router.register("gpt-*", {"k2": mock_proxy2})

        routes = router.list_routes()

        assert len(routes) == 2
        patterns = [route["pattern"] for route in routes]
        assert "gpt-4" in patterns
        assert "gpt-*" in patterns

        # Verify route info structure
        for route in routes:
            assert "pattern" in route
            assert "strategy" in route
            assert "proxy_count" in route
            assert "healthy_count" in route
            assert "keys" in route

    def test_list_routes_empty(self):
        """Test list_routes returns empty list when no routes."""
        router = ModelRouter()
        routes = router.list_routes()
        assert routes == []

    def test_list_routes_with_healthy_status(self):
        """Test list_routes reflects healthy proxy count correctly."""
        router = ModelRouter()
        mock_proxy1 = MagicMock(spec=OpenAIChatProxy)
        mock_proxy2 = MagicMock(spec=OpenAIChatProxy)

        router.register("gpt-4", {"k1": mock_proxy1, "k2": mock_proxy2})

        routes = router.list_routes()
        assert routes[0]["healthy_count"] == 2

        # Mark one as unhealthy
        router.mark_unhealthy("gpt-4", "k1")

        routes = router.list_routes()
        assert routes[0]["healthy_count"] == 1

    def test_list_routes_with_different_strategies(self):
        """Test list_routes shows correct strategy for each route."""
        router = ModelRouter()
        mock_proxy = MagicMock(spec=OpenAIChatProxy)

        router.register(
            "gpt-4",
            {"k1": mock_proxy},
            strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN,
        )
        router.register(
            "gpt-3.5",
            {"k2": mock_proxy},
            strategy=LoadBalanceStrategy.LEAST_CONNECTIONS,
        )

        routes = router.list_routes()
        strategies = [route["strategy"] for route in routes]

        assert "weighted_round_robin" in strategies
        assert "least_connections" in strategies
