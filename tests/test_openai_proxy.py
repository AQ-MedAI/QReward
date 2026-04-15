import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from qreward.client import (
    LoadBalanceStrategy,
    OpenAIChatProxy,
    OpenAIChatProxyManager,
)


from tests.conftest import TEST_BASE_URL as TEST_URL, TEST_API_KEY


def test_get_openai_key_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env_key_123")
    assert OpenAIChatProxy.get_openai_key() == "env_key_123"


def test_with_methods(proxy):
    assert proxy.with_max_concurrent(10)._max_concurrent == 10
    assert proxy.with_temperature(0.9)._default_temperature == 0.9
    assert proxy.with_timeout(99)._default_timeout == 99

    def dummy_error_func(e):
        return str(e)

    assert (
        proxy.with_error_process_func(
            error_process_func=dummy_error_func,
        )._default_error_process_func
        == dummy_error_func
    )


def test_httpx_add_hook():

    async def update_path(request) -> None:
        if request.url.path in ["/embeddings"]:
            request.url = request.url.copy_with(
                path="/v1/embeddings",
            )

    async def update_resp(response) -> None:
        print(response.status_code)

    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        httpx_request_hook=update_path,
        httpx_response_hook=update_resp,
    )

    assert len(proxy.client._client.event_hooks.get("request")) == 1
    assert len(proxy.client._client.event_hooks.get("response")) == 1
    assert proxy.client._client.event_hooks.get("request")[0] == update_path
    assert proxy.client._client.event_hooks.get("response")[0] == update_resp


def test_proxy_add_patch():
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        is_hack_embedding_method=True,
    )
    proxy._is_hack_embedding = True


@pytest.mark.asyncio
async def test_chat_completion_success(proxy, monkeypatch):
    completion_mock = MagicMock()
    completion_mock.choices = [
        MagicMock(message=MagicMock(content="Hello world")),
    ]

    # mock async call
    proxy.client.chat.completions.create = AsyncMock(
        return_value=completion_mock,
    )

    result = await proxy.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
    )
    assert result == "Hello world"


@pytest.mark.asyncio
async def test_chat_completion_with_custom_processing(proxy, monkeypatch):

    completion_mock = MagicMock()
    completion_mock.choices = [MagicMock(message=MagicMock(content="Hello"))]

    # 使用自定义处理函数
    def process_func(resp):
        return resp  # 这里可以做额外处理

    proxy._default_chat_process_func = process_func

    proxy.client.chat.completions.create = AsyncMock(
        return_value=completion_mock,
    )

    result = await proxy.chat_completion(messages=[], model="test")
    assert result == "Hello"


@pytest.mark.asyncio
async def test_batch_chat_completion(proxy, monkeypatch):
    proxy.chat_completion = AsyncMock(side_effect=["msg1", "msg2"])

    batch_messages = [
        [{"role": "user", "content": "hi"}],
        [{"role": "user", "content": "hello"}],
    ]
    results = await proxy.batch_chat_completion(
        batch_messages=batch_messages,
        model="model-x",
    )
    assert results == ["msg1", "msg2"]


@pytest.mark.asyncio
async def test_embeddings_with_openai(proxy, monkeypatch):
    emb_mock = MagicMock()
    emb_mock.data = [{"embedding": [0.1, 0.2]}]
    proxy.client.embeddings.create = AsyncMock(return_value=emb_mock)

    res = await proxy.embeddings(sentences=["hello"], model="embedding-model")
    assert res == [{"embedding": [0.1, 0.2]}]


@pytest.mark.asyncio
async def test_batch_embeddings(proxy, monkeypatch):
    proxy.embeddings = AsyncMock(side_effect=[["embed1"], ["embed2"]])

    res = await proxy.batch_embeddings(
        batch_sentences=[["a"], ["b"]],
        model="emb-model",
    )
    assert res == [["embed1"], ["embed2"]]


