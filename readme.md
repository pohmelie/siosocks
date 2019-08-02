# siosocks
![Travis status for master branch](https://travis-ci.com/pohmelie/siosocks.svg?branch=master)
![Codecov coverage for master branch](https://codecov.io/gh/pohmelie/siosocks/branch/master/graph/badge.svg)
![Pypi version](https://img.shields.io/pypi/v/siosocks.svg)
![Pypi downloads count](https://pypi-badges.global.ssl.fastly.net/svg?package=siosocks&timeframe=monthly)

[Sans-io](https://sans-io.readthedocs.io/) socks 4/5 client/server library/framework.

# Reasons
* No oneshot socks servers
* Sans-io
* asyncio-ready [`twunnel3`](https://github.com/jvansteirteghem/twunnel3) is dead
* [`aiosocks`](https://github.com/nibrag/aiosocks) do not mimic `asyncio.open_connection` arguments (maybe dead too)
* Fun

# Features
* Only tcp connect (no bind, no udp)
* Both client and server
* Socks versions: 4, 4a, 5
* Socks5 auth: no auth, username/password
* Couple io backends: asyncio, trio, socketserver
* Oneshot socks server

# License
`siosocks` is offered under WTFPL license.

# Requirements
* python 3.6+

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
* asyncio: [`open_connection`](https://docs.python.org/3/library/asyncio-stream.html#asyncio.open_connection)
* trio: [`open_tcp_stream`](https://trio.readthedocs.io/en/stable/reference-io.html#trio.open_tcp_stream)

Extra keyword-only arguments:
* `socks_host`: string
* `socks_port`: integer
* `socks_version`: integer (4 or 5)
* `username`: optional string (default: `None`)
* `password`: optional string (default: `None`)
* `encoding`: optional string (default: `"utf-8"`)
* `socks4_extras`: optional dictionary
* `socks5_extras`: optional dictionary

Extras:
* socks4
    * `user_id`: string (default: `""`)
* socks5
    * None at this moment, added for uniform api
## Server
End user implementations mimic «parent» library server request handlers.
* asyncio: [`start_server`](https://docs.python.org/3/library/asyncio-stream.html#asyncio.start_server)
* trio: [`serve_tcp`](https://trio.readthedocs.io/en/stable/reference-io.html#trio.serve_tcp)
* socketserver: [`ThreadingTCPServer`](https://docs.python.org/3/library/socketserver.html#socketserver.ThreadingTCPServer)

You should use [`partial`](https://docs.python.org/3/library/functools.html#functools.partial) to bind socks specific arguments:
* `allowed_versions`: set of integers (default: `{4, 5}`)
* `username`: optional string (default: `None`)
* `password`: optional string (default: `None`)
* `strict_security_policy`: boolean, if `True` exception will be raised if authentication required and 4 is in allowed versions set (default: `True`)
* `encoding`: optional string (default: `"utf-8"`)

Nothing to say more. Typical usage can be found at [`__main__.py`](https://github.com/pohmelie/siosocks/blob/master/siosocks/__main__.py)

# Example
Shadowsocks-like [client/server](https://github.com/pohmelie/siosocks/blob/master/examples/shadowsocks-like.py). Shadowsocks-like built on top of socks5 and encryption. It have «client», which is actually socks server and «server». So, precisely there are two servers: client side and server side. Purpose of shadowsocks is to encrypt data between «incoming» and «outgoing» servers. In common this looks like:
```
client → «incoming» socks server ⇒ «outgoing» socks server → target server
```
In this scheme `→` means «raw»/not encrypted socks connection, and `⇒` means encrypted somehow data flow.

Example above use Caesar cipher for simplicity (and security of course).

# Roadmap/contibutions
* [ ] add more backends (average)
* [ ] speed up `passthrough` implementation (seems hard)
