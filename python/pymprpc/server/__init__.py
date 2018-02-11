
import logging.config
from .log import LOGGING_CONFIG_DEFAULTS
from .server import BaseServer as SimpleMprpcServer
logging.config.dictConfig(LOGGING_CONFIG_DEFAULTS)


__all__ = ["SimpleMprpcServer"]
