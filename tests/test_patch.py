import sys
import types
import builtins
import httpx

from qreward.utils import patch_httpx


class DummyResponse:
    def __init__(self, content: bytes):
        self.content = content


def get_stream_bytes(stream):
    """收集 ByteStream 内容为 bytes"""
    return b"".join(stream)


# 测试数据：不嵌套中文、浮点数组、嵌套中文
complex_json = {
    "title": "中文标题",
    "numbers": [1.5, 2.3],
    "nested": {"中文键": "测试"},
}


def test_original_httpx_behavior():
    """验证 patch 前原版 httpx 行为"""
    headers, stream = httpx._content.encode_json(complex_json)
    body = get_stream_bytes(stream)
    assert b"title" in body
    content_bytes = '{"nested":{"中文键":"测试"}}'.encode("utf-8")
    resp = httpx.Response(200, content=content_bytes)
    assert resp.json()["nested"]["中文键"] == "测试"


def test_patch_with_ujson(monkeypatch):
    """ujson 存在版本"""
    sys.modules.pop("ujson", None)
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "ujson":
            t = '{"title":"中文标题","numbers":[1.5,2.3],"nested":{"中文键":"测试"}}'
            mod = types.ModuleType("ujson")
            mod.dumps = lambda obj, **kwargs: t
            mod.loads = lambda b, **kwargs: complex_json
            sys.modules["ujson"] = mod
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    patch_httpx("ujson")

    headers, stream = httpx._content.encode_json(complex_json)
    body = get_stream_bytes(stream)
    assert "中文标题".encode("utf-8") in body
    assert b"[1.5,2.3]" in body
    assert "中文键".encode("utf-8") in body
    resp = DummyResponse(body)
    assert httpx.Response.__dict__["json"](resp) == complex_json


def test_patch_with_ujson_importerror(monkeypatch):
    """ujson ImportError 分支"""
    sys.modules.pop("ujson", None)
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "ujson":
            raise ImportError()
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    patch_httpx("ujson")

    headers, stream = httpx._content.encode_json(complex_json)
    body = get_stream_bytes(stream)
    assert "中文标题".encode("utf-8") in body
    assert b"[1.5,2.3]" in body
    assert "中文键".encode("utf-8") in body
    resp = DummyResponse(body)
    assert httpx.Response.__dict__["json"](resp) == complex_json


def test_patch_with_orjson(monkeypatch):
    """orjson 存在版本"""
    sys.modules.pop("orjson", None)
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "orjson":
            t = '{"title":"中文标题","numbers":[1.5,2.3],"nested":{"中文键":"测试"}}'
            mod = types.ModuleType("orjson")
            mod.dumps = lambda obj: t.encode("utf-8")
            mod.loads = lambda b: complex_json
            sys.modules["orjson"] = mod
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    patch_httpx("orjson")

    headers, stream = httpx._content.encode_json(complex_json)
    body = get_stream_bytes(stream)
    assert "中文标题".encode("utf-8") in body
    assert b"[1.5,2.3]" in body
    assert "中文键".encode("utf-8") in body
    resp = DummyResponse(body)
    assert httpx.Response.__dict__["json"](resp) == complex_json


def test_patch_with_orjson_importerror(monkeypatch):
    """orjson ImportError 分支"""
    sys.modules.pop("orjson", None)
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "orjson":
            raise ImportError()
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    patch_httpx("orjson")

    headers, stream = httpx._content.encode_json(complex_json)
    body = get_stream_bytes(stream)
    assert "中文标题".encode("utf-8") in body
    assert b"[1.5,2.3]" in body
    assert "中文键".encode("utf-8") in body
    resp = DummyResponse(body)
    assert httpx.Response.__dict__["json"](resp) == complex_json
