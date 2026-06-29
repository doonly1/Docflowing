import os
import time
import yaml
import base64
import hmac
import hashlib
import secrets
from pathlib import Path
from logging_config import get_logger

logger = get_logger(__name__)


def _get_config_dir():
    from server.workspace import _get_workspace_dir
    return os.path.join(_get_workspace_dir(), 'config')


def _get_config_path():
    return os.path.join(_get_config_dir(), 'p2p_node.yaml')


def _get_device_fingerprint() -> str:
    """获取稳定的设备指纹，用于确定性 node_id 生成。

    组合多个硬件/系统特征，确保同一台设备返回相同指纹：
    - Windows MachineGuid（注册表，OS 重装后变）
    - 主网卡 MAC 地址（换硬件后变）
    - 主机名
    """
    import platform
    import uuid

    parts = []

    # Windows 机器唯一 ID（注册表）
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Cryptography'
        ) as key:
            guid, _ = winreg.QueryValueEx(key, 'MachineGuid')
            parts.append(f'guid={guid}')
    except Exception:
        pass

    # 主网卡 MAC 地址（uuid.getnode() 返回稳定值）
    try:
        mac_raw = uuid.getnode()
        mac = ':'.join(f'{(mac_raw >> i) & 0xff:02x}'
                       for i in range(0, 48, 8))
        parts.append(f'mac={mac}')
    except Exception:
        pass

    # 主机名
    try:
        parts.append(f'host={platform.node()}')
    except Exception:
        pass

    fingerprint = '|'.join(parts) if parts else platform.node() or 'unknown'
    return fingerprint


def _generate_secret():
    """生成 32 字节 HMAC 密钥。

    从设备指纹派生（确定性），确保同一设备每次生成的 node_id 相同。
    如果 p2p_node.yaml 已存在则直接读取，不走此路径。
    """
    fingerprint = _get_device_fingerprint()
    seed = hashlib.sha256(fingerprint.encode()).digest()
    app_salt = b'docflowing-node-v1'
    material = hashlib.sha256(seed + app_salt).digest()
    secret = material[:32]
    return base64.b64encode(secret).decode()


def _derive_node_id(secret_b64: str) -> str:
    """节点 ID = HMAC-SHA256 密钥的前 16 位 base64"""
    return secret_b64[:16]


class NodeIdentity:
    def __init__(self):
        self.node_id: str = ''
        self.display_name: str = ''
        self._secret: bytes | None = None
        self.port: int = 5000

    def load_or_create(self) -> 'NodeIdentity':
        config_path = _get_config_path()
        old_pub_backup = ''
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            self.display_name = cfg.get('display_name', '')
            self.port = cfg.get('port', 5000)
            self.node_id = cfg.get('node_id', '')  # 优先读取显式存储的 node_id
            secret_b64 = cfg.get('private_key', '') or cfg.get('secret_key', '')
            if secret_b64:
                decoded = base64.b64decode(secret_b64)
                if len(decoded) == 32:
                    # 新格式 HMAC 密钥（32 字节）
                    self._secret = decoded
                    if not self.node_id:
                        # 尝试从 legacy 字段恢复 node_id
                        legacy = cfg.get('legacy_public_key', '')
                        self.node_id = legacy[:16] if legacy else _derive_node_id(secret_b64)
                    logger.info("Loaded node identity: %s (%s)", self.node_id[:8], self.display_name)
                    return self
                # 旧格式 Ed25519 密钥（DER > 32 字节），自动迁移
                logger.info("Migrating from Ed25519 key to HMAC (node_id preserved)")
                old_pub_backup = cfg.get('public_key', '')
                if not self.node_id and old_pub_backup:
                    self.node_id = old_pub_backup[:16]

        secret_b64 = _generate_secret()
        self._secret = base64.b64decode(secret_b64)
        if not self.node_id:
            self.node_id = _derive_node_id(secret_b64)

        if not self.display_name:
            import getpass
            self.display_name = getpass.getuser()

        cfg = {
            'display_name': self.display_name,
            'port': self.port,
            'node_id': self.node_id,
            'private_key': secret_b64,
            'public_key': secret_b64,
            'legacy_public_key': old_pub_backup,  # 保留旧公钥用于 node_id 恢复
            'secret_key': secret_b64,
            'created_at': time.time()
        }
        os.makedirs(_get_config_dir(), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, allow_unicode=True)

        logger.info("Created new node identity: %s (%s)", self.node_id[:8], self.display_name)
        return self

    def sign(self, data: bytes) -> str:
        sig = hmac.digest(self._secret, data, hashlib.sha256)
        return base64.b64encode(sig).decode()

    def get_public_key_b64(self) -> str:
        """返回 HMAC 密钥的 base64（兼容旧接口名称）"""
        return base64.b64encode(self._secret).decode()

    def _get_secret_b64(self) -> str:
        return base64.b64encode(self._secret).decode()

    def save_config(self) -> bool:
        """持久化当前配置到 p2p_node.yaml"""
        try:
            config_path = _get_config_path()
            secret_b64 = self._get_secret_b64()
            cfg = {
                'display_name': self.display_name,
                'port': self.port,
                'node_id': self.node_id,
                'private_key': secret_b64,
                'public_key': secret_b64,
                'secret_key': secret_b64,
                'updated_at': time.time()
            }
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True)
            logger.info("Saved node config: %s port=%d", self.display_name, self.port)
            return True
        except Exception as e:
            logger.warning("Failed to save node config: %s", e)
            return False


def verify_signature(secret_b64: str, data: bytes, sig_b64: str) -> bool:
    """HMAC-SHA256 签名验证（替代 Ed25519 verify）"""
    try:
        secret = base64.b64decode(secret_b64)
        sig = base64.b64decode(sig_b64)
        expected = hmac.digest(secret, data, hashlib.sha256)
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False