@pytest.mark.asyncio
async def test_embeddings_debug_print(caplog):
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.client.openai"):
        proxy = OpenAIChatProxy(
            base_url=TEST_URL,
            api_key=TEST_API_KEY,
            debug=True,
        )
        emb_mock = MagicMock()
        emb_mock.data = [{"embedding": [0.1, 0.2]}]
        proxy.client.embeddings.create = AsyncMock(return_value=emb_mock)

        await proxy.embeddings(sentences=["hello"], model="embedding-model")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Begin" in r.message and "embedding-model" in r.message for r in debug_records)
    assert any("End" in r.message and "embedding-model" in r.message for r in debug_records)


@pytest.mark.asyncio
async def test_async_context_manager(proxy, monkeypatch):

    # mock close 方法，避免真实资源释放
    proxy.client.close = AsyncMock()

    async with proxy as instance:
        # 验证 __aenter__ 返回的是自身
        assert instance is proxy

    # 验证 __aexit__ 调用了 client.close()
    proxy.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_async_context_manager_with_exception(proxy):
    proxy.client.close = AsyncMock()

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        async with proxy:
            raise CustomError("boom")


@pytest.mark.asyncio
async def test_chat_completion_debug_print(caplog):
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.client.openai"):
        proxy = OpenAIChatProxy(
            base_url=TEST_URL,
            api_key=TEST_API_KEY,
            debug=True,
        )

        # 构造一个假的 ChatCompletion 响应
        completion_mock = type("MockCompletion", (), {})()
        completion_mock.choices = [
            type("Choice", (), {"message": type("Msg", (), {"content": "Hi"})()})()
        ]

        proxy.client.chat.completions.create = AsyncMock(
            return_value=completion_mock,
        )

        result = await proxy.chat_completion(
            messages=[{"role": "user", "content": "hello"}], model="test-model"
        )
        assert result == "Hi"

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Begin" in r.message and "test-model" in r.message for r in debug_records)
    assert any("End" in r.message and "test-model" in r.message for r in debug_records)


@pytest.mark.asyncio
async def test_batch_chat_completion_error_process():
    # 构造一个假的 error_process_fuc，用于检测是否调用
    def fake_error_process_func(exc):
        return f"processed: {exc}"

    # 实例化代理对象（用假的 base_url 和 api_key）
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        error_process_func=fake_error_process_func,
    )

    # 模拟 chat_completion 总是返回一个异常对象
    async def fake_chat_completion(*args, **kwargs):
        return Exception("boom")

    proxy.chat_completion = fake_chat_completion

    # 准备一批消息（这里只有一条）
    batch_messages = [[{"role": "user", "content": "Hello"}]]

    # 调用 batch_chat_completion
    results = await proxy.batch_chat_completion(
        batch_messages=batch_messages, model="gpt-test"
    )

    # 验证结果是 error_process_fuc 处理过的字符串
    assert results == ["processed: boom"]


@pytest.mark.asyncio
async def test_embeddings_retry_on_api_error(proxy, monkeypatch):
    """验证 embeddings 方法对 _ERROR_GROUP 中的异常触发 @retry 重试。

    修复前：embeddings 方法裸捕获 Exception 并返回 []，@retry 对非 TimeoutError 不生效。
    修复后：移除 try-except，@retry 装饰器直接处理 _ERROR_GROUP 中的异常重试。
    """
    from openai import RateLimitError
    from unittest.mock import MagicMock
    import httpx

    call_count = 0

    async def fake_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            mock_response = httpx.Response(
                status_code=429,
                request=httpx.Request("POST", "http://fake/embeddings"),
            )
            raise RateLimitError(
                message="Rate limit exceeded",
                response=mock_response,
                body=None,
            )
        result = MagicMock()
        result.data = [{"embedding": [0.1, 0.2]}]
        return result

    monkeypatch.setattr(proxy.client.embeddings, "create", fake_create)

    result = await proxy.embeddings(
        sentences=["test sentence"],
        model="text-embedding-model",
    )
    assert result == [{"embedding": [0.1, 0.2]}]
    assert call_count == 3


