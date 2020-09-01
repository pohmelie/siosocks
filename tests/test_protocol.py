import collections
import contextlib

import pytest

from siosocks.exceptions import SocksException
from siosocks.protocol import SocksClient, SocksServer
from siosocks.sansio import SansIORW


class ConnectionFailed(Exception):
    pass


class Node:

    def __init__(self, generator):
        self.generator = generator
        self.receive = [None]
        self.send = None
        self.calls = collections.defaultdict(int)

    def run(self, *, fail_connection=False):
        gen_method = self.generator.send
        while True:
            request = gen_method(self.receive.pop(0))
            gen_method = self.generator.send
            method = request.pop("method")
            self.calls[method] += 1
            if method == "write":
                data = request["data"]
                if data:
                    self.send.append(data)
                self.receive.append(None)
            elif method == "connect":
                if fail_connection:
                    gen_method = self.generator.throw
                    self.receive.append(ConnectionFailed("test"))
                else:
                    self.receive.append(None)
            elif method == "passthrough":
                return
            elif method == "read":
                if not self.receive:
                    return
            else:
                raise ValueError(f"Unexpected method {method}")


def rotor(client, server, *, fail_connection=False):
    nodes = collections.deque([Node(client), Node(server)])
    nodes[0].send = nodes[1].receive
    nodes[1].send = nodes[0].receive
    while not all(n.calls["passthrough"] for n in nodes):
        with contextlib.suppress(ConnectionFailed):
            nodes[0].run(fail_connection=fail_connection)
        nodes.rotate(1)


def test_client_bad_socks_version():

    def server():
        io = SansIORW(encoding="utf-8")
        yield from io.read_exactly(1)

    with pytest.raises(SocksException):
        rotor(SocksClient("abc", 123, 6), server())


def test_client_socks4_and_auth():

    def server():
        io = SansIORW(encoding="utf-8")
        yield from io.read_exactly(1)

    with pytest.raises(SocksException):
        rotor(SocksClient("abc", 123, 4, username="yoba", password="foo"), server())


def test_client_socks4_connection_failed():

    def server():
        io = SansIORW(encoding="utf-8")
        version, command, port, ipv4 = yield from io.read_struct("BBH4s")
        assert version == 4
        assert command == 1
        assert port == 123
        assert ipv4 == b"\x7f\x00\x00\x01"
        user_id = yield from io.read_c_string()
        assert user_id == "yoba"
        yield from io.connect(ipv4, port)
        yield from io.write_struct("BBH4s", 0, 0x5b, 0, b"\x00" * 4)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("127.0.0.1", 123, 4, socks4_extras=dict(user_id="yoba")), server())


@pytest.mark.skip("this check removed")
def test_client_socks4_redirect_not_supported_by_port():

    def server():
        io = SansIORW(encoding="utf-8")
        version, command, port, ipv4 = yield from io.read_struct("BBH4s")
        assert version == 4
        assert command == 1
        assert port == 123
        assert ipv4 == b"\x7f\x00\x00\x01"
        user_id = yield from io.read_c_string()
        assert user_id == "yoba"
        yield from io.connect(ipv4, port)
        yield from io.write_struct("BBH4s", 0, 0x5a, 666, b"\x00" * 4)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("127.0.0.1", 123, 4, socks4_extras=dict(user_id="yoba")), server())


@pytest.mark.skip("this check removed")
def test_client_socks4_redirect_not_supported_by_host():

    def server():
        io = SansIORW(encoding="utf-8")
        version, command, port, ipv4 = yield from io.read_struct("BBH4s")
        assert version == 4
        assert command == 1
        assert port == 123
        assert ipv4 == b"\x7f\x00\x00\x01"
        user_id = yield from io.read_c_string()
        assert user_id == "yoba"
        yield from io.connect(ipv4, port)
        yield from io.write_struct("BBH4s", 0, 0x5a, 0, b"\x7f\x00\x00\x01")
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("127.0.0.1", 123, 4, socks4_extras=dict(user_id="yoba")), server())


def test_client_socks4_success_by_ipv4():

    def server():
        io = SansIORW(encoding="utf-8")
        version, command, port, ipv4 = yield from io.read_struct("BBH4s")
        assert version == 4
        assert command == 1
        assert port == 123
        assert ipv4 == b"\x7f\x00\x00\x01"
        user_id = yield from io.read_c_string()
        assert user_id == ""
        yield from io.connect(ipv4, port)
        yield from io.write_struct("BBH4s", 0, 0x5a, 0, b"\x00" * 4)
        yield from io.passthrough()

    rotor(SocksClient("127.0.0.1", 123, 4), server())


