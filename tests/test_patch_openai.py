import pytest
from unittest.mock import MagicMock, patch

from openai.types.create_embedding_response import Embedding, Usage

import qreward.client.patch_openai as my_module


def test_hack_parser_success_and_failure():
    """合法构造 HackCreateEmbeddingResponse，测试 hack_parser 全分支"""

    # 使用 MagicMock(spec=...) 确保符合 Pydantic 类型要求
    fake_embedding = MagicMock(spec=Embedding)
    fake_usage = MagicMock(spec=Usage)

    # 正常情况
    obj = my_module.HackCreateEmbeddingResponse(
        embeddings=[fake_embedding],
        model="my_model",
        object="list",
        usage=fake_usage,
    )
    assert my_module.hack_parser(obj) is obj

    # 异常情况
    obj_empty = my_module.HackCreateEmbeddingResponse(
        embeddings=[],
        model="my_model",
        object="list",
        usage=fake_usage,
    )
    with pytest.raises(ValueError):
        my_module.hack_parser(obj_empty)


@pytest.mark.asyncio
async def test_patch_openai_embeddings_branches():
    """测试 encoding_format 未给出（设为 base64）和已给出（保留原值）两个分支"""

    class DummyAsyncEmbeddings:
        pass

    dummy_instance = DummyAsyncEmbeddings()

    async def fake_post(self, url, body, options, cast_to):
        dummy_instance._called_args = (url, body, options, cast_to)
        return "POST_RESULT"

    dummy_instance._post = fake_post.__get__(
        dummy_instance,
        DummyAsyncEmbeddings,
    )

    # 分支1：未给出 encoding_format -> 强制设置为 base64
    with (
        patch(
            "openai.resources.embeddings.AsyncEmbeddings",
            DummyAsyncEmbeddings,
        ),
        patch.object(my_module, "is_given", lambda x: False),
        patch.object(my_module, "maybe_transform", lambda p, _: p),
        patch.object(my_module,
                     "make_request_options",
                     lambda **kwargs: kwargs),
    ):

        my_module.patch_openai_embeddings()
        result = await dummy_instance.create(
            input="abc", model="mymodel", encoding_format=None
        )
        assert result == "POST_RESULT"

        url, body, options, cast_to = dummy_instance._called_args
        assert body["encoding_format"] == "base64"
        assert cast_to == my_module.HackCreateEmbeddingResponse
        assert options["post_parser"] == my_module.hack_parser

    # 分支2：已给出 encoding_format -> 保留原值
    with (
        patch(
            "openai.resources.embeddings.AsyncEmbeddings",
            DummyAsyncEmbeddings,
        ),
        patch.object(my_module, "is_given", lambda x: True),
        patch.object(my_module, "maybe_transform", lambda p, _: p),
        patch.object(my_module,
                     "make_request_options",
                     lambda **kwargs: kwargs),
    ):

        my_module.patch_openai_embeddings()
        _ = await dummy_instance.create(
            input="abc2",
            model="mymodel",
            encoding_format="float",
        )
        url, body, options, _ = dummy_instance._called_args
        assert body["encoding_format"] == "float"


@pytest.mark.asyncio
async def test_patch_with_custom_class_and_parser():
    """测试自定义返回类和 parser"""

    class CustomReturnCls:
        pass

    def custom_parser(obj):
        return f"parsed:{obj}"

    class DummyAsyncEmbeddings:
        pass

    dummy_instance = DummyAsyncEmbeddings()

    async def fake_post(self, url, body, options, cast_to):
        return (f"cast_to:{cast_to.__name__}, "
                f"parser:{options['post_parser']('OBJ')}")

    dummy_instance._post = fake_post.__get__(
        dummy_instance,
        DummyAsyncEmbeddings,
    )

    with (
        patch(
            "openai.resources.embeddings.AsyncEmbeddings",
            DummyAsyncEmbeddings,
        ),
        patch.object(my_module, "is_given", lambda x: True),
        patch.object(my_module, "maybe_transform", lambda p, _: p),
        patch.object(my_module,
                     "make_request_options",
                     lambda **kwargs: kwargs),
    ):

        my_module.patch_openai_embeddings(CustomReturnCls, custom_parser)
        result = await dummy_instance.create(
            input="x", model="y", encoding_format="float"
        )

        assert "CustomReturnCls" in result
        assert "parsed:OBJ" in result


# ============================================================
# Sprint 4: unpatch_openai_embeddings tests
# ============================================================

from qreward.client.patch_openai import unpatch_openai_embeddings  # noqa: E402


@pytest.fixture(autouse=False)
def _reset_patch_state():
    """Reset the global _original_async_embeddings_create state before and
    after each unpatch-related test to ensure test isolation from prior
    patches."""
    from openai.resources.embeddings import AsyncEmbeddings

    # Unpatch if previously patched by other tests
    unpatch_openai_embeddings()
    # Reset the global to None so we start clean
    my_module._original_async_embeddings_create = None
    original = AsyncEmbeddings.create
    yield original
    # Cleanup: restore original after test
    unpatch_openai_embeddings()
    my_module._original_async_embeddings_create = None
    AsyncEmbeddings.create = original


def test_unpatch_openai_embeddings(_reset_patch_state):
    """Verify unpatch restores AsyncEmbeddings.create to original method."""
    from openai.resources.embeddings import AsyncEmbeddings

    original_create = _reset_patch_state

    # Apply patch
    my_module.patch_openai_embeddings()
    assert AsyncEmbeddings.create is not original_create

    # Unpatch — should restore
    unpatch_openai_embeddings()
    assert AsyncEmbeddings.create is original_create


def test_unpatch_idempotent(_reset_patch_state):
    """Verify calling unpatch multiple times is safe (no-op if not patched)."""
    from openai.resources.embeddings import AsyncEmbeddings

    original_create = _reset_patch_state

    # Unpatch without prior patch — should be no-op
    unpatch_openai_embeddings()
    assert AsyncEmbeddings.create is original_create

    # Patch then unpatch twice — second unpatch should be no-op
    my_module.patch_openai_embeddings()
    unpatch_openai_embeddings()
    assert AsyncEmbeddings.create is original_create

    unpatch_openai_embeddings()
    assert AsyncEmbeddings.create is original_create


def test_patch_unpatch_patch_cycle(_reset_patch_state):
    """Verify patch -> unpatch -> patch cycle works correctly."""
    from openai.resources.embeddings import AsyncEmbeddings

    original_create = _reset_patch_state

    # First patch
    my_module.patch_openai_embeddings()
    patched_create = AsyncEmbeddings.create
    assert patched_create is not original_create

    # Unpatch
    unpatch_openai_embeddings()
    assert AsyncEmbeddings.create is original_create

    # Re-patch
    my_module.patch_openai_embeddings()
    assert AsyncEmbeddings.create is not original_create

    # Cleanup
    unpatch_openai_embeddings()
    assert AsyncEmbeddings.create is original_create
