"""Load Balancer & Failover Example

Demonstrates how to use OpenAIChatProxyManager with different load balancing
strategies and health-based failover.

Supported strategies:
  - ROUND_ROBIN:          Cycle through proxies in order (default)
  - WEIGHTED_ROUND_ROBIN: Prefer proxies with higher weights
  - LEAST_CONNECTIONS:    Select the least-loaded proxy

Health management:
  - mark_unhealthy(key): Remove a proxy from the selection pool
  - mark_healthy(key):   Add a proxy back to the selection pool
  - healthy_proxies():   Get all currently healthy proxies

NOTE: This example demonstrates the management layer (proxy selection,
health tracking) which works without an API key. Actual API calls
require setting OPENAI_API_BASE and OPENAI_API_KEY environment variables.
"""

import os

from qreward.client import LoadBalanceStrategy, OpenAIChatProxy, OpenAIChatProxyManager


# --- Example 1: Round-Robin Load Balancing ---
def demo_round_robin():
    print("=== Round-Robin Load Balancing ===\n")

    manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.ROUND_ROBIN)

    # Add multiple proxies (simulating different API endpoints)
    for i in range(3):
        manager.add_proxy(
            key=f"endpoint_{i}",
            proxy=OpenAIChatProxy(
                base_url=f"http://api-{i}.example.com/v1",
                api_key="sk-placeholder",
            ),
        )

    # Round-robin selection cycles through all proxies
    selected_keys = []
    for _ in range(6):
        proxy = manager.select_proxy()
        # Find which key was selected
        for key, p in manager.proxies().items():
            if p is proxy:
                selected_keys.append(key)
                break

    print(f"  Selection order: {selected_keys}")
    print(f"  (Cycles through all 3 endpoints evenly)\n")


# --- Example 2: Weighted Round-Robin ---
def demo_weighted_round_robin():
    print("=== Weighted Round-Robin ===\n")

    manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN)

    # Add proxies with different weights
    # "primary" gets 3x more traffic than "secondary"
    manager.add_proxy(
        key="primary",
        proxy=OpenAIChatProxy(base_url="http://primary.example.com/v1", api_key="sk-placeholder"),
        weight=3,
    )
    manager.add_proxy(
        key="secondary",
        proxy=OpenAIChatProxy(base_url="http://secondary.example.com/v1", api_key="sk-placeholder"),
        weight=1,
    )

    # Track selection distribution
    counts = {"primary": 0, "secondary": 0}
    for _ in range(8):
        proxy = manager.select_proxy()
        for key, p in manager.proxies().items():
            if p is proxy:
                counts[key] += 1
                break

    print(f"  Selection counts over 8 calls: {counts}")
    print(f"  (Primary gets ~3x more traffic than secondary)\n")


# --- Example 3: Health-Based Failover ---
def demo_failover():
    print("=== Health-Based Failover ===\n")

    manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.ROUND_ROBIN)
    manager.add_proxy(
        key="us-east",
        proxy=OpenAIChatProxy(base_url="http://us-east.example.com/v1", api_key="sk-placeholder"),
    )
    manager.add_proxy(
        key="us-west",
        proxy=OpenAIChatProxy(base_url="http://us-west.example.com/v1", api_key="sk-placeholder"),
    )
    manager.add_proxy(
        key="eu-west",
        proxy=OpenAIChatProxy(base_url="http://eu-west.example.com/v1", api_key="sk-placeholder"),
    )

    print(f"  All healthy: {list(manager.healthy_proxies().keys())}")

    # Simulate us-east going down
    manager.mark_unhealthy("us-east")
    print(f"  After us-east failure: {list(manager.healthy_proxies().keys())}")

    # Selections now skip us-east
    selected = []
    for _ in range(4):
        proxy = manager.select_proxy()
        for key, p in manager.proxies().items():
            if p is proxy:
                selected.append(key)
                break
    print(f"  Selections (us-east down): {selected}")

    # Recover us-east
    manager.mark_healthy("us-east")
    print(f"  After recovery: {list(manager.healthy_proxies().keys())}\n")


# --- Example 4: Chain-style API ---
def demo_chain_api():
    print("=== Chain-Style Proxy Setup ===\n")

    manager = (
        OpenAIChatProxyManager(strategy=LoadBalanceStrategy.ROUND_ROBIN)
        .add_proxy_with_default("svc-a", "http://a.example.com/v1", "sk-aaa")
        .add_proxy_with_default("svc-b", "http://b.example.com/v1", "sk-bbb")
        .add_proxy_with_default("svc-c", "http://c.example.com/v1", "sk-ccc")
    )

    print(f"  Registered proxies: {list(manager.proxies().keys())}")
    print(f"  All healthy: {manager.exist_proxy('svc-a')}\n")


# --- Example 5: No healthy proxy error ---
def demo_no_healthy_proxy():
    print("=== No Healthy Proxy Error ===\n")

    manager = OpenAIChatProxyManager()
    manager.add_proxy(
        key="only-one",
        proxy=OpenAIChatProxy(base_url="http://only.example.com/v1", api_key="sk-placeholder"),
    )

    manager.mark_unhealthy("only-one")

    try:
        manager.select_proxy()
    except RuntimeError as exc:
        print(f"  Error: {exc}")
        print(f"  (All proxies are unhealthy, selection fails)\n")


if __name__ == "__main__":
    demo_round_robin()
    demo_weighted_round_robin()
    demo_failover()
    demo_chain_api()
    demo_no_healthy_proxy()
