import abc
import enum
import contextlib
from ipaddress import IPv4Address, IPv6Address

from .exceptions import SocksException
from .sansio import SansIORW


DEFAULT_ENCODING = "utf-8"


def _hex(i: int):
    return f"0x{i:0>2x}"


class SocksCommand(enum.IntEnum):
    tcp_connect = 0x01
    tcp_bind = 0x02
    udp_bind = 0x03


class AbstractSocks(abc.ABC):

    def __init__(self, io):
        self.io = io

    @property
    @abc.abstractmethod
    def version(self):
        """
        Curent instance socks version
        """

    def verify_version(self, version):
        if version != self.version:
            raise SocksException(f"Expect socks version {self.version}, but got {version}")

    @abc.abstractmethod
    def run(self):
        """
        Logic generator
        """


class Socks4Code(enum.IntEnum):
    success = 0x5a
    fail = 0x5b


class BaseSocks4(AbstractSocks):

    @property
    def version(self):
        return 4

    fmt = "BBH4s"
    this_network = IPv4Address("0.0.0.0")
    domain_flag_value_low = IPv4Address("0.0.0.1")
    domain_flag_value_high = IPv4Address("0.0.0.255")


class Socks4Server(BaseSocks4):

    def write_response(self, code):
        yield from self.io.write_struct(self.fmt, 0, code, 0, self.this_network.packed)

    def run(self):
        version, command, port, ipv4 = yield from self.io.read_struct(self.fmt)
        self.verify_version(version)
        user_id = yield from self.io.read_c_string()  # noqa
        if command != SocksCommand.tcp_connect:
            raise SocksException(f"Socks command {_hex(command)} is not supported")
        ipv4 = IPv4Address(ipv4)
        if self.domain_flag_value_low <= ipv4 <= self.domain_flag_value_high:
            host = yield from self.io.read_c_string()
        else:
            host = ipv4.compressed
        try:
            yield from self.io.connect(host, port)
        except Exception as exc:
            yield from self.write_response(Socks4Code.fail)
            raise SocksException from exc
        else:
            yield from self.write_response(Socks4Code.success)
            yield from self.io.passthrough()


class Socks4Client(BaseSocks4):

    def resolve_host(self, host):
        with contextlib.suppress(ValueError):
            return IPv4Address(host)
        return self.domain_flag_value_high

    def run(self, host, port, user_id=""):
        ipv4 = self.resolve_host(host)
        yield from self.io.write_struct(self.fmt, self.version, SocksCommand.tcp_connect, port, ipv4.packed)
        yield from self.io.write_c_string(user_id)
        if self.domain_flag_value_low <= ipv4 <= self.domain_flag_value_high:
            yield from self.io.write_c_string(host)
        _, code, *_ = yield from self.io.read_struct(self.fmt)
        if code != Socks4Code.success:
            raise SocksException(f"Code {_hex(code)} not equal to 'success' code {_hex(Socks4Code.success)}")
        yield from self.io.passthrough()


class Socks5AuthMethod(enum.IntEnum):
    no_auth = 0x00
    gssapi = 0x01
    username_password = 0x02
    no_acceptable = 0xff


class Socks5AddressType(enum.IntEnum):
    ipv4 = 0x01
    domain = 0x03
    ipv6 = 0x04


class Socks5Code(enum.IntEnum):
    request_granted = 0x00
    general_failure = 0x01
    connection_not_allowed_by_ruleset = 0x02
    network_unreachable = 0x03
    host_unreachable = 0x04
    connection_refused_by_destination_host = 0x05
    ttl_expired = 0x06
    command_not_supported_or_protocol_error = 0x07
    address_type_not_supported = 0x08


class BaseSocks5(AbstractSocks):

    @property
    def version(self):
        return 5

    @staticmethod
    def resolve_address(host):
        with contextlib.suppress(ValueError):
            return Socks5AddressType.ipv4, IPv4Address(host)
        with contextlib.suppress(ValueError):
            return Socks5AddressType.ipv6, IPv6Address(host)
        return Socks5AddressType.domain, host

    def read_command(self):
        version, command, _, address_type = yield from self.io.read_struct("4B")
        self.verify_version(version)
        if address_type == Socks5AddressType.ipv4:
            octets = yield from self.io.read_struct("4s")
            host = IPv4Address(octets).compressed
        elif address_type == Socks5AddressType.ipv6:
            octets = yield from self.io.read_struct("16s")
            host = IPv6Address(octets).compressed
        elif address_type == Socks5AddressType.domain:
            host = (yield from self.io.read_pascal_string())
        else:
            raise SocksException(f"Unknown address type {_hex(address_type)}")
        port = yield from self.io.read_struct("H")
        return command, host, port

    def write_command(self, command, host="0.0.0.0", port=0):
        address_type, address = self.resolve_address(host)
        yield from self.io.write_struct("4B", self.version, command, 0, address_type)
        if address_type == Socks5AddressType.ipv4:
            yield from self.io.write_struct("4s", address.packed)
        elif address_type == Socks5AddressType.ipv6:
            yield from self.io.write_struct("16s", address.packed)
        elif address_type == Socks5AddressType.domain:
            yield from self.io.write_pascal_string(address)
        yield from self.io.write_struct("H", port)


