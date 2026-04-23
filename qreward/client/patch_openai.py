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


# Store the original method reference for unpatch support
_original_async_embeddings_create = None


# ===== PATCH 函数 =====
def patch_openai_embeddings(
    custom_return_cls: type = HackCreateEmbeddingResponse,
    custom_parser: Callable = hack_parser,
) -> None:
    """Replace OpenAI AsyncEmbeddings.create with a custom implementation.

    Replaces the method at runtime to return a custom Response class
    and use a custom parser. Can be reversed with unpatch_openai_embeddings().

    Args:
        custom_return_cls: Custom return class (BaseModel subclass)
        custom_parser: Custom parser function that receives and returns
            a custom_return_cls instance
    """
    global _original_async_embeddings_create
    from openai.resources.embeddings import AsyncEmbeddings

    # Save original method only on first patch to support idempotent unpatch.
    # Use getattr to handle test scenarios where AsyncEmbeddings may be mocked
    # with a dummy class that lacks a 'create' attribute.
    if _original_async_embeddings_create is None:
        _original_async_embeddings_create = getattr(
            AsyncEmbeddings, "create", None
        )

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

    AsyncEmbeddings.create = patched_create


def unpatch_openai_embeddings() -> None:
    """Restore OpenAI AsyncEmbeddings.create to its original implementation.

    This reverses the effect of patch_openai_embeddings(). If patch has not
    been applied, this function is a no-op (idempotent).
    """
    global _original_async_embeddings_create
    if _original_async_embeddings_create is None:
        return

    from openai.resources.embeddings import AsyncEmbeddings

    AsyncEmbeddings.create = _original_async_embeddings_create
    _original_async_embeddings_create = None
