"""定义mprpc服务器端的log对象和基本log设置

+ File: log.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-01-23 version-0.5 by hsz
"""
import sys
import logging


LOGGING_CONFIG_DEFAULTS = dict(
    version=1,
    disable_existing_loggers=False,

    loggers={
        "root": {
            "level": "INFO",
            "handlers": ["console"]
        },
        "pymprpc.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": True,
            "qualname": "pymprpc.error"
        },

        "pymprpc.access": {
            "level": "INFO",
            "handlers": ["access_console"],
            "propagate": True,
            "qualname": "pymprpc.access"
        }
    },
    handlers={
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": sys.stdout
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": sys.stderr
        },
        "access_console": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": sys.stdout
        },
    },
    formatters={
        "generic": {
            "format": (
                "[LOG]-%(asctime)s-[%(levelname)s]-[%(process)d]: %(message)s"
            ),
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter"
        },
        "access": {
            "format": (
                "[ACC]-%(asctime)s-[%(levelname)s]-%(client)s: %(message)s"
            ),
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter"
        },
    }
)


logger = logging.getLogger('root')
error_logger = logging.getLogger('pymprpc.error')
access_logger = logging.getLogger('pymprpc.access')
