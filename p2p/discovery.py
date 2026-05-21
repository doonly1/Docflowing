import socket
import threading
import json
import time

from logging_config import get_logger

logger = get_logger(__name__)

_DISCOVERY_PORT = 5330
_DISCOVERY_INTERVAL = 30


class NodeDiscovery:
    def __init__(self, node_id: str, display_name: str, port: int, public_key_b64: str = ''):
        self.node_id = node_id
        self.display_name = display_name
        self.port = port
        self.public_key = public_key_b64
        self._running = False
        self._thread: threading.Thread | None = None
        self._discovered: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="P2PDiscovery")
        self._thread.start()
        logger.info("P2P discovery started on port %d", _DISCOVERY_PORT)

    def stop(self):
        self._running = False

    def _run(self):
        self._broadcast()
        while self._running:
            self._broadcast()
            time.sleep(_DISCOVERY_INTERVAL)

    def _broadcast(self):
        try:
            msg = json.dumps({
                't': 'docproc-p2p',
                'v': 1,
                'id': self.node_id,
                'n': self.display_name,
                'p': self.port,
                'k': self.public_key
            }).encode('utf-8')

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(2)

            sock.bind(('0.0.0.0', 0))
            sock.setsockopt(socket.IPPROTO_IP, 2, 1)

            sock.sendto(msg, ('<broadcast>', _DISCOVERY_PORT))

            deadline = time.time() + 2
            while time.time() < deadline:
                try:
                    data, addr = sock.recvfrom(4096)
                    self._handle_message(data, addr)
                except socket.timeout:
                    break

            sock.close()
        except Exception as e:
            logger.debug("Discovery broadcast error: %s", e)

    def _handle_message(self, data: bytes, addr: tuple):
        try:
            msg = json.loads(data.decode('utf-8'))
            if msg.get('t') != 'docproc-p2p':
                return
            node_id = msg.get('id', '')
            if node_id == self.node_id:
                return
            display_name = msg.get('n', '')
            port = msg.get('p', 5000)
            pub_key = msg.get('k', '')
            host = addr[0]

            with self._lock:
                existing = self._discovered.get(node_id)
                if existing and existing['addr'] == f'{host}:{port}':
                    existing['last_seen'] = time.time()
                else:
                    self._discovered[node_id] = {
                        'node_id': node_id,
                        'display_name': display_name,
                        'public_key': pub_key,
                        'addr': f'{host}:{port}',
                        'host': host,
                        'port': port,
                        'first_seen': time.time(),
                        'last_seen': time.time()
                    }
                    logger.info("Discovered node: %s (%s) at %s:%d", display_name, node_id[:8], host, port)
        except Exception as e:
            logger.debug("Discovery message parse error: %s", e)

    def get_discovered_nodes(self) -> list[dict]:
        with self._lock:
            now = time.time()
            alive = {}
            for nid, info in self._discovered.items():
                if now - info['last_seen'] < 120:
                    alive[nid] = info
            return list(alive.values())