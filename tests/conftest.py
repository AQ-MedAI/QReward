"""Shared test fixtures for the QReward test suite."""

import pytest

from qreward.client import OpenAIChatProxy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_BASE_URL = "http://fake"
TEST_API_KEY = "abc"


# ---------------------------------------------------------------------------
# OpenAIChatProxy fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def proxy():
    """Create a default OpenAIChatProxy instance for testing."""
    return OpenAIChatProxy(base_url=TEST_BASE_URL, api_key=TEST_API_KEY)


@pytest.fixture
def debug_proxy():
    """Create an OpenAIChatProxy instance with debug mode enabled."""
    return OpenAIChatProxy(
        base_url=TEST_BASE_URL,
        api_key=TEST_API_KEY,
        debug=True,
    )
