"""Model Router Example

Demonstrates how to route requests to different proxy groups based on the
model name. This is useful when you have different API endpoints for
different models (e.g., GPT-4 on one service, DeepSeek on another).

Features:
  - Exact model name matching (e.g., "gpt-4")
  - Wildcard/glob pattern matching (e.g., "gpt-*", "deepseek-*")
  - Per-group load balancing strategy
  - Per-group health management
  - Integration with OpenAIChatProxyManager

NOTE: This example demonstrates the routing logic which works without
an API key. Actual API calls require valid endpoints and credentials.
"""

from qreward.client import LoadBalanceStrategy, OpenAIChatProxy, OpenAIChatProxyManager
from qreward.client.model_router import ModelRouter


# --- Example 1: Basic Model Routing ---
def demo_basic_routing():
    print("=== Basic Model Routing ===\n")

    router = ModelRouter()

    # Register exact model routes
    router.register(
        "gpt-4",
        proxy_map={
            "openai-1": OpenAIChatProxy(base_url="http://openai-1.example.com/v1", api_key="sk-1"),
            "openai-2": OpenAIChatProxy(base_url="http://openai-2.example.com/v1", api_key="sk-2"),
        },
    )

    router.register(
        "deepseek-r1",
        proxy_map={
            "ds-1": OpenAIChatProxy(base_url="http://deepseek-1.example.com/v1", api_key="sk-ds"),
        },
    )

    # Resolve routes
    gpt4_group = router.resolve("gpt-4")
    deepseek_group = router.resolve("deepseek-r1")
    unknown_group = router.resolve("claude-3")

    print(f"  gpt-4 → {gpt4_group.pattern if gpt4_group else None}")
    print(f"  deepseek-r1 → {deepseek_group.pattern if deepseek_group else None}")
    print(f"  claude-3 → {unknown_group}")
    print()


# --- Example 2: Wildcard Pattern Matching ---
def demo_wildcard_routing():
    print("=== Wildcard Pattern Matching ===\n")

    router = ModelRouter()

    # Register wildcard patterns
    router.register(
        "gpt-*",
        proxy_map={
            "openai": OpenAIChatProxy(base_url="http://openai.example.com/v1", api_key="sk-openai"),
        },
    )

    router.register(
        "deepseek-*",
        proxy_map={
            "ds": OpenAIChatProxy(base_url="http://deepseek.example.com/v1", api_key="sk-ds"),
        },
    )

    # All gpt-* models route to the same group
    models_to_test = ["gpt-4", "gpt-3.5-turbo", "gpt-4o", "deepseek-r1", "deepseek-v2", "llama-3"]
    for model in models_to_test:
        group = router.resolve(model)
        result = group.pattern if group else "no match"
        print(f"  {model:20s} → {result}")
    print()


# --- Example 3: Exact Match Takes Priority ---
def demo_exact_priority():
    print("=== Exact Match Priority ===\n")

    router = ModelRouter()

    # Register both exact and wildcard
    router.register(
        "gpt-4",
        proxy_map={
            "premium": OpenAIChatProxy(base_url="http://premium.example.com/v1", api_key="sk-premium"),
        },
    )
    router.register(
        "gpt-*",
        proxy_map={
            "standard": OpenAIChatProxy(base_url="http://standard.example.com/v1", api_key="sk-std"),
        },
    )

    # gpt-4 matches exact route, gpt-3.5 matches wildcard
    gpt4 = router.resolve("gpt-4")
    gpt35 = router.resolve("gpt-3.5-turbo")

    print(f"  gpt-4       → keys: {list(gpt4.proxies.keys()) if gpt4 else None}")
    print(f"  gpt-3.5     → keys: {list(gpt35.proxies.keys()) if gpt35 else None}")
    print(f"  (gpt-4 uses 'premium', gpt-3.5 falls back to wildcard 'standard')\n")


# --- Example 4: Per-Group Load Balancing ---
def demo_per_group_lb():
    print("=== Per-Group Load Balancing ===\n")

    router = ModelRouter()

    # GPT-4 uses weighted round-robin (premium endpoint gets more traffic)
    router.register(
        "gpt-4",
        proxy_map={
            "premium": OpenAIChatProxy(base_url="http://premium.example.com/v1", api_key="sk-p"),
            "standard": OpenAIChatProxy(base_url="http://standard.example.com/v1", api_key="sk-s"),
        },
        weights={"premium": 3, "standard": 1},
        strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN,
    )

    group = router.resolve("gpt-4")
    counts = {"premium": 0, "standard": 0}
    for _ in range(8):
        proxy = router.select_from_group(group)
        for key, p in group.proxies.items():
            if p is proxy:
                counts[key] += 1
                break

    print(f"  Selection counts over 8 calls: {counts}")
    print(f"  (Premium gets ~3x traffic due to weight=3)\n")


# --- Example 5: Health Management per Group ---
def demo_group_health():
    print("=== Per-Group Health Management ===\n")

    router = ModelRouter()
    router.register(
        "gpt-4",
        proxy_map={
            "east": OpenAIChatProxy(base_url="http://east.example.com/v1", api_key="sk-e"),
            "west": OpenAIChatProxy(base_url="http://west.example.com/v1", api_key="sk-w"),
        },
    )

    group = router.resolve("gpt-4")
    print(f"  Healthy keys: {group.healthy_keys}")

    # Mark east as unhealthy
    router.mark_unhealthy("gpt-4", "east")
    print(f"  After east failure: {group.healthy_keys}")

    # All selections go to west
    proxy = router.select_from_group(group)
    for key, p in group.proxies.items():
        if p is proxy:
            print(f"  Selected: {key}")

    # Recover east
    router.mark_healthy("gpt-4", "east")
    print(f"  After recovery: {group.healthy_keys}\n")


# --- Example 6: Integration with ProxyManager ---
def demo_manager_integration():
    print("=== ProxyManager + Model Router ===\n")

    manager = OpenAIChatProxyManager()

    # Add default proxies
    manager.add_proxy(
        "default",
        OpenAIChatProxy(base_url="http://default.example.com/v1", api_key="sk-default"),
    )

    # Register model-specific routes
    manager.register_model_route(
        "gpt-4",
        proxy_map={
            "gpt4-svc": OpenAIChatProxy(base_url="http://gpt4.example.com/v1", api_key="sk-gpt4"),
        },
    )
    manager.register_model_route(
        "deepseek-*",
        proxy_map={
            "ds-svc": OpenAIChatProxy(base_url="http://ds.example.com/v1", api_key="sk-ds"),
        },
    )

    # List all routes
    routes = manager.list_routes()
    for route in routes:
        print(f"  Route: {route['pattern']} ({route['strategy']}) "
              f"- {route['proxy_count']} proxies, {route['healthy_count']} healthy")

    # select_proxy with model uses the router
    # select_proxy without model uses the default pool
    print(f"\n  Default proxies: {list(manager.proxies().keys())}")
    print(f"  Model routes: {len(routes)}\n")


if __name__ == "__main__":
    demo_basic_routing()
    demo_wildcard_routing()
    demo_exact_priority()
    demo_per_group_lb()
    demo_group_health()
    demo_manager_integration()
