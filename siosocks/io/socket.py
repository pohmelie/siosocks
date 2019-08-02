import socketserver
import socket
import logging
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION

from ..interface import AbstractSocksIO, sync_engine
from ..protocol import SocksServer
from .const import DEFAULT_BLOCK_SIZE


logger = logging.getLogger(__name__)


TIMEOUT = 0.5


class ServerIO(AbstractSocksIO):

    def __init__(self, socket):
        self.incoming_socket = socket
        self.incoming_socket.settimeout(TIMEOUT)
        self.outgoing_socket = None
        self._finished = False

    def read(self):
        return self.incoming_socket.recv(DEFAULT_BLOCK_SIZE)

    def write(self, data):
        self.incoming_socket.sendall(data)

    def connect(self, host, port):
        logger.debug("connect call %s:%d", host, port)
        self.outgoing_socket = socket.socket()
        self.outgoing_socket.connect((host, port))
        self.outgoing_socket.settimeout(TIMEOUT)

    def passthrough(self):
        logger.debug("passthrough started")
        tasks = [
            (self._sink, self.incoming_socket, self.outgoing_socket),
            (self._sink, self.outgoing_socket, self.incoming_socket),
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            fs = [executor.submit(*args) for args in tasks]
            wait(fs, return_when=FIRST_EXCEPTION)
            self._finished = True

    def _sink(self, producer, consumer):
        while True:
            try:
                data = producer.recv(DEFAULT_BLOCK_SIZE)
                if not data:
                    break
                consumer.sendall(data)
            except TimeoutError:
                if self._finished:
                    return


class socks_server_handler(socketserver.BaseRequestHandler):

    def __init__(self, *args, socks_protocol_kw, **kwargs):
        self._socks_protocol_kw = socks_protocol_kw
        super().__init__(*args, **kwargs)

    def handle(self):
        io = ServerIO(self.request)
        protocol = SocksServer(**self._socks_protocol_kw)
        sync_engine(protocol, io)
