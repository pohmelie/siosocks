import argparse
import sys
import functools
import socket
import asyncio
import socketserver
import contextlib

from . import __version__
from .io.asyncio import socks_server_handler as asyncio_socks_server_handler
from .io.socket import socks_server_handler as socket_socks_server_handler
from .protocol import DEFAULT_ENCODING


parser = argparse.ArgumentParser("siosocks", description="Socks proxy server")
parser.add_argument("--backend", default="asyncio", choices=["asyncio", "socketserver", "trio"],
                    help="Socks server backend [default: %(default)s]")
parser.add_argument("--host", default=None, help="Socks server host [default: %(default)s]")
parser.add_argument("--port", default=1080, type=int, help="Socks server port [default: %(default)s]")
parser.add_argument("--family", choices=("ipv4", "ipv6", "auto"), default="auto",
                    help="Socket family [default: %(default)s]")
parser.add_argument("--socks", action="append", type=int, default=[],
                    help="Socks protocol version [default: %(default)s]")
parser.add_argument("--username", default=None, help="Socks auth username [default: %(default)s]")
parser.add_argument("--password", default=None, help="Socks auth password [default: %(default)s]")
parser.add_argument("--encoding", default=DEFAULT_ENCODING, help="String encoding [default: %(default)s]")
parser.add_argument("--no-strict", default=False, action="store_true",
                    help="Allow multiversion socks server, when socks5 used with username/password auth "
                         "[default: %(default)s]")
parser.add_argument("-v", "--version", action="store_true", help="Show siosocks version")
ns = parser.parse_args()
if ns.version:
    print(__version__)
    sys.exit()

family = {
    "ipv4": socket.AF_INET,
    "ipv6": socket.AF_INET6,
    "auto": socket.AF_UNSPEC,
}[ns.family]
socks_versions = set(ns.socks) or {4, 5}
if 4 in socks_versions and ns.username is not None:
    print("Socks4 do not provide auth methods, but socks4 allowed "
          "and auth required and strict security policy enabled")
    sys.exit(1)


def asyncio_main(socks_versions, family, ns):

    async def main():
        server = await asyncio.start_server(handler, host=ns.host, port=ns.port, family=family)
        addresses = []
        for sock in server.sockets:
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                host, port, *_ = sock.getsockname()
                addresses.append(f"{host}:{port}")
        print(f"Socks{socks_versions} proxy serving on {', '.join(addresses)}")
        with contextlib.suppress(KeyboardInterrupt):
            await server.serve_forever()

    handler = functools.partial(
        asyncio_socks_server_handler,
        allowed_versions=socks_versions,
        username=ns.username,
        password=ns.password,
        strict_security_policy=not ns.no_strict,
        encoding=ns.encoding,
    )
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(main())


def socketserver_main(socks_versions, family, ns):
    handler = functools.partial(
        socket_socks_server_handler,
        socks_protocol_kw=dict(
            allowed_versions=socks_versions,
            username=ns.username,
            password=ns.password,
            strict_security_policy=not ns.no_strict,
            encoding=ns.encoding,
        ),
    )
    with socketserver.ThreadingTCPServer((ns.host or "0.0.0.0", ns.port), handler) as server:
        server.socket.settimeout(0.5)
        h, p = server.server_address
        print(f"Socks{socks_versions} porxy serving on {h}:{p}")
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


def trio_main(socks_versions, family, ns):
    import trio
    from .io.trio import socks_server_handler as trio_socks_server_handler

    async def main():
        with contextlib.suppress(KeyboardInterrupt):
            async with trio.open_nursery() as n:
                serve_tcp = functools.partial(trio.serve_tcp, handler, ns.port, host=ns.host)
                listeners = await n.start(serve_tcp)
                addresses = []
                for listener in listeners:
                    sock = listener.socket
                    if sock.family in (socket.AF_INET, socket.AF_INET6):
                        host, port, *_ = sock.getsockname()
                        addresses.append(f"{host}:{port}")
                print(f"Socks{socks_versions} proxy serving on {', '.join(addresses)}")

    handler = functools.partial(
        trio_socks_server_handler,
        allowed_versions=socks_versions,
        username=ns.username,
        password=ns.password,
        strict_security_policy=not ns.no_strict,
        encoding=ns.encoding,
    )
    trio.run(main)


backends = {
    "asyncio": asyncio_main,
    "socketserver": socketserver_main,
    "trio": trio_main,
}
try:
    backends[ns.backend](socks_versions, family, ns)
except ImportError:
    print(f"{ns.backend} backend dependencies are not installed")
    raise
