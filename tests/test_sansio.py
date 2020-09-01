import pytest

from siosocks.sansio import SansIORW
from siosocks.exceptions import SocksException


@pytest.fixture
def io():

    class IO:

        def __init__(self):
            self.buffer = []
            self.io = SansIORW(encoding="utf-8")

        def set(self, *data):
            self.buffer = list(data)
            return self

        def read(self):
            if not self.buffer:
                return b""
            return self.buffer.pop(0)

        def write(self, data):
            self.buffer.append(data)

        def __getattr__(self, name):

            def wrapper(*args, **kwargs):
                gen = getattr(self.io, name)(*args, **kwargs)
                method, data = gen.send, None
                while True:
                    try:
                        request = method(data)
                    except StopIteration as e:
                        return e.value
                    else:
                        data = getattr(self, request.pop("method"))(**request)

            return wrapper

    return IO()


def test_read_exactly(io):
    io.set(b"1", b"234")
    assert io.read_exactly(3) == b"123"
    assert io.read_exactly(1, put_back=True) == b"4"
    assert io.read_exactly(1) == b"4"
    with pytest.raises(SocksException):
        io.set(b"1").read_exactly(2)


def test_read_until(io):
    io.set(b"1", b"234", b"56")
    assert io.read_until(b"3", put_back=True) == b"12"
    assert io.read_until(b"3") == b"12"
    assert io.read_until(b"5", max_size=2) == b"34"
    with pytest.raises(SocksException):
        io.set(b"1", b"234", b"56").read_until(b"4", max_size=2)
    with pytest.raises(SocksException):
        io.set(b"123", b"456").read_until(b"4", max_size=2)
    with pytest.raises(SocksException):
        io.set(b"123").read_until(b"4")


def test_read_struct(io):
    io.set(b"\x01\x02\x03")
    assert io.read_struct("3B", put_back=True) == (1, 2, 3)
    assert io.read_struct("3B") == (1, 2, 3)
    assert io.set(b"\x01\x02").read_struct("B") == 1
    with pytest.raises(SocksException):
        io.set(b"\x01").read_struct("3B")


def test_read_c_string(io):
    io.set(b"foo", b"bar", b"\x00", b"tail")
    assert io.read_c_string() == "foobar"
    assert io.read_exactly(4) == b"tail"
    with pytest.raises(SocksException):
        io.set(b"foobar").read_c_string()


def test_read_pascal_string(io):
    assert io.set(b"\x06", b"foobar").read_pascal_string() == "foobar"
    with pytest.raises(SocksException):
        io.set(b"\x07", b"foobar").read_pascal_string()


def test_read_strings_without_encoding(io):
    io.io.encoding = None
    assert io.set(b"\x06", b"foobar").read_pascal_string() == b"foobar"
    assert io.set(b"foobar\x00").read_c_string() == b"foobar"


def test_write(io):
    io.write(b"123")
    assert io.buffer == [b"123"]


def test_write_struct(io):
    io.write_struct("3B", 1, 2, 3)
    assert io.buffer == [b"\x01\x02\x03"]


def test_write_c_string(io):
    io.write_c_string("foobar")
    assert io.buffer == [b"foobar", b"\x00"]


def test_write_pascal_string(io):
    io.write_pascal_string("foobar")
    assert io.buffer == [b"\x06", b"foobar"]
    with pytest.raises(SocksException):
        io.write_pascal_string("x" * 256)
