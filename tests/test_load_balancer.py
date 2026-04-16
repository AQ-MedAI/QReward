"""Tests for load_balancer module."""

from qreward.client.load_balancer import (
    RoundRobinSelector,
    WeightedRoundRobinSelector,
)


class TestRoundRobinSelector:
    """Test cases for RoundRobinSelector."""

    def test_select_empty_keys_returns_none(self):
        """Test that select returns None when keys is empty."""
        selector = RoundRobinSelector()
        result = selector.select([], {"a", "b"})
        assert result is None

    def test_select_empty_healthy_keys_returns_none(self):
        """Test that select returns None when healthy_keys is empty."""
        selector = RoundRobinSelector()
        result = selector.select(["a", "b"], set())
        assert result is None

    def test_select_all_unhealthy_returns_none(self):
        """Test that select returns None when all keys are unhealthy."""
        selector = RoundRobinSelector()
        result = selector.select(["a", "b"], {"c"})
        assert result is None

    def test_select_normal_round_robin(self):
        """Test normal round-robin selection."""
        selector = RoundRobinSelector()
        keys = ["a", "b", "c"]
        healthy_keys = {"a", "b", "c"}

        # Test round-robin order
        assert selector.select(keys, healthy_keys) == "a"
        assert selector.select(keys, healthy_keys) == "b"
        assert selector.select(keys, healthy_keys) == "c"
        assert selector.select(keys, healthy_keys) == "a"

    def test_select_skips_unhealthy(self):
        """Test that select skips unhealthy keys."""
        selector = RoundRobinSelector()
        keys = ["a", "b", "c"]
        healthy_keys = {"a", "c"}

        # 'b' is unhealthy, should be skipped
        assert selector.select(keys, healthy_keys) == "a"
        assert selector.select(keys, healthy_keys) == "c"
        assert selector.select(keys, healthy_keys) == "a"


class TestWeightedRoundRobinSelector:
    """Test cases for WeightedRoundRobinSelector."""

    def test_select_empty_keys_returns_none(self):
        """Test that select returns None when keys is empty."""
        selector = WeightedRoundRobinSelector()
        result = selector.select([], {"a", "b"}, {"a": 1, "b": 1})
        assert result is None

    def test_select_empty_healthy_returns_none(self):
        """Test that select returns None when healthy_keys is empty."""
        selector = WeightedRoundRobinSelector()
        result = selector.select(["a", "b"], set(), {"a": 1, "b": 1})
        assert result is None

    def test_select_no_eligible_returns_none(self):
        """Test that select returns None when
        no eligible keys (keys not in weights)."""
        selector = WeightedRoundRobinSelector()
        keys = ["a"]
        healthy_keys = {"a"}
        weights = {"b": 1}

        result = selector.select(keys, healthy_keys, weights)
        assert result is None

    def test_select_weighted_distribution(self):
        """Test that weighted distribution works correctly."""
        selector = WeightedRoundRobinSelector()
        keys = ["a", "b", "c"]
        healthy_keys = {"a", "b", "c"}
        weights = {"a": 5, "b": 3, "c": 2}

        # With weights 5:3:2, 'a' should be selected most frequently
        results = {"a": 0, "b": 0, "c": 0}
        for _ in range(100):
            selected = selector.select(keys, healthy_keys, weights)
            results[selected] += 1

        # 'a' should have the most selections
        assert results["a"] > results["b"]
        assert results["a"] > results["c"]

    def test_update_weights_adds_new_keys(self):
        """Test that update_weights adds new keys."""
        selector = WeightedRoundRobinSelector()
        selector.update_weights({"a": 1, "b": 2})

        # Add a new key
        selector.update_weights({"a": 1, "b": 2, "c": 3})

        keys = ["a", "b", "c"]
        healthy_keys = {"a", "b", "c"}
        weights = {"a": 1, "b": 2, "c": 3}

        result = selector.select(keys, healthy_keys, weights)
        assert result in keys

    def test_update_weights_removes_old_keys(self):
        """Test that update_weights removes old keys."""
        selector = WeightedRoundRobinSelector()
        selector.update_weights({"a": 1, "b": 2, "c": 3})

        # Remove 'c'
        selector.update_weights({"a": 1, "b": 2})

        keys = ["a", "b", "c"]
        healthy_keys = {"a", "b", "c"}
        weights = {"a": 1, "b": 2}

        # 'c' should not be selected since it's not in weights
        for _ in range(10):
            result = selector.select(keys, healthy_keys, weights)
            assert result in ["a", "b"]
