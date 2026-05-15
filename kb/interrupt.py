import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class InterruptRegistry:
    _instances: dict = {}
    _lock = threading.Lock()

    def __init__(self):
        self._events: dict = {}

    def register(self, session_id: str) -> threading.Event:
        event = threading.Event()
        with self._lock:
            self._events[session_id] = event
        return event

    def signal(self, session_id: str) -> bool:
        with self._lock:
            event = self._events.get(session_id)
            if event:
                event.set()
                return True
            return False

    def unregister(self, session_id: str):
        with self._lock:
            self._events.pop(session_id, None)

    def is_set(self, session_id: str) -> bool:
        with self._lock:
            event = self._events.get(session_id)
            if event:
                return event.is_set()
            return False

    @classmethod
    def get_instance(cls) -> "InterruptRegistry":
        tid = threading.get_ident()
        if tid not in cls._instances:
            cls._instances[tid] = InterruptRegistry()
        return cls._instances[tid]


class InterruptedError(Exception):
    pass