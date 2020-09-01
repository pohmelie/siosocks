from functools import partial

import trio
import pytest

from siosocks.exceptions import SocksException
from siosocks.io.trio import socks_server_handler, open_tcp_stream


# TODO: Use fixtures after https://github.com/pytest-dev/pytest-asyncio/issues/124 resolved

HOST = "127.0.0.1"
MESSAGE = b"socks work!"


async def endpoint(nursery):

    async def handler(stream):
        async with stream:
            while True:
                b = await stream.receive_some(8192)
                if not b:
                    break
                await stream.send_all(b)

    listeners = await nursery.start(partial(trio.serve_tcp, handler, 0, host=HOST))
    _, port, *_ = listeners[0].socket.getsockname()
    return port


async def socks(nursery):
    listeners = await nursery.start(partial(trio.serve_tcp, socks_server_handler, 0, host=HOST))
    _, port, *_ = listeners[0].socket.getsockname()
    return port


@pytest.mark.trio
async def test_connection_direct_success(nursery):
    endpoint_port = await endpoint(nursery)
    stream = await open_tcp_stream(HOST, endpoint_port)
    async with stream:
        await stream.send_all(MESSAGE)
        m = await stream.receive_some(8192)
        assert m == MESSAGE


@pytest.mark.trio
async def test_connection_socks_success(nursery):
    endpoint_port = await endpoint(nursery)
    socks_server_port = await socks(nursery)
    stream = await open_tcp_stream(HOST, endpoint_port,
                                   socks_host=HOST, socks_port=socks_server_port, socks_version=4)
    async with stream:
        await stream.send_all(MESSAGE)
        m = await stream.receive_some(8192)
        assert m == MESSAGE


@pytest.mark.trio
async def test_connection_partly_passed_error(nursery):
    endpoint_port = await endpoint(nursery)
    socks_server_port = await socks(nursery)
    with pytest.raises(SocksException):
        await open_tcp_stream(HOST, endpoint_port,
                              socks_host=HOST, socks_port=socks_server_port)
