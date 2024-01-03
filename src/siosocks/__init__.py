import importlib.metadata

__version__ = importlib.metadata.version(__package__)
version = tuple(map(int, __version__.split(".")))
