"""Model-based routing for directing requests to specific proxy groups."""

import fnmatch
import threading
from dataclasses import dataclass, field
from typing import Optional

from qreward.client.load_balancer import (
    LoadBalanceStrategy,
    RoundRobinSelector,
    WeightedRoundRobinSelector,
)
from qreward.client.openai import OpenAIChatProxy


@dataclass
class ProxyGroup:
    """A group of proxies serving a specific model or model pattern.

    Attributes:
        pattern: Model name or glob pattern (e.g. "gpt-4" or "gpt-*").
        proxies: Mapping of key → proxy instance.
        insertion_order: Keys in insertion order for round-robin.
        healthy_keys: Set of currently healthy proxy keys.
        weights: Per-key weights for weighted round-robin.
        strategy: Load balancing strategy for this group.
    """

    pattern: str
    proxies: dict[str, OpenAIChatProxy] = field(default_factory=dict)
    insertion_order: list[str] = field(default_factory=list)
    healthy_keys: set[str] = field(default_factory=set)
    weights: dict[str, int] = field(default_factory=dict)
    strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN
    rr_selector: RoundRobinSelector = field(default_factory=RoundRobinSelector)
    wrr_selector: WeightedRoundRobinSelector = field(
        default_factory=WeightedRoundRobinSelector
    )


class ModelRouter:
    """Routes model names to dedicated proxy groups.

    Matching priority: exact match → glob/wildcard match → None (fallback).

    Example:
        >>> router = ModelRouter()
        >>> router.register("gpt-4", group)
        >>> router.register("gpt-*", wildcard_group)
        >>> router.resolve("gpt-4")       # exact match
        >>> router.resolve("gpt-3.5")     # wildcard match
        >>> router.resolve("claude-3")    # None (no match)
    """

    def __init__(self) -> None:
        self._exact: dict[str, ProxyGroup] = {}
        self._wildcards: list[ProxyGroup] = []
        self._lock = threading.Lock()

    def register(
        self,
        pattern: str,
        proxy_map: dict[str, OpenAIChatProxy],
        weights: Optional[dict[str, int]] = None,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN,
    ) -> None:
        """Register a proxy group for a model pattern.

        Args:
            pattern: Exact model name or glob pattern (e.g. "gpt-*").
            proxy_map: Mapping of key → OpenAIChatProxy.
            weights: Optional per-key weights for weighted round-robin.
            strategy: Load balancing strategy for this group.
        """
        group = ProxyGroup(
            pattern=pattern,
            proxies=dict(proxy_map),
            insertion_order=list(proxy_map.keys()),
            healthy_keys=set(proxy_map.keys()),
            weights=weights or {k: 1 for k in proxy_map},
            strategy=strategy,
        )
        group.wrr_selector.update_weights(group.weights)

        with self._lock:
            if _is_glob_pattern(pattern):
                self._wildcards.append(group)
            else:
                self._exact[pattern] = group

    def resolve(self, model: str) -> Optional[ProxyGroup]:
        """Find the best matching proxy group for a model name.

        Args:
            model: The model name to route.

        Returns:
            Matching ProxyGroup or None if no route matches.
        """
        with self._lock:
            if model in self._exact:
                return self._exact[model]
            for group in self._wildcards:
                if fnmatch.fnmatch(model, group.pattern):
                    return group
        return None

    def select_from_group(self, group: ProxyGroup) -> OpenAIChatProxy:
        """Select a proxy from a group using its load balancing strategy.

        Args:
            group: The proxy group to select from.

        Returns:
            Selected OpenAIChatProxy instance.

        Raises:
            RuntimeError: When no healthy proxy is available in the group.
        """
        selected_key: Optional[str] = None

        if group.strategy == LoadBalanceStrategy.ROUND_ROBIN:
            selected_key = group.rr_selector.select(
                group.insertion_order, group.healthy_keys
            )
        elif group.strategy == LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN:
            selected_key = group.wrr_selector.select(
                group.insertion_order, group.healthy_keys, group.weights
            )
        elif group.strategy == LoadBalanceStrategy.LEAST_CONNECTIONS:
            selected_key = group.rr_selector.select(
                group.insertion_order, group.healthy_keys
            )

        if selected_key is None:
            raise RuntimeError(
                f"No healthy proxy in group '{group.pattern}'."
            )
        return group.proxies[selected_key]

    def mark_unhealthy(self, pattern: str, key: str) -> None:
        """Mark a proxy as unhealthy within a specific group.

        Args:
            pattern: The group pattern.
            key: The proxy key within the group.
        """
        group = self._find_group(pattern)
        if group and key in group.proxies:
            group.healthy_keys.discard(key)

    def mark_healthy(self, pattern: str, key: str) -> None:
        """Mark a proxy as healthy within a specific group.

        Args:
            pattern: The group pattern.
            key: The proxy key within the group.
        """
        group = self._find_group(pattern)
        if group and key in group.proxies:
            group.healthy_keys.add(key)

    def list_routes(self) -> list[dict]:
        """List all registered routes with their status.

        Returns:
            List of dicts with pattern, strategy, proxy_count, healthy_count.
        """
        routes = []
        with self._lock:
            for pattern, group in self._exact.items():
                routes.append(self._group_info(group))
            for group in self._wildcards:
                routes.append(self._group_info(group))
        return routes

    def _find_group(self, pattern: str) -> Optional[ProxyGroup]:
        """Find a group by its exact pattern string."""
        with self._lock:
            if pattern in self._exact:
                return self._exact[pattern]
            for group in self._wildcards:
                if group.pattern == pattern:
                    return group
        return None

    @staticmethod
    def _group_info(group: ProxyGroup) -> dict:
        """Build info dict for a proxy group."""
        return {
            "pattern": group.pattern,
            "strategy": group.strategy.value,
            "proxy_count": len(group.proxies),
            "healthy_count": len(group.healthy_keys),
            "keys": list(group.proxies.keys()),
        }


def _is_glob_pattern(pattern: str) -> bool:
    """Check if a pattern contains glob wildcards."""
    return any(char in pattern for char in ("*", "?", "["))
