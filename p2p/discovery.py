import socket
import threading
import time

from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, Zeroconf
from logging_config import get_logger

logger = get_logger(__name__)

_SERVICE_TYPE = "_docflow-p2p._tcp.local."
_TTL = 120  # 节点存活时间（秒）


class NodeDiscovery:
    """基于 zeroconf mDNS 的 P2P 节点发现"""

    def __init__(self, node_id: str, display_name: str, port: int, public_key_b64: str = ''):
        self.node_id = node_id
        self.display_name = display_name
        self.port = port
        self.public_key = public_key_b64

        self._zeroconf: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._service_info: ServiceInfo | None = None

        self._discovered: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ─────────────────────────────────────────────
    # 公开 API
    # ─────────────────────────────────────────────

    def start(self):
        """启动 mDNS 注册与浏览"""
        if self._zeroconf is not None:
            return

        self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self._register()
        self._browse()
        logger.info("P2P discovery started (mDNS %s)", _SERVICE_TYPE)

    def stop(self):
        """停止并清理资源"""
        if self._browser:
            self._browser.cancel()
            self._browser = None

        if self._service_info and self._zeroconf:
            self._zeroconf.unregister_service(self._service_info)
            self._service_info = None

        if self._zeroconf:
            self._zeroconf.close()
            self._zeroconf = None

        logger.info("P2P discovery stopped")

    def get_discovered_nodes(self) -> list[dict]:
        """返回当前在线的节点列表"""
        with self._lock:
            now = time.time()
            alive = {}
            for nid, info in self._discovered.items():
                if now - info["last_seen"] < _TTL:
                    alive[nid] = info
            return list(alive.values())

    # ─────────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────────

    def _register(self):
        """注册本节点为 mDNS 服务"""
        addresses = self._get_local_ipv4()

        props = {
            "id": self.node_id,
            "n": self.display_name,
            "k": self.public_key,
            "v": "1",
        }

        self._service_info = ServiceInfo(
            type_=_SERVICE_TYPE,
            name=f"{self.node_id}._docflow-p2p._tcp.local.",
            addresses=[socket.inet_aton(addr) for addr in addresses],
            port=self.port,
            properties=props,
            server=f"{socket.gethostname()}.local.",
        )

        self._zeroconf.register_service(self._service_info)
        logger.info("mDNS service registered: %s → %s:%d", self.node_id[:8], addresses, self.port)

    def _browse(self):
        """开始浏览同类型服务"""
        self._browser = ServiceBrowser(self._zeroconf, _SERVICE_TYPE, self)

    def _get_local_ipv4(self) -> list[str]:
        """获取本机所有非回环 IPv4 地址"""
        ips: list[str] = []
        for family, _, _, _, sockaddr in socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET
        ):
            ip = sockaddr[0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)

        # 兜底：如果只拿到 127.0.0.1，至少能本地通信
        if not ips:
            ips = ["127.0.0.1"]
        return ips

    # ─────────────────────────────────────────────
    # zeroconf ServiceListener 回调
    # ─────────────────────────────────────────────

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """有新节点加入网络"""
        info = zc.get_service_info(type_, name)
        if info is None:
            return

        node_id = self._decode_prop(info, "id")
        if not node_id or node_id == self.node_id:
            return

        host = self._decode_address(info)
        port = info.port
        display_name = self._decode_prop(info, "n")
        public_key = self._decode_prop(info, "k")

        with self._lock:
            self._discovered[node_id] = {
                "node_id": node_id,
                "display_name": display_name,
                "public_key": public_key,
                "addr": f"{host}:{port}",
                "host": host,
                "port": port,
                "first_seen": time.time(),
                "last_seen": time.time(),
            }

        logger.info("Discovered node: %s (%s) at %s:%d", display_name, node_id[:8], host, port)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """节点离开网络"""
        node_id = name.split(".")[0] if "." in name else name
        with self._lock:
            self._discovered.pop(node_id, None)
        logger.info("Node removed: %s", node_id[:8])

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """节点信息更新（刷新 last_seen）"""
        node_id = name.split(".")[0] if "." in name else name
        with self._lock:
            if node_id in self._discovered:
                self._discovered[node_id]["last_seen"] = time.time()

    # ─────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────

    @staticmethod
    def _decode_prop(info, key: str) -> str:
        """从 ServiceInfo.properties 中解码字符串属性"""
        key_bytes = key.encode() if isinstance(key, str) else key
        raw = info.properties.get(key_bytes)
        if raw is None:
            return ""
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    @staticmethod
    def _decode_address(info) -> str:
        """从 ServiceInfo 中解码第一个 IPv4 地址"""
        addrs = info.addresses
        if addrs:
            return socket.inet_ntoa(addrs[0])
        return "127.0.0.1"
