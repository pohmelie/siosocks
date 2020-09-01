import struct

from .exceptions import SocksException


MAX_STRING_SIZE = 2 ** 10


class SansIORW:

    def __init__(self, encoding):
        self.buffer = b""
        self.encoding = encoding

    def _take_first(self, x, *, put_back=False):
        result = self.buffer[:x]
        if put_back:
            return result
        self.buffer = self.buffer[x:]
        return result

    def _read(self):
        data = yield dict(method="read")
        if not data:
            raise SocksException("Unexpected end of data")
        return data

    def read_exactly(self, count, *, put_back=False):
        while len(self.buffer) < count:
            self.buffer += yield from self._read()
        return self._take_first(count, put_back=put_back)

    def read_until(self, delimiter, *, max_size=None, put_back=False):
        while True:
            pos = self.buffer.find(delimiter)
            if max_size is not None and (pos == -1 and len(self.buffer) > max_size or pos > max_size):
                raise SocksException(f"Buffer became too long ({len(self.buffer)} > {max_size})")
            if pos != -1:
                return self._take_first(pos, put_back=put_back)
            self.buffer += yield from self._read()

    def read_struct(self, fmt, *, put_back=False):
        s = struct.Struct("!" + fmt)
        raw = yield from self.read_exactly(s.size, put_back=put_back)
        values = s.unpack(raw)
        if len(values) == 1:
            return values[0]
        return values

    def read_c_string(self, *, max_size=MAX_STRING_SIZE):
        b = yield from self.read_until(delimiter=b"\x00", max_size=max_size)
        yield from self.read_exactly(1)
        if self.encoding is None:
            return b
        return b.decode(self.encoding)

    def read_pascal_string(self):
        size = yield from self.read_struct("B")
        b = yield from self.read_exactly(size)
        if self.encoding is None:
            return b
        return b.decode(self.encoding)

    def write(self, data):
        yield dict(method="write", data=data)

    def write_struct(self, fmt, *values):
        s = struct.Struct("!" + fmt)
        yield from self.write(s.pack(*values))

    def write_c_string(self, s):
        b = s if self.encoding is None else s.encode(self.encoding)
        yield from self.write(b)
        yield from self.write(b"\x00")

    def write_pascal_string(self, s):
        b = s if self.encoding is None else s.encode(self.encoding)
        size = len(b)
        if size > 255:
            raise SocksException(f"Pascal string must be no longer than 255 characters, got {size}")
        yield from self.write_struct("B", size)
        yield from self.write(b)

    def connect(self, host, port):
        yield dict(method="connect", host=host, port=port)

    def passthrough(self):
        yield dict(method="passthrough")