def test_client_socks4_success_by_host():

    def server():
        io = SansIORW(encoding="utf-8")
        version, command, port, ipv4 = yield from io.read_struct("BBH4s")
        assert version == 4
        assert command == 1
        assert port == 123
        assert ipv4 == b"\x00\x00\x00\xff"
        user_id = yield from io.read_c_string()
        assert user_id == ""
        host = yield from io.read_c_string()
        assert host == "python.org"
        yield from io.connect(host, port)
        yield from io.write_struct("BBH4s", 0, 0x5a, 0, b"\x00" * 4)
        yield from io.passthrough()

    rotor(SocksClient("python.org", 123, 4), server())


def test_server_socks4_auth_required():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write(b"\x04")
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(username="foo"))


def test_server_socks_bad_socks_version():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write(b"\x06")
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer())


def test_server_socks_bad_socks_version_but_allowed():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write(b"\x06")
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(allowed_versions={6}))


def test_server_socks4_unsupported_command():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("BBH4s", 4, 2, 123, b"\x7f\x00\x00\x01")
        yield from io.write_c_string("yoba")
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer())


def test_server_socks4_connect_failed():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("BBH4s", 4, 1, 123, b"\x7f\x00\x00\x01")
        yield from io.write_c_string("yoba")
        prefix, code, port, ipv4 = yield from io.read_struct("BBH4s")
        assert prefix == 0
        assert code == 0x5b
        assert port == 0
        assert ipv4 == b"\x00" * 4
        raise RuntimeError("connection failed")

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(), fail_connection=True)


def test_server_socks4_success_by_ipv4():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("BBH4s", 4, 1, 123, b"\x7f\x00\x00\x01")
        yield from io.write_c_string("yoba")
        prefix, code, port, ipv4 = yield from io.read_struct("BBH4s")
        assert prefix == 0
        assert code == 0x5a
        assert port == 0
        assert ipv4 == b"\x00" * 4
        yield from io.passthrough()

    rotor(client(), SocksServer())


def test_server_socks4_success_by_host():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("BBH4s", 4, 1, 123, b"\x00\x00\x00\x01")
        yield from io.write_c_string("yoba")
        yield from io.write_c_string("python.org")
        prefix, code, port, ipv4 = yield from io.read_struct("BBH4s")
        assert prefix == 0
        assert code == 0x5a
        assert port == 0
        assert ipv4 == b"\x00" * 4
        yield from io.passthrough()

    rotor(client(), SocksServer())


def test_client_socks5_request_auth_bad_version():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert version == 5
        assert one == 1
        assert auth_method == 0
        yield from io.write_struct("BB", 1, 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("abc", 666, 5), server())


def test_client_socks5_request_auth_not_accepted():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert version == 5
        assert one == 1
        assert auth_method == 0
        yield from io.write_struct("BB", 5, 1)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("abc", 666, 5), server())


def test_client_socks5_request_auth_username_bad_auth_version():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert version == 5
        assert one == 1
        assert auth_method == 2
        yield from io.write_struct("BB", 5, 2)
        auth_version = yield from io.read_struct("B")
        assert auth_version == 1
        username = yield from io.read_pascal_string()
        password = yield from io.read_pascal_string()
        assert username == "yoba"
        assert password == "foo"
        yield from io.write_struct("BB", 0, 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("abc", 666, 5, username="yoba", password="foo"), server())


def test_client_socks5_request_auth_username_failed():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert version == 5
        assert one == 1
        assert auth_method == 2
        yield from io.write_struct("BB", 5, 2)
        auth_version = yield from io.read_struct("B")
        assert auth_version == 1
        username = yield from io.read_pascal_string()
        password = yield from io.read_pascal_string()
        assert username == "yoba"
        assert password == "foo"
        yield from io.write_struct("BB", 1, 1)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("abc", 666, 5, username="yoba", password="foo"), server())


def test_client_socks5_command_bad_version():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert (version, one, auth_method) == (5, 1, 0)
        yield from io.write_struct("BB", 5, 0)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x7f\x00\x00\x01", 666)
        yield from io.write_struct("4B", 6, 0, 0, 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("127.0.0.1", 666, 5), server())


def test_client_socks5_command_request_not_granted():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert (version, one, auth_method) == (5, 1, 0)
        yield from io.write_struct("BB", 5, 0)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x7f\x00\x00\x01", 666)
        yield from io.write_struct("4B", 5, 1, 0, 1)
        yield from io.write(b"\x00" * 4)
        yield from io.write_struct("H", 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("127.0.0.1", 666, 5), server())


@pytest.mark.skip("this check removed")
def test_client_socks5_command_redirect_is_not_allowed():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert (version, one, auth_method) == (5, 1, 0)
        yield from io.write_struct("BB", 5, 0)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x7f\x00\x00\x01", 666)
        yield from io.write_struct("4B", 5, 0, 0, 1)
        yield from io.write(b"\x00" * 4)
        yield from io.write_struct("H", 1)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(SocksClient("127.0.0.1", 666, 5), server())


