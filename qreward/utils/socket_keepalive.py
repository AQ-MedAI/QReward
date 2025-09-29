import socket
import sys
from typing import List

from requests.adapters import HTTPAdapter

from qreward.types import SOCKET_OPTION


def aiohttp_keepalive_socket_factory(
    addr_info,
    keepalive_secs: int = 60,
    keepalive_interval: int = 30,
    keepalive_cnt: int = 3,
) -> socket.socket:
    """aiohttp 保持 keepalive 连接的 socket 工厂函数

    Args:
        addr_info (tuple): socket 地址信息
        keepalive_secs (int, optional): 保持 keepalive 连接的时间, 默认 60 秒
        keepalive_interval (int, optional): 保持 keepalive 连接的间隔, 默认 30 秒
        keepalive_cnt (int, optional): 保持 keepalive 探测的次数, 默认 3 次

    Returns:
        socket: socket 对象
    """

    family, type_, proto, _, _ = addr_info

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    if sys.platform.startswith("linux"):
        # Linux
        sock.setsockopt(
            socket.IPPROTO_TCP,
            socket.TCP_KEEPIDLE,
            keepalive_secs,
        )
    elif sys.platform.startswith("darwin"):
        # Darwin
        sock.setsockopt(
            socket.IPPROTO_TCP,
            socket.TCP_KEEPALIVE,
            keepalive_secs,
        )

    sock.setsockopt(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPINTVL,
        keepalive_interval,
    )
    sock.setsockopt(
        socket.IPPROTO_TCP,
        socket.TCP_KEEPCNT,
        keepalive_cnt,
    )
    return sock


def httpx_keepalive_socket(
    keepalive_secs: int = 60,
    keepalive_interval: int = 30,
    keepalive_cnt: int = 3,
) -> List[SOCKET_OPTION]:
    """
    httpx 保持 keepalive 连接的 socket 选项

    :param keepalive_secs: 保持 keepalive 连接的时间, 默认 60 秒
    :param keepalive_interval: 保持 keepalive 连接的间隔, 默认 30 秒
    :param keepalive_cnt: 保持 keepalive 探测的次数, 默认 3 次
    :return: socket 选项列表
    """

    socket_options = [
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),  # 启用keepalive
    ]

    if sys.platform.startswith("linux"):
        socket_options.append((
            socket.IPPROTO_TCP,
            socket.TCP_KEEPIDLE,
            keepalive_secs,
        ))
    elif sys.platform.startswith("darwin"):
        socket_options.append((
            socket.IPPROTO_TCP,
            socket.TCP_KEEPALIVE,
            keepalive_secs,
        ))

    socket_options.append((
        socket.IPPROTO_TCP,
        socket.TCP_KEEPINTVL,
        keepalive_interval,
    ))
    socket_options.append((
        socket.IPPROTO_TCP,
        socket.TCP_KEEPCNT,
        keepalive_cnt,
    ))
    return socket_options


class RequestsTCPKeepAliveAdapter(HTTPAdapter):
    """自定义适配器：注入keepalive socket选项"""

    def __init__(self, *args, **kwargs):
        self._default = httpx_keepalive_socket()
        self.socket_options = kwargs.pop("socket_options", self._default)
        super().__init__(*args, **kwargs)

    def init_poolmanager(
        self,
        connections,
        maxsize,
        block=False,
        **pool_kwargs,
    ):
        if self.socket_options is not None:
            pool_kwargs['socket_options'] = self.socket_options
        super().init_poolmanager(connections, maxsize, block, **pool_kwargs)
