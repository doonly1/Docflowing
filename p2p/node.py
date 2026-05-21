import os
import time
import yaml
import base64
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
    load_der_private_key, load_der_public_key
)
from logging_config import get_logger

logger = get_logger(__name__)


def _get_config_dir():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, 'config')


def _get_config_path():
    return os.path.join(_get_config_dir(), 'p2p_node.yaml')


def _generate_keypair():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_der = private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    pub_der = public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

    priv_b64 = base64.b64encode(priv_der).decode()
    pub_b64 = base64.b64encode(pub_der).decode()

    return priv_b64, pub_b64


def _derive_node_id(pub_b64: str) -> str:
    return pub_b64[:16]


class NodeIdentity:
    def __init__(self):
        self.node_id: str = ''
        self.display_name: str = ''
        self._priv_key: Ed25519PrivateKey | None = None
        self._pub_key: Ed25519PublicKey | None = None
        self.port: int = 5000

    def load_or_create(self) -> 'NodeIdentity':
        config_path = _get_config_path()
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            self.display_name = cfg.get('display_name', '')
            self.port = cfg.get('port', 5000)
            priv_b64 = cfg.get('private_key', '')
            pub_b64 = cfg.get('public_key', '')
            if priv_b64 and pub_b64:
                priv_der = base64.b64decode(priv_b64)
                self._priv_key = load_der_private_key(priv_der, None)
                pub_der = base64.b64decode(pub_b64)
                self._pub_key = load_der_public_key(pub_der)
                self.node_id = _derive_node_id(pub_b64)
                logger.info("Loaded node identity: %s (%s)", self.node_id[:8], self.display_name)
                return self

        priv_b64, pub_b64 = _generate_keypair()
        self._priv_key = load_der_private_key(base64.b64decode(priv_b64), None)
        self._pub_key = load_der_public_key(base64.b64decode(pub_b64))
        self.node_id = _derive_node_id(pub_b64)

        if not self.display_name:
            import getpass
            self.display_name = getpass.getuser()

        cfg = {
            'display_name': self.display_name,
            'port': self.port,
            'private_key': priv_b64,
            'public_key': pub_b64,
            'created_at': time.time()
        }
        os.makedirs(_get_config_dir(), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, allow_unicode=True)

        logger.info("Created new node identity: %s (%s)", self.node_id[:8], self.display_name)
        return self

    def sign(self, data: bytes) -> str:
        sig = self._priv_key.sign(data)
        return base64.b64encode(sig).decode()

    def get_public_key_b64(self) -> str:
        pub_der = self._pub_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        return base64.b64encode(pub_der).decode()


def verify_signature(pub_key_b64: str, data: bytes, sig_b64: str) -> bool:
    try:
        pub_der = base64.b64decode(pub_key_b64)
        pub_key = load_der_public_key(pub_der)
        sig = base64.b64decode(sig_b64)
        pub_key.verify(sig, data)
        return True
    except Exception:
        return False