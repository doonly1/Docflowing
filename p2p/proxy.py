import hashlib
import json
import re
import requests

from logging_config import get_logger

logger = get_logger(__name__)

# 禁止访问的本地回环地址前缀
_LOOPBACK_PREFIXES = ('127.', '::1', '0.0.0.0', 'localhost')
_PRIVATE_PREFIXES = ('10.', '172.16.', '172.17.', '172.18.', '172.19.',
                     '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                     '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                     '172.30.', '172.31.', '192.168.')


def _validate_owner_addr(owner_addr: str) -> bool:
    """校验 owner_addr 是否安全，防止 SSRF。

    拒绝：
    - 格式不合法（非 ip:port）
    - 本地回环地址
    - 内网私有地址（纵深防御：外部信任节点不应指向内网）
    """
    if not owner_addr or ':' not in owner_addr:
        return False
    host = owner_addr.rsplit(':', 1)[0]
    # 格式校验：必须是 IPv4 点分格式
    if not re.fullmatch(r'\d{1,3}(?:\.\d{1,3}){3}', host):
        return False
    # 禁止回环地址
    if host.startswith(_LOOPBACK_PREFIXES):
        return False
    # 禁止内网私有地址
    if host.startswith(_PRIVATE_PREFIXES):
        return False
    return True


def _safe_request(method: str, url: str, owner_addr: str, **kwargs):
    """SSRF 安全的请求函数。在发起请求前校验 owner_addr。"""
    if not _validate_owner_addr(owner_addr):
        logger.warning("SSRF 拦截: 拒绝访问 owner_addr=%s", owner_addr)
        return None
    try:
        return requests.request(method, url, **kwargs)
    except Exception as e:
        logger.warning("P2P request failed (%s %s): %s", method, url, e)
        return None


def _sign_request(node_identity, method: str, path: str, body: bytes = b'') -> dict:
    """签名 P2P 请求，格式与 p2p/auth.py 的 p2p_auth_required 装饰器一致。

    签名覆盖 method:path:body_hash，body_hash 为 body 的 SHA256 十六进制，
    无 body 时（GET/DELETE/OPTIONS）为空字符串。
    """
    body_hash = hashlib.sha256(body).hexdigest() if body else ''
    sign_data = f'{method}:{path}:{body_hash}'.encode()
    sig = node_identity.sign(sign_data)
    return {
        'X-Node-ID': node_identity.node_id,
        'X-Node-Sig': sig,
    }


