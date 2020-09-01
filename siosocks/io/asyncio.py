import asyncio
import logging

from ..exceptions import SocksException
from ..interface import AbstractSocksIO, async_engine
from ..protocol import SocksServer, SocksClient, DEFAULT_ENCODING
from .const import DEFAULT_BLOCK_SIZE


logger = logging.getLogger(__name__)


class ServerIO(AbstractSocksIO):

    def __init__(self, reader, writer):
        self.incoming_reader = reader
        self.incoming_writer = writer
        self.outgoing_reader = None
        self.outgoing_writer = None

    async def read(self):
        return await self.incoming_reader.read(DEFAULT_BLOCK_SIZE)

    async def write(self, data):
        self.incoming_writer.write(data)
        await self.incoming_writer.drain()

    async def connect(self, host, port):
        logger.debug("connect call %s:%d", host, port)
        self.outgoing_reader, self.outgoing_writer = await asyncio.open_connection(host, port)

    async def passthrough(self):
        logger.debug("passthrough started")
        coros = [
            self._sink(self.incoming_reader, self.outgoing_writer),
            self._sink(self.outgoing_reader, self.incoming_writer),
        ]
        tasks = {asyncio.ensure_future(coro) for coro in coros}
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.wait(tasks)

    @staticmethod
    async def _sink(r, w):
        while True:
            b = await r.read(DEFAULT_BLOCK_SIZE)
            if not b:
                break
            w.write(b)
            await w.drain()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        if self.outgoing_writer is not None:
            self.outgoing_writer.close()


async def socks_server_handler(reader, writer, **kwargs):
    try:
        async with ServerIO(reader, writer) as io:
            await async_engine(SocksServer(**kwargs), io)
    finally:
        writer.close()


class ClientIO(AbstractSocksIO):

    def __init__(self, reader, writer):
        self.r = reader
        self.w = writer

    async def read(self):
        return await self.r.read(DEFAULT_BLOCK_SIZE)

    async def write(self, data):
        self.w.write(data)
        await self.w.drain()

    async def connect(self, *_):
        raise RuntimeError("ClientIO.connect should not be called")

    async def passthrough(self):
        return


async def open_connection(host=None, port=None, *, socks_host=None, socks_port=None,
                          socks_version=None, username=None, password=None, encoding=DEFAULT_ENCODING,
                          socks4_extras={}, socks5_extras={}, **open_connection_extras):
    socks_required = socks_host, socks_port, socks_version
    socks_enabled = all(socks_required)
    socks_disabled = not any(socks_required)
    if socks_enabled == socks_disabled:
        raise SocksException("Partly passed socks required arguments: "
                             "socks_host = {!r}, socks_port = {!r}, socks_version = {!r}".format(*socks_required))
    if socks_enabled:
        reader, writer = await asyncio.open_connection(socks_host, socks_port, **open_connection_extras)
        protocol = SocksClient(host, port, socks_version, username=username, password=password, encoding=encoding,
                               socks4_extras=socks4_extras, socks5_extras=socks5_extras)
        io = ClientIO(reader, writer)
        await async_engine(protocol, io)
    else:
        reader, writer = await asyncio.open_connection(host, port, **open_connection_extras)
    return reader, writer
