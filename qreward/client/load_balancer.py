"""Load balancing strategies for proxy selection."""

import threading
from enum import Enum
from typing import List, Optional


class LoadBalanceStrategy(Enum):
    """Load balancing strategy enumeration."""

    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"


class RoundRobinSelector:
    """Thread-safe round-robin selector over a list of keys.

    Skips keys that are marked unhealthy.
    """

    def __init__(self) -> None:
        self._index = 0
        self._lock = threading.Lock()

    def select(
        self, keys: List[str], healthy_keys: set[str]
    ) -> Optional[str]:
        """Select the next healthy key in round-robin order.

        Args:
            keys: Ordered list of all proxy keys.
            healthy_keys: Set of keys currently considered healthy.

        Returns:
            The selected key, or None if no healthy key exists.
        """
        if not keys or not healthy_keys:
            return None

        with self._lock:
            total = len(keys)
            for _ in range(total):
                key = keys[self._index % total]
                self._index += 1
                if key in healthy_keys:
                    return key

        return None


class WeightedRoundRobinSelector:
    """Thread-safe weighted round-robin selector.

    Keys with higher weights are selected more frequently.
    Uses the smooth weighted round-robin algorithm (Nginx-style).
    """

    def __init__(self) -> None:
        self._current_weights: dict[str, int] = {}
        self._lock = threading.Lock()

    def update_weights(self, weights: dict[str, int]) -> None:
        """Update the weight configuration.

        Args:
            weights: Mapping of key to weight (positive integer).
        """
        with self._lock:
            for key in weights:
                if key not in self._current_weights:
                    self._current_weights[key] = 0
            removed = set(self._current_weights) - set(weights)
            for key in removed:
                del self._current_weights[key]

    def select(
        self,
        keys: List[str],
        healthy_keys: set[str],
        weights: dict[str, int],
    ) -> Optional[str]:
        """Select the next healthy key using smooth weighted round-robin.

        Args:
            keys: Ordered list of all proxy keys.
            healthy_keys: Set of keys currently considered healthy.
            weights: Mapping of key to weight.

        Returns:
            The selected key, or None if no healthy key exists.
        """
        if not keys or not healthy_keys:
            return None

        with self._lock:
            eligible = [k for k in keys if k in healthy_keys and k in weights]
            if not eligible:
                return None

            total_weight = sum(weights[k] for k in eligible)

            # Increase current weights by effective weight
            for key in eligible:
                self._current_weights.setdefault(key, 0)
                self._current_weights[key] += weights[key]

            # Select the key with the highest current weight
            best_key = max(eligible, key=lambda k: self._current_weights[k])

            # Decrease the selected key's current weight
            self._current_weights[best_key] -= total_weight

            return best_key
