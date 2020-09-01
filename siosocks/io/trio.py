import logging

import trio

from ..exceptions import SocksException
from ..interface import AbstractSocksIO, async_engine
from ..protocol import SocksServer, SocksClient, DEFAULT_ENCODING
from .const import DEFAULT_BLOCK_SIZE


logger = logging.getLogger(__name__)


class ServerIO(AbstractSocksIO):

    def __init__(self, stream):
        self.incoming_stream = stream
        self.outgoing_stream = None

    async def read(self):
        return await self.incoming_stream.receive_some(DEFAULT_BLOCK_SIZE)

    async def write(self, data):
        await self.incoming_stream.send_all(data)

    async def connect(self, host, port):
        logger.debug("connect call %s:%d", host, port)
        self.outgoing_stream = await trio.open_tcp_stream(host, port)

    async def passthrough(self):
        logger.debug("passthrough started")
        async with trio.open_nursery() as n:
            n.start_soon(self._sink, self.incoming_stream, self.outgoing_stream)
            n.start_soon(self._sink, self.outgoing_stream, self.incoming_stream)

    @staticmethod
    async def _sink(r, w):
        while True:
            b = await r.receive_some(DEFAULT_BLOCK_SIZE)
            if not b:
                break
            await w.send_all(b)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        if self.outgoing_stream is not None:
            await self.outgoing_stream.aclose()


async def socks_server_handler(stream, **kwargs):
    try:
        async with stream, ServerIO(stream) as io:
            await async_engine(SocksServer(**kwargs), io)
    except Exception:
        logger.exception("handler failed")


class ClientIO(AbstractSocksIO):

    def __init__(self, stream):
        self.stream = stream

    async def read(self):
        data = await self.stream.receive_some(DEFAULT_BLOCK_SIZE)
        return data

    async def write(self, data):
        await self.stream.send_all(data)

    async def connect(self, *_):
        raise RuntimeError("ClientIO.connect should not be called")

    async def passthrough(self):
        return


async def open_tcp_stream(host, port, *, socks_host=None, socks_port=None,
                          socks_version=None, username=None, password=None, encoding=DEFAULT_ENCODING,
                          socks4_extras={}, socks5_extras={}, **open_tcp_stream_extras):
    socks_required = socks_host, socks_port, socks_version
    socks_enabled = all(socks_required)
    socks_disabled = not any(socks_required)
    if socks_enabled == socks_disabled:
        raise SocksException("Partly passed socks required arguments: "
                             "socks_host = {!r}, socks_port = {!r}, socks_version = {!r}".format(*socks_required))
    if socks_enabled:
        stream = await trio.open_tcp_stream(socks_host, socks_port, **open_tcp_stream_extras)
        protocol = SocksClient(host, port, socks_version, username=username, password=password, encoding=encoding,
                               socks4_extras=socks4_extras, socks5_extras=socks5_extras)
        io = ClientIO(stream)
        await async_engine(protocol, io)
    else:
        stream = await trio.open_tcp_stream(host, port, **open_tcp_stream_extras)
    return stream