@pytest.mark.asyncio
async def test_embeddings_propagates_non_retryable_exception(proxy, monkeypatch):
    """验证 embeddings 方法对非 _ERROR_GROUP 异常直接抛出，不再静默返回 []。"""

    async def fake_create(*args, **kwargs):
        raise ValueError("unexpected error")

    monkeypatch.setattr(proxy.client.embeddings, "create", fake_create)

    with pytest.raises(ValueError, match="unexpected error"):
        await proxy.embeddings(
            sentences=["test sentence"],
            model="text-embedding-model",
        )


@pytest.mark.asyncio
async def test_batch_chat_completion_partial_failure(proxy):
    """验证 batch_chat_completion 部分失败不影响其他任务。

    修复前：asyncio.gather 未设置 return_exceptions=True，单个任务异常导致整批失败。
    修复后：asyncio.gather(*tasks, return_exceptions=True)，部分失败不影响其他任务。
    """

    call_count = 0

    async def fake_chat_completion(messages, model, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError("task 2 failed")
        return f"result_{call_count}"

    proxy.chat_completion = fake_chat_completion

    batch_messages = [
        [{"role": "user", "content": "msg1"}],
        [{"role": "user", "content": "msg2"}],
        [{"role": "user", "content": "msg3"}],
    ]

    results = await proxy.batch_chat_completion(
        batch_messages=batch_messages, model="gpt-test"
    )

    assert len(results) == 3
    assert results[0] == "result_1"
    assert isinstance(results[1], ValueError)
    assert results[2] == "result_3"


@pytest.mark.asyncio
async def test_batch_chat_completion_error_process_with_return_exceptions():
    """验证 error_process_fuc 在 return_exceptions=True 下正常执行。"""

    def fake_error_handler(exc):
        return f"handled: {exc}"

    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        error_process_func=fake_error_handler,
    )

    async def fake_chat_completion(messages, model, **kwargs):
        raise RuntimeError("boom")

    proxy.chat_completion = fake_chat_completion

    batch_messages = [[{"role": "user", "content": "Hello"}]]
    results = await proxy.batch_chat_completion(
        batch_messages=batch_messages, model="gpt-test"
    )

    assert len(results) == 1
    assert results[0] == "handled: boom"


class DummyClient:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class DummyProxy:
    def __init__(self):
        self.client = DummyClient()


@pytest.mark.asyncio
async def test_add_and_proxy_methods(monkeypatch):
    manager = OpenAIChatProxyManager()

    dummy = DummyProxy()

    # add_proxy 正常路径
    ret = manager.add_proxy("p1", dummy)
    assert ret is manager
    assert manager.proxy("p1") is dummy
    assert manager.exist_proxy("p1") is True

    # add_proxy 重复添加触发异常
    with pytest.raises(ValueError):
        manager.add_proxy("p1", dummy)

    # 获取不存在的代理触发 KeyError
    with pytest.raises(KeyError):
        manager.proxy("no_such_key")

    # remove_proxy 正常关闭
    assert not dummy.client.closed
    await manager.remove_proxy("p1")
    assert dummy.client.closed
    # 删除不存在的代理，不报错
    await manager.remove_proxy("p1")


@pytest.mark.asyncio
async def test_add_proxy_with_default_and_batch(monkeypatch):
    manager = OpenAIChatProxyManager()

    # 单个添加
    ret = manager.add_proxy_with_default("k1", "url1", "key1")
    assert ret is manager
    assert manager.exist_proxy("k1")
    assert manager.proxy("k1").client.base_url == "url1/"

    # proxies() 方法多代理场景
    all_proxies = manager.proxies()
    assert set(all_proxies.keys()) == {"k1"}

    # 批量添加
    proxies_info = {
        "k2": ("url2", "key2"),
        "k3": ("url3", "key3"),
    }
    ret = manager.add_proxies_with_default(proxies_info)
    assert ret is manager
    assert manager.exist_proxy("k2")
    assert manager.exist_proxy("k3")
    assert manager.proxy("k2").client.api_key == "key2"

    # close 所有代理
    await manager.close()
    for proxy in manager._proxies.values():
        assert proxy.client.closed

    assert manager._proxies == {}


