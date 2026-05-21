import json
import requests

from logging_config import get_logger

logger = get_logger(__name__)


def _sign_request(node_identity, method: str, path: str, body: bytes = b'') -> dict:
    sign_data = f'{method}:{path}:'.encode() + body
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
        resp = requests.get(f'http://{owner_addr}{path}', params=params, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_list_files failed: %s", e)
        return None


def remote_get_file_content(owner_addr: str, node_identity, fb_id: str, path: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/file-content'
    headers = _sign_request(node_identity, 'GET', api_path)
    try:
        resp = requests.get(f'http://{owner_addr}{api_path}', params={'path': path}, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_get_file_content failed: %s", e)
        return None


def remote_download_file(owner_addr: str, node_identity, fb_id: str, path: str):
    api_path = f'/p2p/fb/{fb_id}/download'
    headers = _sign_request(node_identity, 'GET', api_path)
    try:
        resp = requests.get(f'http://{owner_addr}{api_path}', params={'path': path}, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning("remote_download_file failed: %s", e)
        return None


def remote_upload_file(owner_addr: str, node_identity, fb_id: str, subdir: str, filename: str, file_stream, file_size: int) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/upload'
    sign_data = f'POST:{api_path}:'.encode()
    sig = node_identity.sign(sign_data)
    headers = {
        'X-Node-ID': node_identity.node_id,
        'X-Node-Sig': sig,
    }
    params = {'subdir': subdir} if subdir else {}
    try:
        resp = requests.post(
            f'http://{owner_addr}{api_path}',
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=60)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=60)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=60)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=60)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=60)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=30)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=30)
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_create_dir failed: %s", e)
        return None


def remote_get_metadata(owner_addr: str, node_identity, fb_id: str) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/metadata'
    headers = _sign_request(node_identity, 'GET', api_path)
    try:
        resp = requests.get(f'http://{owner_addr}{api_path}', headers=headers, timeout=10)
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
        resp = requests.post(f'http://{owner_addr}{api_path}', data=body, headers=headers, timeout=15)
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
        resp = requests.post(
            f'http://{owner_addr}{api_path}', data=body, headers=headers,
            stream=True, timeout=600
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning("remote_run_tool failed: %s", e)
        return None


def remote_replace_file(owner_addr: str, node_identity, fb_id: str, path: str, file_stream) -> dict | None:
    api_path = f'/p2p/fb/{fb_id}/replace-file'
    sign_data = f'POST:{api_path}:'.encode()
    sig = node_identity.sign(sign_data)
    headers = {
        'X-Node-ID': node_identity.node_id,
        'X-Node-Sig': sig,
    }
    try:
        resp = requests.post(
            f'http://{owner_addr}{api_path}',
            params={'path': path},
            headers=headers,
            files={'file': (path.split('/')[-1], file_stream, 'application/octet-stream')},
            timeout=300
        )
        return resp.json() if resp.ok else None
    except Exception as e:
        logger.warning("remote_replace_file failed: %s", e)
        return None