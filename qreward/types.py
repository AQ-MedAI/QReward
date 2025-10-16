from collections.abc import Callable, Coroutine
from typing import Any, Tuple, Union

from httpx import Request, Response

# socket options type
SOCKET_OPTION = Union[
    Tuple[int, int, int],
    Tuple[int, int, Union[bytes, bytearray]],
    Tuple[int, int, None, int],
]


# simple retry types
RetryPredicate = Callable[[Exception], bool]
BackoffGenerator = Callable[[int], float]


# httpx hook type
RequestHook = Callable[[Request], None] | Coroutine[Any, Any, None]
ResponseHook = Callable[[Response], None] | Coroutine[Any, Any, None]
