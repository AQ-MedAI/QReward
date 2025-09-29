import socket
import sys
from unittest.mock import MagicMock, patch

import pytest
from requests.adapters import HTTPAdapter

from qreward.utils import (RequestsTCPKeepAliveAdapter,
                           aiohttp_keepalive_socket_factory,
                           httpx_keepalive_socket)


@pytest.fixture(autouse=True)
def patch_socket_constants(monkeypatch):
    """保证所有平台都有这些常量"""
    monkeypatch.setattr(socket, "TCP_KEEPIDLE", 4, raising=False)
    monkeypatch.setattr(socket, "TCP_KEEPINTVL", 5, raising=False)
    monkeypatch.setattr(socket, "TCP_KEEPCNT", 6, raising=False)
    monkeypatch.setattr(socket, "TCP_KEEPALIVE", 7, raising=False)
    yield


def test_aiohttp_keepalive_socket_factory_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    mock_sock = MagicMock()
    monkeypatch.setattr(socket, "socket", MagicMock(return_value=mock_sock))

    addr_info = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))
    sock = aiohttp_keepalive_socket_factory(addr_info, 10, 20, 5)

    assert sock is mock_sock
    mock_sock.setsockopt.assert_any_call(
        socket.SOL_SOCKET,
        socket.SO_KEEPALIVE,
        1,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPIDLE,
        10,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPINTVL,
        20,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPCNT,
        5,
    )


def test_aiohttp_keepalive_socket_factory_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_sock = MagicMock()
    monkeypatch.setattr(socket, "socket", MagicMock(return_value=mock_sock))

    addr_info = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))
    sock = aiohttp_keepalive_socket_factory(addr_info, 15, 25, 8)

    assert sock is mock_sock
    mock_sock.setsockopt.assert_any_call(
        socket.SOL_SOCKET,
        socket.SO_KEEPALIVE,
        1,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPALIVE,
        15,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPINTVL,
        25,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPCNT,
        8,
    )


def test_aiohttp_keepalive_socket_factory_other(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    mock_sock = MagicMock()
    monkeypatch.setattr(socket, "socket", MagicMock(return_value=mock_sock))

    addr_info = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))
    sock = aiohttp_keepalive_socket_factory(addr_info)

    assert sock is mock_sock
    mock_sock.setsockopt.assert_any_call(
        socket.SOL_SOCKET,
        socket.SO_KEEPALIVE,
        1,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPINTVL,
        30,
    )
    mock_sock.setsockopt.assert_any_call(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPCNT,
        3,
    )


def test_httpx_keepalive_socket_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    opts = httpx_keepalive_socket(12, 22, 7)
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 12) in opts
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 22) in opts
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 7) in opts


def test_httpx_keepalive_socket_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    opts = httpx_keepalive_socket(14, 24, 9)
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 14) in opts
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 24) in opts
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 9) in opts


def test_httpx_keepalive_socket_other(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    opts = httpx_keepalive_socket()
    assert any(opt for opt in opts if opt[1] == socket.TCP_KEEPINTVL)
    assert any(opt for opt in opts if opt[1] == socket.TCP_KEEPCNT)


def test_requests_tcp_keepalive_adapter_defaults(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    default_opts = httpx_keepalive_socket()
    adapter = RequestsTCPKeepAliveAdapter()
    assert adapter.socket_options == default_opts


def test_requests_tcp_keepalive_adapter_custom_options():
    custom_opts = [(1, 2, 3)]
    adapter = RequestsTCPKeepAliveAdapter(socket_options=custom_opts)
    assert adapter.socket_options == custom_opts


def test_requests_tcp_keepalive_adapter_init_poolmanager(monkeypatch):
    adapter = RequestsTCPKeepAliveAdapter(socket_options=[(1, 2, 3)])
    called_args = {}

    def fake_init_poolmanager(
        self,
        connections,
        maxsize,
        block=False,
        **kwargs,
    ):
        called_args.update(kwargs)

    with patch.object(HTTPAdapter, "init_poolmanager", fake_init_poolmanager):
        adapter.init_poolmanager(10, 20)

    assert called_args["socket_options"] == [(1, 2, 3)]


def test_init_poolmanager_socket_options_injected():
    # 准备一个自定义 socket_options
    custom_opts = [(1, 2, 3)]
    adapter = RequestsTCPKeepAliveAdapter(socket_options=custom_opts)

    called_args = {}

    # 用 patch 替换掉父类的 init_poolmanager，检查 kwargs
    with patch.object(
        HTTPAdapter,
        "init_poolmanager",
        lambda self, conns, maxsize, block=False, **kwargs:
        called_args.update(kwargs),
    ):
        # 调用方法
        adapter.init_poolmanager(10, 20)

    # 验证 if 条件成立，并且 socket_options 被传入 pool_kwargs
    assert called_args["socket_options"] == custom_opts


def test_init_poolmanager_socket_options_none():
    adapter = RequestsTCPKeepAliveAdapter(socket_options=None)

    called_args = {}

    with patch.object(
        HTTPAdapter,
        "init_poolmanager",
        lambda self, conns, maxsize, block=False, **kwargs:
        called_args.update(kwargs),
    ):
        adapter.init_poolmanager(10, 20)

    # 当 socket_options 为 None 时，kwargs 里不应有这个 key
    assert "socket_options" not in called_args
