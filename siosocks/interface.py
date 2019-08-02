import abc
import contextlib


class AbstractSocksIO(abc.ABC):

    @abc.abstractmethod
    def read(self):
        """
        Socket read method
        """

    @abc.abstractmethod
    def write(self, data):
        """
        Socket write method
        """

    @abc.abstractmethod
    def connect(self, host, port):
        """
        Open connection
        """

    @abc.abstractmethod
    def passthrough(self):
        """
        Transfer data between sockets
        """


def _common_engine(protocol, io):
    generator_method, data = protocol.send, None
    while True:
        try:
            message = generator_method(data)
        except StopIteration:
            break
        method = message.pop("method")
        try:
            generator_method = protocol.send
            data = yield getattr(io, method)(**message)
        except Exception as e:
            generator_method, data = protocol.throw, e


async def async_engine(protocol, io):
    engine = _common_engine(protocol, io)
    data = None
    with contextlib.suppress(StopIteration):
        while True:
            data = await engine.send(data)


def sync_engine(protocol, io):
    engine = _common_engine(protocol, io)
    data = None
    with contextlib.suppress(StopIteration):
        while True:
            data = engine.send(data)
