import logging
import os
import time
import threading

logger = logging.getLogger(__name__)


class CrossPlatformFileLock:
    def __init__(self, lock_path: str, timeout: float = 5.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd = None
        self._acquired = False

    def acquire(self) -> bool:
        deadline = time.monotonic() + self.timeout
        lock_dir = os.path.dirname(self.lock_path)
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)

        while time.monotonic() < deadline:
            try:
                if os.name == 'nt':
                    fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    self._fd = fd
                    self._acquired = True
                    return True
                else:
                    import fcntl
                    fd = os.open(self.lock_path, os.O_CREAT | os.O_WRONLY)
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self._fd = fd
                        self._acquired = True
                        return True
                    except (IOError, OSError):
                        os.close(fd)
                        time.sleep(0.05)
                        continue
            except FileExistsError:
                try:
                    stat = os.stat(self.lock_path)
                    age = time.time() - stat.st_mtime
                    if age > 300:
                        try:
                            os.unlink(self.lock_path)
                        except OSError:
                            pass
                except OSError:
                    pass
                time.sleep(0.05)
                continue
            except OSError:
                time.sleep(0.05)
                continue

        return False

    def release(self):
        if not self._acquired:
            return
        try:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
        except OSError:
            pass
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass
        self._acquired = False

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock: {self.lock_path}")
        return self

    def __exit__(self, *args):
        self.release()


_lock_registry = {}
_lock_registry_lock = threading.Lock()


def get_lock(name: str, timeout: float = 5.0) -> CrossPlatformFileLock:
    import tempfile
    lock_dir = os.path.join(tempfile.gettempdir(), "docflow_locks")
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, f"{name}.lock")
    return CrossPlatformFileLock(lock_path, timeout=timeout)