# ============================================================
# Sprint 4: batch exception logging + lazy patch tests
# ============================================================

import logging


@pytest.mark.asyncio
async def test_batch_chat_completion_exception_logging(caplog):
    """Verify batch_chat_completion logs warnings for failed tasks."""
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
    )

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "ok"

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_completion
        raise ValueError("simulated failure")

    with patch.object(
        proxy.client.chat.completions,
        "create",
        side_effect=mock_create,
    ):
        with caplog.at_level(logging.WARNING, logger="qreward.client.openai"):
            results = await proxy.batch_chat_completion(
                batch_messages=[
                    [{"role": "user", "content": "hi"}],
                    [{"role": "user", "content": "fail"}],
                ],
                model="test-model",
            )

    assert len(results) == 2
    assert results[0] == "ok"
    assert isinstance(results[1], ValueError)
    assert "batch_chat_completion task 2/2 failed" in caplog.text
    assert "simulated failure" in caplog.text


def test_patch_httpx_not_called_on_import():
    """Verify importing qreward.client.openai does not trigger patch_httpx()
    at module level — patch is deferred to OpenAIChatProxy.__init__."""
    import importlib
    import qreward.client.openai as openai_mod

    with patch.object(openai_mod, "patch_httpx") as mock_patch:
        # Creating a proxy should call patch_httpx
        mock_patch.reset_mock()
        OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
        mock_patch.assert_called_once()


# ============================================================
# Sprint 5: default config + SSL + proxies copy tests
# ============================================================


def test_default_max_concurrent():
    """Verify max_concurrent default is 64 (lowered from 1024)."""
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
    assert proxy._max_concurrent == 64


def test_default_max_retries():
    """Verify MAX_RETRIES is 5 (lowered from 10)."""
    from qreward.client.openai import MAX_RETRIES

    assert MAX_RETRIES == 5


def test_verify_ssl_configurable():
    """Verify verify_ssl parameter is passed through to _default_http_client."""
    # Patch _default_http_client to capture the verify argument
    captured_args = {}
    original_method = OpenAIChatProxy._default_http_client

    def spy_http_client(self, **kwargs):
        captured_args.update(kwargs)
        return original_method(self, **kwargs)

    with patch.object(OpenAIChatProxy, "_default_http_client", spy_http_client):
        # Default: verify_ssl=False
        OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
        assert captured_args.get("verify") is False

        # Explicit: verify_ssl=True
        captured_args.clear()
        OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY, verify_ssl=True)
        assert captured_args.get("verify") is True


@pytest.mark.asyncio
async def test_proxies_returns_copy():
    """Verify proxies() returns a dict copy, not the internal dict."""
    manager = OpenAIChatProxyManager()
    dummy = DummyProxy()
    manager.add_proxy("k1", dummy)

    result = manager.proxies()
    # Must be a different dict object
    assert result is not manager._proxies
    # But same content
    assert result == {"k1": dummy}
    # Modifying the copy must not affect internal state
    result["k2"] = DummyProxy()
    assert "k2" not in manager._proxies


# ============================================================
# Sprint 8: Observability — logger replaces print
# ============================================================

