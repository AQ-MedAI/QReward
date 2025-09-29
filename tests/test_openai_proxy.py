import asyncio
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from qreward.client import OpenAIChatProxy, OpenAIChatProxyManager

TEST_URL = "http://fake"
TEST_API_KEY = "abc"
TEST_CUSTOM_URL = "http://fake/api/embed"


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

    res = await proxy.embeddings(["hello"], model="embedding-model")
    assert res == [{"embedding": [0.1, 0.2]}]


@pytest.mark.asyncio
async def test_embeddings_with_custom_url_empty(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)

    async def fake_post(*args, **kwargs):
        class FakeResponse:
            status = HTTPStatus.BAD_REQUEST

            async def json(self):
                return {}

            async def text(self):
                return "error"

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

        return FakeResponse()

    monkeypatch.setattr(aiohttp.ClientSession, "post", fake_post)

    result = await proxy.embeddings(
        ["hello"],
        custom_url=TEST_CUSTOM_URL,
    )
    assert result == []


@pytest.mark.asyncio
async def test_batch_embeddings(monkeypatch):
    proxy = OpenAIChatProxy(base_url=TEST_URL, api_key=TEST_API_KEY)
    proxy.embeddings = AsyncMock(side_effect=[["embed1"], ["embed2"]])

    res = await proxy.batch_embeddings([["a"], ["b"]], model="emb-model")
    assert res == [["embed1"], ["embed2"]]


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


class DummyResponseOK:
    """模拟 200 OK 响应"""

    def __init__(self):
        self.status = HTTPStatus.OK

    async def json(self):
        # 模拟 API 返回 embeddings
        return {"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]}

    async def text(self):
        return "OK"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummyResponseError:
    """模拟错误响应（非200）"""

    def __init__(self):
        self.status = HTTPStatus.BAD_REQUEST

    async def json(self):
        return {}

    async def text(self):
        return "Bad Request"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummySession:
    """模拟 aiohttp.ClientSession"""

    def __init__(self, ok=True):
        self.ok = ok

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def post(self, *args, **kwargs):
        # 根据 ok 参数返回不同的响应
        if self.ok:
            return DummyResponseOK()
        else:
            return DummyResponseError()


@pytest.mark.asyncio
async def test_embeddings_with_custom_url_success(monkeypatch, capsys):
    # 动态检查当前模块路径
    module_path = OpenAIChatProxy.__module__

    # 第一次测试：debug=True + 正常返回
    monkeypatch.setattr(
        f"{module_path}.ClientSession",
        lambda: DummySession(ok=True),
    )
    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
        debug=True,  # 打开调试
    )

    sentences = ["hello", "world"]
    result = await proxy.embeddings(
        sentences=sentences,
        custom_url=TEST_CUSTOM_URL,
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]

    # 检查 debug 信息是否打印
    captured = capsys.readouterr()
    assert "[Begin] - Call embedding" in captured.out
    assert "[End] - Call embedding" in captured.out


@pytest.mark.asyncio
async def test_embeddings_with_custom_url_error(monkeypatch, capsys):
    # 动态检查当前模块路径
    module_path = OpenAIChatProxy.__module__

    sentences = ["hello", "world"]

    proxy = OpenAIChatProxy(
        base_url=TEST_URL,
        api_key=TEST_API_KEY,
    )

    # 第二次测试：错误响应分支
    monkeypatch.setattr(
        f"{module_path}.ClientSession",
        lambda: DummySession(ok=False),
    )
    result_error = await proxy.embeddings(
        sentences=sentences,
        custom_url=TEST_CUSTOM_URL,
    )

    assert result_error == []  # 错误响应应该返回空列表
    # 同时会打印 HTTP Status Code 和 Error Text
    captured_err = capsys.readouterr()
    assert "HTTP Status Code" in captured_err.out
    assert "Bad Request" in captured_err.out


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
