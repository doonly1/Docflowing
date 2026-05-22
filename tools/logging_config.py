import logging
import os
import sys
from contextvars import ContextVar

_request_id_var: ContextVar = ContextVar('request_id', default='-')

_log_initialized = False


def set_request_id(request_id: str):
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get('-')


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id_var.get('-')
        return True


def setup_logging(level=None):
    global _log_initialized
    if _log_initialized:
        return
    _log_initialized = True

    if level is None:
        level = os.environ.get('LOG_LEVEL', 'INFO')

    req_id = os.environ.get('REQUEST_ID')
    if req_id:
        _request_id_var.set(req_id)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.addFilter(RequestIDFilter())

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-7s] [%(request_id)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_logger(name):
    return logging.getLogger(name)
