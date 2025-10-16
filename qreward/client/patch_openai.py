from typing import Callable, List, Union

from typing_extensions import Literal

from openai._base_client import make_request_options
from openai._models import BaseModel
from openai._types import Omit
from openai._utils import is_given, maybe_transform
from openai.types import embedding_create_params
from openai.types.create_embedding_response import Embedding, Usage
from openai.types.embedding_model import EmbeddingModel


class HackCreateEmbeddingResponse(BaseModel):
    embeddings: List[Embedding]

    model: str
    """The name of the model used to generate the embedding."""

    object: Literal["list"]
    """The object type, which is always "list"."""

    usage: Usage
    """The usage information for the request."""


def hack_parser(
    obj: HackCreateEmbeddingResponse,
) -> HackCreateEmbeddingResponse:
    if not obj.embeddings:
        raise ValueError("No embedding data received")

    return obj


# ===== PATCH 函数 =====
def patch_openai_embeddings(
    custom_return_cls: type = HackCreateEmbeddingResponse,
    custom_parser: Callable = hack_parser,
):
    """
    运行时替换 OpenAI Python SDK 的 AsyncEmbeddings.create 方法，
    让其返回自定义的 Response 类，并使用自定义的 parser。

    Args:
        custom_return_cls: 自定义返回类（BaseModel子类）
        custom_parser: 自定义parser函数，接收并返回 custom_return_cls 实例
    """
    from openai.resources.embeddings import AsyncEmbeddings

    async def patched_create(
        self,
        *,
        input,
        model: Union[str, EmbeddingModel],
        dimensions: int | Omit = Omit(),
        encoding_format: Literal["float", "base64"] | Omit = Omit(),
        user: str | Omit = Omit(),
        extra_headers=None,
        extra_query=None,
        extra_body=None,
        timeout=None,
    ):
        params = {
            "input": input,
            "model": model,
            "user": user,
            "dimensions": dimensions,
            "encoding_format": encoding_format,
        }
        if not is_given(encoding_format):
            params["encoding_format"] = "base64"

        return await self._post(
            "/embeddings",
            body=maybe_transform(
                params,
                embedding_create_params.EmbeddingCreateParams,
            ),
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                post_parser=custom_parser,
            ),
            cast_to=custom_return_cls,
        )

    # 替换方法
    AsyncEmbeddings.create = patched_create
