import argparse
import asyncio
import contextlib
import functools
import socket

from siosocks.io.asyncio import ServerIO, ClientIO
from siosocks.interface import async_engine
from siosocks.protocol import SocksServer, SocksClient


# This is very strong encryption method, believe me!
def encode(data: bytes):
    return bytes((x + 1) % 0x100 for x in data)


def decode(data: bytes):
    return bytes((x - 1) % 0x100 for x in data)


class CommonProxy:

    def __init__(self, proxied):
        self._proxied = proxied

    def __getattr__(self, name):
        return getattr(self._proxied, name)


class IncomingDecoder(CommonProxy):

    async def read(self, count):
        return decode(await self._proxied.read(count))


class OutgoingEncoder(CommonProxy):

    def write(self, data):
        return self._proxied.write(encode(data))


class RemoteIO(ServerIO):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.incoming_reader = IncomingDecoder(self.incoming_reader)
        self.incoming_writer = OutgoingEncoder(self.incoming_writer)


async def open_connection(host=None, port=None, *, socks_host=None, socks_port=None, socks_version=None):
    reader, writer = await asyncio.open_connection(socks_host, socks_port)
    reader = IncomingDecoder(reader)
    writer = OutgoingEncoder(writer)
    protocol = SocksClient(host, port, socks_version)
    io = ClientIO(reader, writer)
    await async_engine(protocol, io)
    return reader, writer


class LocalIO(ServerIO):

    def __init__(self, *args, remote_host, remote_port, **kwargs):
        super().__init__(*args, **kwargs)
        self.__remote_host = remote_host
        self.__remote_port = remote_port

    async def connect(self, host, port):
        self.outgoing_reader, self.outgoing_writer = await open_connection(host, port,
                                                                           socks_host=self.__remote_host,
                                                                           socks_port=self.__remote_port,
                                                                           socks_version=5)


async def socks_server_handler(reader, writer, *, io_factory, **kwargs):
    try:
        async with io_factory(reader, writer) as io:
            await async_engine(SocksServer(**kwargs), io)
    finally:
        writer.close()


def serve(ns):
    if ns.io_factory is LocalIO:
        f = functools.partial(ns.io_factory, remote_host=ns.remote_host, remote_port=ns.remote_port)
    else:
        f = ns.io_factory
    handler = functools.partial(socks_server_handler, io_factory=f)
    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(handler, host=ns.host, port=ns.port)
    server = loop.run_until_complete(coro)
    addresses = []
    for sock in server.sockets:
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host, port, *_ = sock.getsockname()
            addresses.append(f"{host}:{port}")
    print(f"Shadowsocks-like serving on {', '.join(addresses)}")
    with contextlib.suppress(KeyboardInterrupt):
        loop.run_forever()


parser = argparse.ArgumentParser(description="Shadowsocks-like proxy server")
parser.add_argument("--host", default=None, help="Shadowsocks-like server host [default: %(default)s]")
parser.add_argument("--port", default=1080, type=int, help="Shadowsocks-like server port [default: %(default)s]")
sub_commands = parser.add_subparsers(dest="command")
sub_commands.required = True
p = sub_commands.add_parser("local")
p.set_defaults(io_factory=LocalIO)
p.add_argument("--remote-host", required=True)
p.add_argument("--remote-port", type=int, default=1080)
p = sub_commands.add_parser("remote")
p.set_defaults(io_factory=RemoteIO)

ns = parser.parse_args()
serve(ns)
