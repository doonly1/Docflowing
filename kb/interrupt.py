import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class InterruptRegistry:
    _instance: Optional["InterruptRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._events: dict = {}
        self._events_lock = threading.Lock()

    def register(self, session_id: str) -> threading.Event:
        event = threading.Event()
        with self._events_lock:
            self._events[session_id] = event
        return event

    def signal(self, session_id: str) -> bool:
        with self._events_lock:
            event = self._events.get(session_id)
            if event:
                event.set()
                return True
            return False

    def unregister(self, session_id: str):
        with self._events_lock:
            self._events.pop(session_id, None)

    def is_set(self, session_id: str) -> bool:
        with self._events_lock:
            event = self._events.get(session_id)
            if event:
                return event.is_set()
            return False

    @classmethod
    def get_instance(cls) -> "InterruptRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = InterruptRegistry()
        return cls._instance


class InterruptedError(Exception):
    pass