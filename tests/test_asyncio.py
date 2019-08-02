import asyncio

import pytest

from siosocks.io.asyncio import socks_server_handler, open_connection


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
async def socks_server_port(unused_tcp_port_factory):
    port = unused_tcp_port_factory()
    server = await asyncio.start_server(socks_server_handler, HOST, port)
    yield port
    server.close()
    await server.wait_closed()


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
