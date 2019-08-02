import asyncio
import socketserver
import threading
from functools import partial

import pytest

from siosocks.io.socket import socks_server_handler
from siosocks.io.asyncio import open_connection


HOST = "127.0.0.1"
MESSAGE = b"socks work!"


@pytest.fixture
async def endpoint_port(unused_tcp_port_factory):
    port = unused_tcp_port_factory()

    async def handler(r, w):
        b = await r.read(8192)
        w.write(b)
        await w.drain()
        w.close()

    server = await asyncio.start_server(handler, HOST, port)
    yield port
    server.close()
    await server.wait_closed()


@pytest.fixture
def socks_server_port(unused_tcp_port_factory):
    port = unused_tcp_port_factory()
    handler = partial(socks_server_handler, socks_protocol_kw={})
    with socketserver.ThreadingTCPServer((HOST, port), handler) as server:
        server.socket.settimeout(0.5)
        thread = threading.Thread(target=server.serve_forever, args=[0.01])
        thread.start()
        yield port
        server.shutdown()
        thread.join()


@pytest.mark.asyncio
async def test_connection_direct_success(endpoint_port):
    r, w = await open_connection(HOST, endpoint_port)
    w.write(MESSAGE)
    m = await r.read(8192)
    assert m == MESSAGE


@pytest.mark.asyncio
async def test_connection_socks_success(endpoint_port, socks_server_port):
    r, w = await open_connection(HOST, endpoint_port,
                                 socks_host=HOST, socks_port=socks_server_port, socks_version=4)
    w.write(MESSAGE)
    m = await r.read(8192)
    assert m == MESSAGE


@pytest.mark.asyncio
async def test_connection_partly_passed_error():
    with pytest.raises(ValueError):
        await open_connection(HOST, endpoint_port,
                              socks_host=HOST, socks_port=socks_server_port)
