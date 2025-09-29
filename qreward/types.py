from collections.abc import Callable
from typing import Tuple, Union

# socket options type
SOCKET_OPTION = Union[
    Tuple[int, int, int],
    Tuple[int, int, Union[bytes, bytearray]],
    Tuple[int, int, None, int],
]


# simple retry types
RetryPredicate = Callable[[Exception], bool]
BackoffGenerator = Callable[[int], float]
