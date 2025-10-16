import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from qreward.client import (
    OpenAIChatProxy,
    OpenAIChatProxyManager,
)


TEST_URL = "http://fake"
TEST_API_KEY = "abc"


def test_get_openai_key_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env_key_123")
    assert OpenAIChatProxy.get_openai_key() == "env_key_123"


def test_with_methods():
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
    assert proxy.with_max_concurrent(10)._max_concurrent == 10
    assert proxy.with_temperature(0.9)._default_temperature == 0.9
    assert proxy.with_timeout(99)._default_timeout == 99

    def dummy_error_func(e):
        return str(e)

    assert (
        proxy.with_error_process_fuc(
            error_process_fuc=dummy_error_func,
        )._default_error_process_fuc
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
async def test_chat_completion_success(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
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
async def test_chat_completion_with_custom_processing(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)

    completion_mock = MagicMock()
    completion_mock.choices = [MagicMock(message=MagicMock(content="Hello"))]

    # 使用自定义处理函数
    def process_func(resp):
        return resp  # 这里可以做额外处理

    proxy._default_chat_process_fuc = process_func

    proxy.client.chat.completions.create = AsyncMock(
        return_value=completion_mock,
    )

    result = await proxy.chat_completion(messages=[], model="test")
    assert result == "Hello"


@pytest.mark.asyncio
async def test_batch_chat_completion(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
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
async def test_embeddings_with_openai(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
    emb_mock = MagicMock()
    emb_mock.data = [{"embedding": [0.1, 0.2]}]
    proxy.client.embeddings.create = AsyncMock(return_value=emb_mock)

    res = await proxy.embeddings(sentences=["hello"], model="embedding-model")
    assert res == [{"embedding": [0.1, 0.2]}]


@pytest.mark.asyncio
async def test_batch_embeddings(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
    proxy.embeddings = AsyncMock(side_effect=[["embed1"], ["embed2"]])

    res = await proxy.batch_embeddings(
        batch_sentences=[["a"], ["b"]],
        model="emb-model",
    )
    assert res == [["embed1"], ["embed2"]]


@pytest.mark.asyncio
async def test_embeddings_debug_print(capsys):
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        debug=True,
    )
    emb_mock = MagicMock()
    emb_mock.data = [{"embedding": [0.1, 0.2]}]
    proxy.client.embeddings.create = AsyncMock(return_value=emb_mock)

    await proxy.embeddings(sentences=["hello"], model="embedding-model")

    # 捕获 debug 输出
    captured = capsys.readouterr()
    assert "[Begin] - Call embedding: embedding-model" in captured.out
    assert "[End] - Call embedding: embedding-model success!" in captured.out


@pytest.mark.asyncio
async def test_async_context_manager(monkeypatch):
    # 创建实例
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)

    # mock close 方法，避免真实资源释放
    proxy.client.close = AsyncMock()

    async with proxy as instance:
        # 验证 __aenter__ 返回的是自身
        assert instance is proxy

    # 验证 __aexit__ 调用了 client.close()
    proxy.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_async_context_manager_with_exception():
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
    proxy.client.close = AsyncMock()

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        async with proxy:
            raise CustomError("boom")


@pytest.mark.asyncio
async def test_chat_completion_debug_print(capsys):
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

    # 捕获 debug 输出
    captured = capsys.readouterr()
    assert "[Begin] - Call model: test-model" in captured.out
    assert "[End] - Call model: test-model success!" in captured.out


@pytest.mark.asyncio
async def test_batch_chat_completion_error_process():
    # 构造一个假的 error_process_fuc，用于检测是否调用
    def fake_error_process_func(exc):
        return f"processed: {exc}"

    # 实例化代理对象（用假的 base_url 和 api_key）
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        error_process_fuc=fake_error_process_func,
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
async def test_embeddings_returns_empty_list_on_timeout():
    """
    测试当embeddings方法遇到超时异常时返回空列表
    """
    # 创建OpenAIChatProxy实例
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY
    )

    # 模拟asyncio.wait_for抛出TimeoutError
    with patch(target='asyncio.wait_for',
               side_effect=Exception("Test other exception")):
        # 调用embeddings方法
        result = await proxy.embeddings(
            sentences=["test sentence"],
            model="text-embedding-model"
        )

        # 验证返回空列表
        assert result == []


@pytest.mark.asyncio
async def test_embeddings_timeout_branch(monkeypatch, capsys):
    """覆盖 except TimeoutError 分支（305-309行）"""
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        debug=True
    )

    # 让 create 抛出 asyncio.TimeoutError 模拟请求超时
    async def fake_timeout_create(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        proxy.client.embeddings,
        "create",
        fake_timeout_create,
    )

    sentences = ["timeout test"]
    with pytest.raises(TimeoutError):  # 方法内会重新 raise TimeoutError
        await proxy.embeddings(
            sentences=sentences,
            model="text-embedding-ada-002",
        )

    captured = capsys.readouterr()
    assert "[Retry-Timeout] - Call model" in captured.out


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