@pytest.mark.asyncio
async def test_debug_uses_logger(caplog):
    """Verify OpenAIChatProxy debug=True uses logger.debug, not print."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="qreward.client.openai"):
        proxy = OpenAIChatProxy(
            base_url=TEST_URL,
            api_key=TEST_API_KEY,
            debug=True,
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "hello"

        with patch.object(
            proxy.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ):
            await proxy.chat_completion(model="test-model", messages=[{"role": "user", "content": "hi"}])

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Begin" in r.message and "test-model" in r.message for r in debug_records)
    assert any("End" in r.message and "test-model" in r.message for r in debug_records)

@pytest.mark.asyncio
async def test_new_param_names():
    """M-VERIFY-1: New parameter names chat_process_func and error_process_func work."""
    def my_chat_func(resp):
        return resp

    def my_error_func(exc):
        return str(exc)

    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        chat_process_func=my_chat_func,
        error_process_func=my_error_func,
    )
    assert proxy._default_chat_process_func == my_chat_func
    assert proxy._default_error_process_func == my_error_func

def test_deprecated_param_names():
    """M-VERIFY-2: Old parameter names still work but trigger DeprecationWarning."""
    import warnings

    def my_chat_func(resp):
        return resp

    def my_error_func(exc):
        return str(exc)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        proxy = OpenAIChatProxy(
            base_url=TEST_URL,
            api_key=TEST_API_KEY,
            chat_process_fuc=my_chat_func,
            error_process_fuc=my_error_func,
        )

    deprecation_messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("chat_process_fuc" in m for m in deprecation_messages)
    assert any("error_process_fuc" in m for m in deprecation_messages)
    assert proxy._default_chat_process_func == my_chat_func
    assert proxy._default_error_process_func == my_error_func


# ============================================================
# Sprint 12: Load Balancing & Failover Tests
# ============================================================


def test_round_robin_selection(monkeypatch):
    """M-VERIFY-1: select_proxy uses ROUND_ROBIN to cycle through proxies."""
    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        lambda self, **kw: setattr(self, "_base_url", kw.get("base_url", ""))
        or setattr(self, "client", MagicMock()),
    )

    manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.ROUND_ROBIN)
    manager.add_proxy_with_default("a", "http://a", "sk-a")
    manager.add_proxy_with_default("b", "http://b", "sk-b")
    manager.add_proxy_with_default("c", "http://c", "sk-c")

    selected = [manager.select_proxy()._base_url for _ in range(6)]
    assert selected == ["http://a", "http://b", "http://c", "http://a", "http://b", "http://c"]


def test_skip_unhealthy_proxy(monkeypatch):
    """M-VERIFY-2: mark_unhealthy causes select_proxy to skip that proxy."""
    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        lambda self, **kw: setattr(self, "_base_url", kw.get("base_url", ""))
        or setattr(self, "client", MagicMock()),
    )

    manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.ROUND_ROBIN)
    manager.add_proxy_with_default("a", "http://a", "sk-a")
    manager.add_proxy_with_default("b", "http://b", "sk-b")
    manager.add_proxy_with_default("c", "http://c", "sk-c")

    manager.mark_unhealthy("b")

    selected = [manager.select_proxy()._base_url for _ in range(4)]
    assert "http://b" not in selected
    assert selected == ["http://a", "http://c", "http://a", "http://c"]


def test_all_unhealthy_raises(monkeypatch):
    """M-VERIFY-3: All proxies unhealthy -> select_proxy raises RuntimeError."""
    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        lambda self, **kw: setattr(self, "_base_url", kw.get("base_url", ""))
        or setattr(self, "client", MagicMock()),
    )

    manager = OpenAIChatProxyManager()
    manager.add_proxy_with_default("a", "http://a", "sk-a")
    manager.add_proxy_with_default("b", "http://b", "sk-b")

    manager.mark_unhealthy("a")
    manager.mark_unhealthy("b")

    with pytest.raises(RuntimeError, match="No healthy proxy available"):
        manager.select_proxy()


def test_mark_healthy_recovers(monkeypatch):
    """mark_healthy restores a previously unhealthy proxy."""
    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        lambda self, **kw: setattr(self, "_base_url", kw.get("base_url", ""))
        or setattr(self, "client", MagicMock()),
    )

    manager = OpenAIChatProxyManager()
    manager.add_proxy_with_default("a", "http://a", "sk-a")

    manager.mark_unhealthy("a")
    with pytest.raises(RuntimeError):
        manager.select_proxy()

    manager.mark_healthy("a")
    assert manager.select_proxy()._base_url == "http://a"


def test_healthy_proxies_returns_copy(monkeypatch):
    """S-2: healthy_proxies returns a copy that excludes unhealthy ones."""
    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        lambda self, **kw: setattr(self, "_base_url", kw.get("base_url", ""))
        or setattr(self, "client", MagicMock()),
    )

    manager = OpenAIChatProxyManager()
    manager.add_proxy_with_default("a", "http://a", "sk-a")
    manager.add_proxy_with_default("b", "http://b", "sk-b")

    manager.mark_unhealthy("b")
    healthy = manager.healthy_proxies()

    assert "a" in healthy
    assert "b" not in healthy
    # Verify it's a copy
    healthy["injected"] = MagicMock()
    assert "injected" not in manager.healthy_proxies()


def test_weighted_round_robin_selection(monkeypatch):
    """S-1: WEIGHTED_ROUND_ROBIN distributes requests by weight."""
    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        lambda self, **kw: setattr(self, "_base_url", kw.get("base_url", ""))
        or setattr(self, "client", MagicMock()),
    )

    manager = OpenAIChatProxyManager(strategy=LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN)
    proxy_a = OpenAIChatProxy(base_url="http://a", api_key="sk-a")
    proxy_b = OpenAIChatProxy(base_url="http://b", api_key="sk-b")
    manager.add_proxy("a", proxy_a, weight=3)
    manager.add_proxy("b", proxy_b, weight=1)

    # Over 4 selections, "a" should appear ~3 times and "b" ~1 time
    results = [manager.select_proxy()._base_url for _ in range(4)]
    assert results.count("http://a") == 3
    assert results.count("http://b") == 1


def test_mark_unhealthy_nonexistent_raises():
    """mark_unhealthy on non-existent key raises KeyError."""
    manager = OpenAIChatProxyManager()
    with pytest.raises(KeyError, match="does not exist"):
        manager.mark_unhealthy("nonexistent")


def test_mark_healthy_nonexistent_raises():
    """mark_healthy on non-existent key raises KeyError."""
    manager = OpenAIChatProxyManager()
    with pytest.raises(KeyError, match="does not exist"):
        manager.mark_healthy("nonexistent")


def test_select_proxy_empty_manager():
    """select_proxy on empty manager raises RuntimeError."""
    manager = OpenAIChatProxyManager()
    with pytest.raises(RuntimeError, match="No healthy proxy available"):
        manager.select_proxy()


@pytest.mark.asyncio
async def test_remove_proxy_cleans_health_state(monkeypatch):
    """remove_proxy also removes health tracking state."""
    def _mock_init(self, **kw):
        self._base_url = kw.get("base_url", "")
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        self.client = mock_client

    monkeypatch.setattr(
        "qreward.client.manager.OpenAIChatProxy.__init__",
        _mock_init,
    )

    manager = OpenAIChatProxyManager()
    manager.add_proxy_with_default("a", "http://a", "sk-a")
    manager.add_proxy_with_default("b", "http://b", "sk-b")

    await manager.remove_proxy("a")

    assert "a" not in manager.healthy_proxies()
    selected = [manager.select_proxy()._base_url for _ in range(3)]
    assert all(url == "http://b" for url in selected)


def test_manager_default_strategy():
    """Manager defaults to ROUND_ROBIN strategy."""
    manager = OpenAIChatProxyManager()
    assert manager._strategy == LoadBalanceStrategy.ROUND_ROBIN


def test_load_balance_strategy_values():
    """LoadBalanceStrategy enum has expected values."""
    assert LoadBalanceStrategy.ROUND_ROBIN.value == "round_robin"
    assert LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN.value == "weighted_round_robin"
    assert LoadBalanceStrategy.LEAST_CONNECTIONS.value == "least_connections"


# ============================================================
# Sprint 13: Streaming Response Tests
# ============================================================


@pytest.mark.asyncio
async def test_stream_chat_completion(proxy):
    """M-VERIFY-1: stream_chat_completion returns AsyncIterator of str chunks."""

    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    chunks = [MockChunk("Hello"), MockChunk(" "), MockChunk("world")]

    class MockStream:
        def __init__(self, items):
            self._items = items
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._index]
            self._index += 1
            return item

        async def close(self):
            pass

    proxy.client.chat.completions.create = AsyncMock(
        return_value=MockStream(chunks)
    )

    collected = []
    async for token in proxy.stream_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
    ):
        collected.append(token)

    assert collected == ["Hello", " ", "world"]


@pytest.mark.asyncio
async def test_stream_error_handling(proxy):
    """M-VERIFY-2: Errors during streaming are properly propagated."""

    proxy.client.chat.completions.create = AsyncMock(
        side_effect=Exception("stream connection failed")
    )

    with pytest.raises(Exception, match="stream connection failed"):
        async for _ in proxy.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-test",
        ):
            pass


@pytest.mark.asyncio
async def test_stream_chat_completion_with_debug(proxy, caplog):
    """S-2: stream_chat_completion emits debug logs."""
    import logging

    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    class MockStream:
        def __init__(self, items):
            self._items = items
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._index]
            self._index += 1
            return item

        async def close(self):
            pass

    proxy.debug = True
    proxy.client.chat.completions.create = AsyncMock(
        return_value=MockStream([MockChunk("ok")])
    )

    with caplog.at_level(logging.DEBUG, logger="qreward.client.openai"):
        collected = []
        async for token in proxy.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-test",
        ):
            collected.append(token)

    assert collected == ["ok"]
    assert any("Stream model" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_stream_skips_empty_chunks(proxy):
    """stream_chat_completion skips chunks with None content."""

    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    class MockEmptyChunk:
        def __init__(self):
            self.choices = []

    class MockStream:
        def __init__(self, items):
            self._items = items
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._index]
            self._index += 1
            return item

        async def close(self):
            pass

    chunks = [MockChunk("Hi"), MockEmptyChunk(), MockChunk(None), MockChunk("!")]
    proxy.client.chat.completions.create = AsyncMock(
        return_value=MockStream(chunks)
    )

    collected = []
    async for token in proxy.stream_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-test",
    ):
        collected.append(token)

    assert collected == ["Hi", "!"]


# ============================================================
# Sprint 16: Model Router Tests
# ============================================================

from qreward.client.model_router import ModelRouter
from qreward.client.load_balancer import LoadBalanceStrategy


def test_model_router_basic():
    """M-VERIFY-1: select_proxy routes by model name."""
    proxy_a = MagicMock(spec=OpenAIChatProxy)
    proxy_b = MagicMock(spec=OpenAIChatProxy)

    manager = OpenAIChatProxyManager()
    manager.add_proxy("default1", proxy_a)

    manager.register_model_route(
        "gpt-4",
        {"gpt4_proxy": proxy_b},
    )

    # Model-based routing returns proxy_b
    result = manager.select_proxy(model="gpt-4")
    assert result is proxy_b

    # Default routing (no model) returns proxy_a
    result_default = manager.select_proxy()
    assert result_default is proxy_a


def test_model_router_fallback():
    """M-VERIFY-2: Unregistered model falls back to default pool."""
    proxy_a = MagicMock(spec=OpenAIChatProxy)

    manager = OpenAIChatProxyManager()
    manager.add_proxy("default1", proxy_a)

    # No routes registered, model param should fallback
    result = manager.select_proxy(model="unknown-model")
    assert result is proxy_a


def test_model_router_independent_health():
    """M-VERIFY-3: Each model group has independent health state."""
    proxy_a = MagicMock(spec=OpenAIChatProxy)
    proxy_b = MagicMock(spec=OpenAIChatProxy)

    manager = OpenAIChatProxyManager()
    manager.add_proxy("default1", proxy_a)

    manager.register_model_route(
        "gpt-4",
        {"gpt4_p1": proxy_b},
    )

    # Mark gpt-4 group proxy unhealthy
    manager._model_router.mark_unhealthy("gpt-4", "gpt4_p1")

    # gpt-4 group has no healthy proxy
    with pytest.raises(RuntimeError, match="No healthy proxy"):
        manager.select_proxy(model="gpt-4")

    # Default pool still works
    result = manager.select_proxy()
    assert result is proxy_a


def test_model_router_wildcard():
    """S-1: Wildcard routing matches glob patterns."""
    proxy_gpt = MagicMock(spec=OpenAIChatProxy)

    router = ModelRouter()
    router.register("gpt-*", {"p1": proxy_gpt})

    group = router.resolve("gpt-3.5-turbo")
    assert group is not None
    assert group.pattern == "gpt-*"

    # Non-matching model
    assert router.resolve("claude-3") is None


def test_model_router_exact_over_wildcard():
    """Exact match takes priority over wildcard."""
    proxy_exact = MagicMock(spec=OpenAIChatProxy)
    proxy_wild = MagicMock(spec=OpenAIChatProxy)

    router = ModelRouter()
    router.register("gpt-*", {"wild": proxy_wild})
    router.register("gpt-4", {"exact": proxy_exact})

    # gpt-4 should match exact, not wildcard
    group = router.resolve("gpt-4")
    assert group is not None
    assert group.pattern == "gpt-4"

    # gpt-3.5 should match wildcard
    group2 = router.resolve("gpt-3.5")
    assert group2 is not None
    assert group2.pattern == "gpt-*"


def test_model_router_list_routes():
    """S-3: list_routes returns route info."""
    proxy = MagicMock(spec=OpenAIChatProxy)

    manager = OpenAIChatProxyManager()
    manager.register_model_route("gpt-4", {"p1": proxy})
    manager.register_model_route("claude-*", {"p2": proxy})

    routes = manager.list_routes()
    assert len(routes) == 2
    patterns = {r["pattern"] for r in routes}
    assert "gpt-4" in patterns
    assert "claude-*" in patterns


def test_model_router_list_routes_empty():
    """list_routes returns empty when no router configured."""
    manager = OpenAIChatProxyManager()
    assert manager.list_routes() == []


# ============================================================
# Sprint 18: Batch Stream Tests
# ============================================================


@pytest.mark.asyncio
async def test_batch_stream_chat_completion():
    """M-VERIFY-1: batch_stream returns (batch_index, token) tuples."""
    proxy = OpenAIChatProxy(base_url="http://fake", api_key="sk-test")

    async def fake_stream(messages, model, **kwargs):
        for tok in ["hello", " ", "world"]:
            yield tok

    with patch.object(proxy, "stream_chat_completion", side_effect=fake_stream):
        results = []
        async for idx, token in proxy.batch_stream_chat_completion(
            [
                [{"role": "user", "content": "hi"}],
                [{"role": "user", "content": "bye"}],
            ],
            model="gpt-4",
        ):
            results.append((idx, token))

    # Both streams produce 3 tokens each
    assert len(results) == 6
    indices = {r[0] for r in results}
    assert indices == {0, 1}


@pytest.mark.asyncio
async def test_batch_stream_partial_failure():
    """M-VERIFY-2: Single stream failure doesn't affect others."""
    proxy = OpenAIChatProxy(base_url="http://fake", api_key="sk-test")
    errors_captured = []

    call_count = 0

    async def fake_stream(messages, model, **kwargs):
        nonlocal call_count
        current = call_count
        call_count += 1
        if current == 0:
            raise RuntimeError("stream 0 failed")
        for tok in ["ok"]:
            yield tok

    with patch.object(proxy, "stream_chat_completion", side_effect=fake_stream):
        results = []
        async for idx, token in proxy.batch_stream_chat_completion(
            [
                [{"role": "user", "content": "fail"}],
                [{"role": "user", "content": "ok"}],
            ],
            model="gpt-4",
            on_stream_error=lambda i, e: errors_captured.append((i, e)),
        ):
            results.append((idx, token))

    # Stream 1 succeeded
    assert len(results) == 1
    assert results[0] == (1, "ok")
    # Stream 0 error was captured
    assert len(errors_captured) == 1
    assert errors_captured[0][0] == 0


@pytest.mark.asyncio
async def test_batch_stream_empty():
    """M-VERIFY-3: Empty batch returns empty iterator."""
    proxy = OpenAIChatProxy(base_url="http://fake", api_key="sk-test")

    results = []
    async for item in proxy.batch_stream_chat_completion([], model="gpt-4"):
        results.append(item)

    assert results == []