def remote_list_files(owner_addr: str, node_identity, fb_id: str, subdir: str = '') -> dict | None:
    path = f'/p2p/fb/{fb_id}/list-files'
    params = {'subdir': subdir} if subdir else {}
    headers = _sign_request(node_identity, 'GET', path)
    try:
        resp = _safe_request('GET', f'http://{owner_addr}{path}', owner_addr, params=params, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_list_files failed: %s", e)
        return None


def remote_get_file_content(owner_addr: str, node_identity, fb_id: str, path: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/file-content'
    headers = _sign_request(node_identity, 'GET', api_path)
    try:
        resp = _safe_request('GET', f'http://{owner_addr}{api_path}', owner_addr, params={'path': path}, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_get_file_content failed: %s", e)
        return None


def remote_download_file(owner_addr: str, node_identity, fb_id: str, path: str):
    api_path = f'/p2p/fb/{fb_id}/download'
    headers = _sign_request(node_identity, 'GET', api_path)
    try:
        resp = _safe_request('GET', f'http://{owner_addr}{api_path}', owner_addr, params={'path': path}, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning("remote_download_file failed: %s", e)
        return None


def remote_upload_file(owner_addr: str, node_identity, fb_id: str, subdir: str, filename: str, file_stream, file_size: int) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/upload'
    # 大文件上传：签名只覆盖 method:path:（文件内容不哈希，避免内存开销）
    # 服务端依然做签名 + 节点身份校验，但文件完整性由 TLS（未来）或应用层保证
    headers = _sign_request(node_identity, 'POST', api_path)
    params = {'subdir': subdir} if subdir else {}
    try:
        resp = _safe_request(
            'POST', f'http://{owner_addr}{api_path}', owner_addr,
            params=params,
            headers=headers,
            files={'file': (filename, file_stream, 'application/octet-stream')},
            timeout=300
        )
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_upload_file failed: %s", e)
        return None


def remote_save_file(owner_addr: str, node_identity, fb_id: str, path: str, content: str, client_mtime: float) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/save-file'
    body = json.dumps({'path': path, 'content': content, 'client_mtime': client_mtime}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=60)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_save_file failed: %s", e)
        return None


def remote_delete_items(owner_addr: str, node_identity, fb_id: str, paths: list) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/delete-items'
    body = json.dumps({'paths': paths}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=60)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_delete_items failed: %s", e)
        return None


def remote_rename_item(owner_addr: str, node_identity, fb_id: str, path: str, new_name: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/rename-item'
    body = json.dumps({'path': path, 'new_name': new_name}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=60)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_rename_item failed: %s", e)
        return None


def remote_move_items(owner_addr: str, node_identity, fb_id: str, sources: list, dest: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/move-items'
    body = json.dumps({'sources': sources, 'dest': dest}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=60)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_move_items failed: %s", e)
        return None


def remote_copy_items(owner_addr: str, node_identity, fb_id: str, sources: list, dest: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/copy-items'
    body = json.dumps({'sources': sources, 'dest': dest}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=60)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_copy_items failed: %s", e)
        return None


def remote_create_file(owner_addr: str, node_identity, fb_id: str, name: str, parent: str = '') -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/create-file'
    body = json.dumps({'name': name, 'parent': parent}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_create_file failed: %s", e)
        return None


def remote_create_dir(owner_addr: str, node_identity, fb_id: str, name: str, parent: str = '') -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/create-dir'
    body = json.dumps({'name': name, 'parent': parent}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_create_dir failed: %s", e)
        return None


def remote_get_metadata(owner_addr: str, node_identity, fb_id: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/metadata'
    headers = _sign_request(node_identity, 'GET', api_path)
    try:
        resp = _safe_request('GET', f'http://{owner_addr}{api_path}', owner_addr, headers=headers, timeout=10)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_get_metadata failed: %s", e)
        return None


def remote_search_kb(owner_addr: str, node_identity, fb_ids: list, query: str) -> dict | None:
    api_path = '/p2p/kb/search'
    body = json.dumps({'fb_ids': fb_ids, 'q': query}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request('POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers, timeout=15)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_search_kb failed: %s", e)
        return None


def remote_run_tool(owner_addr: str, node_identity, fb_id: str, tool: str, files: list, subdir: str = ''):
    api_path = f'/p2p/fb/{fb_id}/run-tool'
    body = json.dumps({'tool': tool, 'files': files, 'subdir': subdir}).encode()
    headers = _sign_request(node_identity, 'POST', api_path, body)
    headers['Content-Type'] = 'application/json'
    try:
        resp = _safe_request(
            'POST', f'http://{owner_addr}{api_path}', owner_addr, data=body, headers=headers,
            stream=True, timeout=600
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning("remote_run_tool failed: %s", e)
        return None


def remote_replace_file(owner_addr: str, node_identity, fb_id: str, path: str, file_stream) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/replace-file'
    # 与 remote_upload_file 同理，签名只覆盖 method:path:
    headers = _sign_request(node_identity, 'POST', api_path)
    try:
        resp = _safe_request(
            'POST', f'http://{owner_addr}{api_path}', owner_addr,
            params={'path': path},
            headers=headers,
            files={'file': (path.split('/')[-1], file_stream, 'application/octet-stream')},
            timeout=300
        )
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_replace_file failed: %s", e)
        return None