import abc

from siosocks.exceptions import SocksException


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


async def async_engine(protocol, io):
    generator_method, data = protocol.send, None
    while True:
        try:
            message = generator_method(data)
        except SocksException:
            raise
        except StopIteration:
            break
        method = message.pop("method")
        try:
            generator_method = protocol.send
            data = await getattr(io, method)(**message)
        except Exception as exc:
            generator_method, data = protocol.throw, exc


def sync_engine(protocol, io):
    generator_method, data = protocol.send, None
    while True:
        try:
            message = generator_method(data)
        except SocksException:
            raise
        except StopIteration:
            break
        method = message.pop("method")
        try:
            generator_method = protocol.send
            data = getattr(io, method)(**message)
        except Exception as exc:
            generator_method, data = protocol.throw, exc
