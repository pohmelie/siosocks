# siosocks
[![Github actions status for master branch](https://github.com/pohmelie/siosocks/actions/workflows/ci.yml/badge.svg?branch=master)(https://github.com/pohmelie/siosocks/actions)
[![Codecov coverage for master branch](https://codecov.io/gh/pohmelie/siosocks/branch/master/graph/badge.svg)](https://codecov.io/gh/pohmelie/siosocks)
[![Pypi version](https://img.shields.io/pypi/v/siosocks.svg)](https://pypi.org/project/siosocks/)
[![Pypi downloads count](https://img.shields.io/pypi/dm/siosocks)](https://pypi.org/project/siosocks/)

[Sans-io](https://sans-io.readthedocs.io/) socks 4/5 client/server library/framework.

# Reasons
- No one-shot socks servers
- Sans-io
- asyncio-ready [`twunnel3`](https://github.com/jvansteirteghem/twunnel3) is dead
- [`aiosocks`](https://github.com/nibrag/aiosocks) do not mimic `asyncio.open_connection` arguments (maybe dead too)
- Fun

# Features
- Only tcp connect (no bind, no udp)
- Both client and server
- Socks versions: 4, 4a, 5
- Socks5 auth: no auth, username/password
- Couple io backends: asyncio, trio, socketserver
- One-shot socks server (`python -m siosocks`)

# License
`siosocks` is offered under MIT license.

# Requirements
- python 3.8+

# IO implementation matrix

Framework | Client | Server
--- | :---: | :---:
asyncio | + | +
trio | + | +
socket | | +

Feel free to make it bigger :wink:

# Usage
End user implementations mimic «parent» library api.
## Client
- asyncio: [`open_connection`](https://docs.python.org/3/library/asyncio-stream.html#asyncio.open_connection)
- trio: [`open_tcp_stream`](https://trio.readthedocs.io/en/stable/reference-io.html#trio.open_tcp_stream)

Extra keyword-only arguments:
- `socks_host`: string
- `socks_port`: integer
- `socks_version`: integer (4 or 5)
- `username`: optional string (default: `None`)
- `password`: optional string (default: `None`)
- `encoding`: optional string (default: `"utf-8"`)
- `socks4_extras`: optional dictionary
- `socks5_extras`: optional dictionary

Extras:
- socks4
    - `user_id`: string (default: `""`)
- socks5
    - None at this moment, added for uniform api
## Server
End user implementations mimic «parent» library server request handlers.
- asyncio: [`start_server`](https://docs.python.org/3/library/asyncio-stream.html#asyncio.start_server)
- trio: [`serve_tcp`](https://trio.readthedocs.io/en/stable/reference-io.html#trio.serve_tcp)
- socketserver: [`ThreadingTCPServer`](https://docs.python.org/3/library/socketserver.html#socketserver.ThreadingTCPServer)

You should use [`partial`](https://docs.python.org/3/library/functools.html#functools.partial) to bind socks specific arguments:
- `allowed_versions`: set of integers (default: `{4, 5}`)
- `username`: optional string (default: `None`)
- `password`: optional string (default: `None`)
- `strict_security_policy`: boolean, if `True` exception will be raised if authentication required and 4 is in allowed versions set (default: `True`)
- `encoding`: optional string (default: `"utf-8"`)

Nothing to say more. Typical usage can be found at [`__main__.py`](https://github.com/pohmelie/siosocks/blob/master/siosocks/__main__.py)

# Examples
## High-level
This section will use `asyncio` as backend, since it is main target/reason for `siosocks`
### Client
``` python
import asyncio

from siosocks.io.asyncio import open_connection


HOST = "api.ipify.org"
REQ = """GET /?format=json HTTP/1.1
Host: api.ipify.org
User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: en,en-US;q=0.7,ru;q=0.3
Accept-Encoding: gzip, deflate
DNT: 1
Connection: keep-alive
Upgrade-Insecure-Requests: 1
Cache-Control: max-age=0

"""


async def main():
    # assume we have tor started
    r, w = await open_connection(HOST, 80, socks_host="localhost", socks_port=9050, socks_version=5)
    w.write(REQ.replace("\n", "\r\n").encode())
    await w.drain()
    print(await r.read(8192))
    w.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
```
### Server
``` python
import socket
import asyncio
import contextlib

from siosocks.io.asyncio import socks_server_handler


loop = asyncio.get_event_loop()
server = loop.run_until_complete(asyncio.start_server(socks_server_handler, port=1080))
addresses = []
for sock in server.sockets:
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        host, port, *_ = sock.getsockname()
        addresses.append(f"{host}:{port}")
print(f"Socks4/5 proxy serving on {', '.join(addresses)}")
with contextlib.suppress(KeyboardInterrupt):
    loop.run_forever()
```
But if you just want one-shot socks server then try:
``` bash
python -m siosocks
```
This will start socks 4, 5 server on all interfaces on 1080 port. For more information try `--help`
``` bash
python -m siosocks --help
usage: siosocks [-h] [--backend {asyncio,socketserver,trio}] [--host HOST]
                [--port PORT] [--family {ipv4,ipv6,auto}] [--socks SOCKS]
                [--username USERNAME] [--password PASSWORD]
                [--encoding ENCODING] [--no-strict] [-v]

Socks proxy server

optional arguments:
  -h, --help            show this help message and exit
  --backend {asyncio,socketserver,trio}
                        Socks server backend [default: asyncio]
  --host HOST           Socks server host [default: None]
  --port PORT           Socks server port [default: 1080]
  --family {ipv4,ipv6,auto}
                        Socket family [default: auto]
  --socks SOCKS         Socks protocol version [default: []]
  --username USERNAME   Socks auth username [default: None]
  --password PASSWORD   Socks auth password [default: None]
  --encoding ENCODING   String encoding [default: utf-8]
  --no-strict           Allow multiversion socks server, when socks5 used with
                        username/password auth [default: False]
  -v, --version         Show siosocks version
```

### Exceptions
`siosocks` have unified exception for all types of socks-related errors:
``` python
import asyncio

from siosocks.exceptions import SocksException
from siosocks.io.asyncio import open_connection


async def main():
    try:
        r, w = await open_connection("127.0.0.1", 80, socks_host="localhost", socks_port=9050, socks_version=5)
    except SocksException:
        ...
    else:
        # at this point all socks-related tasks done and returned reader and writer
        # are just plain asyncio objects without any siosocks proxies


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
```

## Low-level
Shadowsocks-like [client/server](https://github.com/pohmelie/siosocks/blob/master/examples/shadowsocks-like.py). Shadowsocks-like built on top of socks5 and encryption. It have «client», which is actually socks server and «server». So, precisely there are two servers: client side and server side. Purpose of shadowsocks is to encrypt data between «incoming» and «outgoing» servers. In common this looks like:
```
client (non-encrypted socks) «incoming» socks server (encrypted socks) «outgoing» socks server (non-socks connection) target server
```
Example above use Caesar cipher for simplicity (and security of course).

# Roadmap/contibutions
- [ ] add more backends (average)
- [ ] speed up `passthrough` implementation (seems hard)
- [ ] add client redirection
