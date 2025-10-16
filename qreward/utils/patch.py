import os

import httpx

# 可以通过环境变量控制
_default_json_lib = os.getenv(
    key="JSON_LIB",
    default=None,
)


def patch_httpx(json_lib_name: str = _default_json_lib):  # type: ignore
    _use_ujson = False
    _use_orjson = False

    from httpx._content import Any, ByteStream, json_dumps
    from httpx._models import typing, jsonlib

    if json_lib_name == "ujson":
        try:
            import ujson
            _use_ujson = True
        except ImportError:
            pass
    elif json_lib_name == "orjson":
        try:
            import orjson
            _use_orjson = True
        except ImportError:
            pass

    def encode_json(json: Any) -> tuple[dict[str, str], ByteStream]:
        if _use_orjson:
            body = orjson.dumps(json)
        elif _use_ujson:
            body = ujson.dumps(
                json,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        else:
            body = json_dumps(
                json,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )

        if isinstance(body, str):
            body = body.encode("utf-8")

        content_length = str(len(body))
        content_type = "application/json"
        headers = {
            "Content-Length": content_length,
            "Content-Type": content_type,
        }
        return headers, ByteStream(body)

    def decode_json(self, **kwargs: typing.Any) -> typing.Any:
        if _use_orjson:
            return orjson.loads(self.content)
        elif _use_ujson:
            return ujson.loads(self.content, **kwargs)
        return jsonlib.loads(self.content, **kwargs)

    # encode
    encode_json.__globals__.update(httpx._content.__dict__)
    encode_json.__module__ = httpx._content.__name__
    httpx._content.encode_json = encode_json

    # decode
    httpx._models.Response.json = decode_json