class Socks5Server(BaseSocks5):

    def auth(self, username, password):
        auth_methods_count = yield from self.io.read_struct("B")
        auth_methods = yield from self.io.read_exactly(auth_methods_count)
        auth_required = username is not None
        if auth_required:
            auth_method = Socks5AuthMethod.username_password
        else:
            auth_method = Socks5AuthMethod.no_auth
        if auth_method not in auth_methods:
            auth_method = Socks5AuthMethod.no_acceptable
        yield from self.io.write_struct("BB", self.version, auth_method)
        if auth_method == Socks5AuthMethod.no_acceptable:
            raise SocksException("No acceptible auth method")
        if auth_method == Socks5AuthMethod.username_password:
            auth_version = yield from self.io.read_struct("B")
            if auth_version != 1:
                raise SocksException(f"Username/password auth version {_hex(auth_version)} not supported")
            received_username = yield from self.io.read_pascal_string()
            received_password = yield from self.io.read_pascal_string()
            auth_successful = received_username == username and received_password == password
            auth_return_code = 0 if auth_successful else 1
            yield from self.io.write_struct("BB", auth_version, auth_return_code)
            if not auth_successful:
                raise SocksException("Wrong username or password")

    def run(self, username=None, password=None):
        version = yield from self.io.read_struct("B")
        self.verify_version(version)
        yield from self.auth(username, password)
        command, host, port = yield from self.read_command()
        if command != SocksCommand.tcp_connect:
            yield from self.write_command(Socks5Code.command_not_supported_or_protocol_error)
            raise SocksException(f"Socks command {_hex(command)} is not supported")
        try:
            yield from self.io.connect(host, port)
        except Exception as exc:
            yield from self.write_command(Socks5Code.general_failure)
            raise SocksException from exc
        else:
            yield from self.write_command(Socks5Code.request_granted)
            yield from self.io.passthrough()


class Socks5Client(BaseSocks5):

    def auth(self, username, password):
        auth_required = username is not None
        if auth_required:
            auth_method = Socks5AuthMethod.username_password
        else:
            auth_method = Socks5AuthMethod.no_auth
        yield from self.io.write_struct("BB", 1, auth_method)
        version, code = yield from self.io.read_struct("BB")
        self.verify_version(version)
        if code != auth_method:
            raise SocksException(f"Auth method {_hex(auth_method)} not accepted with {_hex(code)} code")
        if auth_method == Socks5AuthMethod.username_password:
            yield from self.io.write_struct("B", 1)
            yield from self.io.write_pascal_string(username)
            yield from self.io.write_pascal_string(password)
            auth_version, code = yield from self.io.read_struct("BB")
            if auth_version != 1:
                raise SocksException(f"Username/password auth version {_hex(auth_version)} not supported")
            if code != 0:
                raise SocksException(f"Username/password auth failed with code {_hex(code)}")

    def run(self, host, port, username=None, password=None):
        yield from self.io.write_struct("B", self.version)
        yield from self.auth(username, password)
        yield from self.write_command(SocksCommand.tcp_connect, host, port)
        code, *_ = yield from self.read_command()
        if code != Socks5Code.request_granted:
            raise SocksException(f"Code {_hex(code)} not equal to 'success' code {_hex(Socks5Code.request_granted)}")
        yield from self.io.passthrough()


def SocksServer(*, allowed_versions={4, 5}, username=None, password=None,
                strict_security_policy=True, encoding=DEFAULT_ENCODING):
    auth_required = username is not None
    if 4 in allowed_versions and auth_required and strict_security_policy:
        raise SocksException("Socks4 do not provide auth methods, "
                             "but socks4 allowed and auth provided and "
                             "strict security policy enabled")
    io = SansIORW(encoding)
    version = yield from io.read_struct("B", put_back=True)
    if version not in allowed_versions:
        raise SocksException(f"Version {version} is not in allowed {allowed_versions}")
    if version == 4:
        yield from Socks4Server(io).run()
    elif version == 5:
        yield from Socks5Server(io).run(username, password)
    else:
        raise SocksException(f"Version {version} is not supported")


def SocksClient(host, port, version, *, username=None, password=None, encoding=DEFAULT_ENCODING,
                socks4_extras={}, socks5_extras={}):
    auth_required = username is not None
    if version == 4 and auth_required:
        raise SocksException("Socks4 do not provide auth methods, but auth provided")
    io = SansIORW(encoding)
    if version == 4:
        yield from Socks4Client(io).run(host, port, **socks4_extras)
    elif version == 5:
        yield from Socks5Client(io).run(host, port, username, password, **socks5_extras)
    else:
        raise SocksException(f"Version {version} is not supported")