def test_client_socks5_success_ipv4():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert (version, one, auth_method) == (5, 1, 0)
        yield from io.write_struct("BB", 5, 0)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x7f\x00\x00\x01", 666)
        yield from io.write_struct("4B", 5, 0, 0, 1)
        yield from io.write(b"\x00" * 4)
        yield from io.write_struct("H", 0)
        yield from io.passthrough()

    rotor(SocksClient("127.0.0.1", 666, 5), server())


def test_client_socks5_success_ipv6():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert (version, one, auth_method) == (5, 1, 0)
        yield from io.write_struct("BB", 5, 0)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 4)
        ipv6, port = yield from io.read_struct("16sH")
        assert (ipv6, port) == ((b"\x00" * 15) + b"\x01", 666)
        yield from io.write_struct("4B", 5, 0, 0, 1)
        yield from io.write(b"\x00" * 4)
        yield from io.write_struct("H", 0)
        yield from io.passthrough()

    rotor(SocksClient("::1", 666, 5), server())


def test_client_socks5_success_domain():

    def server():
        io = SansIORW(encoding="utf-8")
        version, one, auth_method = yield from io.read_struct("BBB")
        assert (version, one, auth_method) == (5, 1, 0)
        yield from io.write_struct("BB", 5, 0)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 3)
        domain = yield from io.read_pascal_string()
        port = yield from io.read_struct("H")
        assert (domain, port) == ("python.org", 666)
        yield from io.write_struct("4B", 5, 0, 0, 1)
        yield from io.write(b"\x00" * 4)
        yield from io.write_struct("H", 0)
        yield from io.passthrough()

    rotor(SocksClient("python.org", 666, 5), server())


def test_server_socks5_no_auth_methods():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("B", 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer())


def test_server_socks5_bad_username_auth_version():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 2)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 2)
        yield from io.write_struct("B", 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(allowed_versions={5}, username="yoba", password="foo"))


def test_server_socks5_bad_username():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 2)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 2)
        yield from io.write_struct("B", 1)
        yield from io.write_pascal_string("yoba1")
        yield from io.write_pascal_string("foo")
        auth_version, retcode = yield from io.read_struct("BB")
        assert (auth_version, retcode) == (1, 1)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(allowed_versions={5}, username="yoba", password="foo"))


def test_server_socks5_bad_password():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 2)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 2)
        yield from io.write_struct("B", 1)
        yield from io.write_pascal_string("yoba")
        yield from io.write_pascal_string("foo1")
        auth_version, retcode = yield from io.read_struct("BB")
        assert (auth_version, retcode) == (1, 1)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(allowed_versions={5}, username="yoba", password="foo"))


def test_server_socks5_command_not_supported():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 0)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 0)
        yield from io.write_struct("4B", 5, 2, 0, 1)
        yield from io.write_struct("4sH", b"\x00" * 4, 666)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 7, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x00" * 4, 0)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer())


def test_server_socks5_address_type_not_supported():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 0)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 0)
        yield from io.write_struct("4B", 5, 2, 0, 13)
        yield from io.passthrough()

    with pytest.raises(SocksException):
        rotor(client(), SocksServer())


def test_server_socks5_connection_failed():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 0)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 0)
        yield from io.write_struct("4B", 5, 1, 0, 1)
        yield from io.write_struct("4sH", b"\x00" * 4, 666)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 1, 0, 1)
        raise RuntimeError("connection failed")

    with pytest.raises(SocksException):
        rotor(client(), SocksServer(), fail_connection=True)


def test_server_socks5_connection_ipv4_success():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 0)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 0)
        yield from io.write_struct("4B", 5, 1, 0, 1)
        yield from io.write_struct("4sH", b"\x00" * 4, 666)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 0, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x00" * 4, 0)
        yield from io.passthrough()

    rotor(client(), SocksServer())


def test_server_socks5_connection_ipv6_success():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 0)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 0)
        yield from io.write_struct("4B", 5, 1, 0, 4)
        yield from io.write_struct("16sH", b"\x00" * 16, 666)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 0, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x00" * 4, 0)
        yield from io.passthrough()

    rotor(client(), SocksServer())


def test_server_socks5_connection_domain_success():

    def client():
        io = SansIORW(encoding="utf-8")
        yield from io.write_struct("B", 5)
        yield from io.write_struct("BB", 1, 0)
        version, auth_method = yield from io.read_struct("BB")
        assert (version, auth_method) == (5, 0)
        yield from io.write_struct("4B", 5, 1, 0, 3)
        yield from io.write_pascal_string("python.org")
        yield from io.write_struct("H", 666)
        version, command, zero, address_type = yield from io.read_struct("4B")
        assert (version, command, zero, address_type) == (5, 0, 0, 1)
        ipv4, port = yield from io.read_struct("4sH")
        assert (ipv4, port) == (b"\x00" * 4, 0)
        yield from io.passthrough()

    rotor(client(), SocksServer())
