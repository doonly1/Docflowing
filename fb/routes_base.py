"""文件库基础 CRUD 功能"""

import os
import uuid
import time
import shutil
from flask import Blueprint, request, jsonify, g

from server.auth import login_required
from fb.database import get_db, get_visible_fb_ids
from fb.decorators import _require_fb_permission, require_fb_perm, _is_admin

fb_bp = Blueprint('fb', __name__, url_prefix='/api/fb')


def _get_user_workspace(user_id=None):
    """获取用户工作空间目录"""
    try:
        import platform
        system = platform.system()
        desktop = None

        if system == 'Windows':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
            desktop, _ = winreg.QueryValueEx(key, 'Desktop')
            winreg.CloseKey(key)
            desktop = os.path.expandvars(desktop)
        else:
            desktop = os.environ.get('XDG_DESKTOP_DIR')
            if not desktop:
                user_dirs = os.path.join(os.path.expanduser('~'), '.config', 'user-dirs.dirs')
                if os.path.exists(user_dirs):
                    with open(user_dirs, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip().startswith('XDG_DESKTOP_DIR'):
                                desktop = line.split('=', 1)[1].strip().strip('"')
                                desktop = os.path.expandvars(desktop)
                                break
                if not desktop:
                    home = os.path.expanduser('~')
                    for name in ('Desktop', '桌面'):
                        candidate = os.path.join(home, name)
                        if os.path.isdir(candidate):
                            desktop = candidate
                            break

        if desktop and os.path.isdir(desktop):
            return desktop
    except Exception:
        pass

    return os.path.expanduser('~')


@fb_bp.route('/create-folder', methods=['POST'])
@login_required
def create_folder():
    """创建文件库"""
    user_id = g.user_id
    data = request.get_json()
    filebase_type = (data.get('filebase_type') or 'local').strip()
    name = (data.get('name') or '').strip()
    local_path = (data.get('local_path') or '').strip()

    if filebase_type == 'net':
        network_path = (data.get('network_path') or data.get('local_path') or '').strip()
        if not network_path:
            return jsonify({'success': False, 'message': '网络路径不能为空'})

        if not name:
            return jsonify({'success': False, 'message': '网络文件库名称不能为空'})

        db = get_db()
        filebase_id = str(uuid.uuid4())
        now = time.time()
        db.execute(
            "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at, is_synced_to_kb) VALUES (?, ?, ?, 'net', ?, ?, 0)",
            (filebase_id, name, user_id, network_path, now)
        )
        db.execute(
            "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
            (filebase_id, user_id, 'manage')
        )
        db.commit()
        _invalidate_list_cache(user_id)

        return jsonify({
            'success': True,
            'fb': {'id': filebase_id, 'name': name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'net',
                   'local_path': network_path}
        })

    # local 本地文件库：仅支持「添加本地已有文件夹」。
    # 无固定工作空间，应用不再代用户在某个默认目录里新建文件夹。
    if not local_path:
        return jsonify({'success': False, 'message': '请选择要添加的本地文件夹路径'})
    if not os.path.isdir(local_path):
        return jsonify({'success': False, 'message': '目录不存在或无效'})
    folder_name = os.path.basename(local_path.rstrip('/\\'))
    if not folder_name:
        return jsonify({'success': False, 'message': '无效的目录路径'})

    db = get_db()
    filebase_id = str(uuid.uuid4())
    now = time.time()

    existing = db.execute(
        "SELECT id FROM filebases WHERE owner_id = ? AND local_path = ?",
        (user_id, local_path)
    ).fetchone()
    if existing:
        return jsonify({'success': False, 'message': '该目录已在文件库中'})

    db.execute(
        "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at, is_synced_to_kb) VALUES (?, ?, ?, 'local', ?, ?, 0)",
        (filebase_id, folder_name, user_id, local_path, now)
    )
    db.execute(
        "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
        (filebase_id, user_id, 'manage')
    )
    db.commit()
    _invalidate_list_cache(user_id)

    return jsonify({
        'success': True,
        'fb': {'id': filebase_id, 'name': folder_name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'local',
               'local_path': local_path}
    })


@fb_bp.route('/copy-folder', methods=['POST'])
@login_required
def copy_folder():
    """复制文件库"""
    user_id = g.user_id
    data = request.get_json()
    filebase_id = (data.get('fb_id') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not filebase_id or not new_name:
        return jsonify({'success': False, 'message': '参数不完整'})

    db = get_db()
    kb_row = db.execute("SELECT * FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '源文件库不存在'})

    src_path = kb_row['local_path']
    if not os.path.isdir(src_path):
        return jsonify({'success': False, 'message': '源目录不存在'})

    # 复制到源目录的同级位置（无固定工作空间，不猜测存放目录）
    dst_base = os.path.dirname(src_path)
    dst_path = os.path.join(dst_base, new_name)

    counter = 1
    orig_name = new_name
    while os.path.exists(dst_path) and counter < 100:
        new_name = orig_name + '_' + str(counter)
        dst_path = os.path.join(dst_base, new_name)
        counter += 1
    if os.path.exists(dst_path):
        return jsonify({'success': False, 'message': '无法生成唯一的名称'})

    try:
        shutil.copytree(src_path, dst_path)
    except Exception as e:
        return jsonify({'success': False, 'message': '复制目录失败: ' + str(e)})

    new_filebase_id = str(uuid.uuid4())
    now = time.time()
    db.execute(
        "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at, is_synced_to_kb) VALUES (?, ?, ?, 'local', ?, ?, 0)",
        (new_filebase_id, new_name, user_id, dst_path, now)
    )
    db.execute(
        "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, ?)",
        (new_filebase_id, user_id, 'manage')
    )
    db.commit()
    _invalidate_list_cache(user_id)

    return jsonify({
        'success': True,
        'fb': {'id': new_filebase_id, 'name': new_name, 'owner_id': user_id, 'created_at': now, 'filebase_type': 'local', 'local_path': dst_path}
    })


_list_fb_cache = {}          # cache_key -> data
_list_fb_cache_time = {}     # cache_key -> timestamp
_LIST_FB_CACHE_TTL = 5


@fb_bp.route('/list', methods=['GET'])
@login_required
def list_fb():
    """获取文件库列表"""
    user_id = g.user_id

    cache_key = f"list_fb:{user_id}"
    now = time.time()
    if cache_key in _list_fb_cache and now - _list_fb_cache_time.get(cache_key, 0) < _LIST_FB_CACHE_TTL:
        return jsonify(_list_fb_cache[cache_key])

    is_admin = _is_admin(user_id)
    db = get_db()

    # 首次使用引导：无任何本地文件库时在运行时目录下创建「示例文件库」（幂等）。
    # 注意：不再自动扫描/注册任何工作空间目录，文件库一律显式创建或添加。
    _ensure_sample_filebase(user_id)

    if is_admin:
        visible_rows = db.execute("SELECT * FROM filebases WHERE COALESCE(status, 'active') != 'trashed'").fetchall()
    else:
        visible_ids = get_visible_fb_ids(user_id, False)
        visible_rows = []
        for filebase_id in visible_ids:
            r = db.execute("SELECT * FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
            if r:
                visible_rows.append(r)

    # 批量查询所有本地文件库的文件数（避免 N+1 SQL + 全量 JSON 解析）
    fb_file_counts = {}
    local_fb_ids = [(row['id'], row['owner_id']) for row in visible_rows if row['filebase_type'] not in ('net', 'remote')]
    if local_fb_ids:
        try:
            conditions = []
            params = []
            for fb_id, owner_id in local_fb_ids:
                conditions.append('(filebase_id = ? AND user_id = ?)')
                params.extend([fb_id, owner_id])
            batch_sql = f"""SELECT filebase_id, json_extract(state_json, '$.total_files') AS total_files
                FROM filebase_sync_states
                WHERE {' OR '.join(conditions)}"""
            for r in db.execute(batch_sql, params).fetchall():
                fb_file_counts[r['filebase_id']] = r['total_files'] or 0
        except Exception:
            import logging
            logging.getLogger(__name__).warning('批量查询文件数失败，使用逐个回退')

    kbs = []
    for row in visible_rows:
        perm_row = db.execute(
            "SELECT permission_level FROM filebase_permissions WHERE filebase_id = ? AND user_id = ?",
            (row['id'], user_id)
        ).fetchone()
        permission = 'manage' if row['owner_id'] == user_id or is_admin else (
            perm_row['permission_level'] if perm_row else 'view'
        )

        owner_username = (row['owner_id'] or '')[:8]

        local_path = row['local_path']
        display_path = local_path
        if local_path:
            norm = os.path.normpath(local_path)
            parts = norm.split(os.sep)
            try:
                ws_idx = [p.lower() for p in parts].index('docflowing')
                if ws_idx + 2 < len(parts):
                    parts[ws_idx + 1] = owner_username
                path_parts = parts[ws_idx + 1:]
                display_path = '/'.join(path_parts)
            except ValueError:
                pass

        kbs.append({
            'id': row['id'],
            'name': row['name'],
            'owner_id': row['owner_id'],
            'owner_username': owner_username,
            'display_path': display_path,
            'created_at': row['created_at'],
            'permission': permission,
            'filebase_type': row['filebase_type'] or 'local',
            'local_path': local_path,
            'total_files': fb_file_counts.get(row['id'], _get_fb_file_count(row['id'], row['owner_id']))
        })

    from p2p.models import RemoteFilebaseStore, TrustStore
    remote_store = RemoteFilebaseStore()
    trust_store = TrustStore()
    for fb_id, fb_info in remote_store.get_all().items():
        owner_node = trust_store.get_node_info(fb_info['owner_node_id'])
        owner_name = owner_node['display_name'] if owner_node else fb_info['owner_node_id'][:8]
        kbs.append({
            'id': fb_id,
            'name': f'[远程] {owner_name}/{fb_info["name"]}',
            'owner_id': fb_info['owner_node_id'],
            'owner_username': owner_name,
            'display_path': f'远程节点: {fb_info["owner_addr"]}',
            'created_at': fb_info.get('created_at', 0),
            'permission': fb_info['permission'],
            'filebase_type': 'remote',
            'local_path': ''
        })

    result = {'success': True, 'kbs': kbs}
    _list_fb_cache[cache_key] = result
    _list_fb_cache_time[cache_key] = now
    return jsonify(result)


def _get_fb_file_count(filebase_id: str, owner_id: str) -> int:
    """获取文件库的文件总数，优先使用同步缓存，回退到数据库持久化状态，最后直接扫描磁盘"""
    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        stats = worker.get_filebase_stats(filebase_id)
        if stats:
            return stats['total_files']
    except Exception:
        import logging
        logging.getLogger(__name__).debug('worker stats unavailable, falling back to sync_state', exc_info=True)
    try:
        from kb.sync_state import get_sync_state_manager
        state_manager = get_sync_state_manager()
        state = state_manager.load_state(owner_id, filebase_id)
        if state.total_files > 0:
            return state.total_files
    except Exception:
        import logging
        logging.getLogger(__name__).debug('sync_state unavailable, falling back to disk scan', exc_info=True)
    # 最后兜底：直接扫描磁盘
    return _count_files_on_disk(filebase_id, owner_id)


def _count_files_on_disk(filebase_id: str, owner_id: str) -> int:
    """直接扫描文件库目录统计文件数，并回写 sync_state 避免重复扫描"""
    try:
        from fb.database import get_db
        db = get_db()
        row = db.execute("SELECT local_path FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
        if not row or not row['local_path']:
            return 0
        local_path = row['local_path']
        if not os.path.isdir(local_path):
            return 0
        total = 0
        for root, dirs, files in os.walk(local_path):
            # 跳过隐藏文件和临时文件
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('~')]
            total += sum(1 for f in files if not f.startswith('.') and not f.startswith('~'))
        # 回写 sync_state 缓存，避免下次再扫
        if total > 0:
            try:
                from kb.sync_state import get_sync_state_manager
                state_mgr = get_sync_state_manager()
                state = state_mgr.load_state(owner_id, filebase_id)
                state.total_files = total
                state_mgr.save_state(owner_id, filebase_id, state)
            except Exception:
                import logging
                logging.getLogger(__name__).debug('could not write sync_state cache', exc_info=True)
        return total
    except Exception:
        import logging
        logging.getLogger(__name__).exception('disk count failed')
        return 0


@fb_bp.route('/<fb_id>', methods=['PUT'])
@login_required
@require_fb_perm('manage')
def rename_fb(filebase_id):
    """重命名文件库"""
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '名称不能为空'})

    db = get_db()
    kb_row = db.execute("SELECT local_path, filebase_type FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not kb_row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    filebase_type = kb_row['filebase_type'] or 'local'
    old_path = kb_row['local_path']

    if filebase_type == 'net':
        db.execute("UPDATE filebases SET name = ? WHERE id = ?", (name, filebase_id))
        db.commit()
        _invalidate_list_cache(user_id)
        return jsonify({'success': True, 'message': '重命名成功'})

    parent_dir = os.path.dirname(old_path)
    new_path = os.path.join(parent_dir, name)

    if os.path.exists(new_path):
        return jsonify({'success': False, 'message': '同名目录已存在'})

    try:
        os.rename(old_path, new_path)
    except Exception as e:
        return jsonify({'success': False, 'message': '重命名目录失败: ' + str(e)})

    db.execute("UPDATE filebases SET name = ?, local_path = ? WHERE id = ?", (name, new_path, filebase_id))
    db.commit()
    _invalidate_list_cache(user_id)
    return jsonify({'success': True, 'message': '重命名成功'})


@fb_bp.route('/<fb_id>/agent-settings', methods=['GET', 'PUT'])
@login_required
@require_fb_perm('manage')
def agent_settings(filebase_id):
    """获取/切换文件库的 agent 访问开关"""
    if request.method == 'GET':
        db = get_db()
        row = db.execute(
            "SELECT fb_agent_enabled FROM filebases WHERE id = ?",
            (filebase_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'message': '文件库不存在'})
        enabled = row['fb_agent_enabled']
        return jsonify({
            'success': True,
            'agent_enabled': enabled if enabled is not None else 1
        })

    # PUT: 切换开关
    data = request.get_json() or {}
    enabled = data.get('agent_enabled')
    if enabled is None:
        return jsonify({'success': False, 'message': '缺少 agent_enabled 参数'})
    db = get_db()
    db.execute(
        "UPDATE filebases SET fb_agent_enabled = ? WHERE id = ?",
        (1 if enabled else 0, filebase_id)
    )
    db.commit()
    return jsonify({'success': True, 'agent_enabled': 1 if enabled else 0})


def _cleanup_synced_data(user_id, filebase_id):
    """删除文件库时清理 KB 中的同步数据"""
    try:
        from kb.sync_worker import get_sync_worker
        worker = get_sync_worker()
        worker.cleanup_filebase(user_id, filebase_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to cleanup synced data: {e}")


def _invalidate_list_cache(*user_ids):
    """使 /api/fb/list 的缓存失效（删除/移动后调用，保证列表即时刷新）"""
    for uid in user_ids:
        if uid:
            _list_fb_cache.pop(f"list_fb:{uid}", None)
            _list_fb_cache_time.pop(f"list_fb:{uid}", None)


def _is_path_inside(base_dir, path):
    """判断 path 是否位于 base_dir 目录内（含等于 base_dir 本身），大小写不敏感"""
    if not base_dir or not path:
        return False
    base = os.path.normcase(os.path.normpath(base_dir))
    p = os.path.normcase(os.path.normpath(path))
    return p == base or p.startswith(base + os.sep)


@fb_bp.route('/<fb_id>', methods=['DELETE'])
@login_required
@require_fb_perm('manage')
def delete_fb(filebase_id):
    """删除文件库（软删除：标记 status='trashed'，移到回收站，隐藏 KB 数据）"""
    db = get_db()
    row = db.execute("SELECT id, name, local_path, owner_id, filebase_type, status FROM filebases WHERE id = ?", (filebase_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '文件库不存在'})

    local_path = row['local_path']
    filebase_type = row['filebase_type'] or 'local'
    trash_dir = _get_trash_dir()
    # 使当前操作者与库属主的列表缓存一并失效，保证删除后列表即时刷新
    invalidate_users = (row['owner_id'], g.user_id)

    # 网络文件库：仅解除关联（无本地磁盘目录可删）
    if filebase_type == 'net':
        _cleanup_synced_data(row['owner_id'], filebase_id)
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
        _invalidate_list_cache(*invalidate_users)
        return jsonify({'success': True, 'message': '网络文件库已删除'})

    # 已标记 trashed 的彻底删除（从回收站清空过来）
    if row['status'] == 'trashed' or _is_path_inside(trash_dir, local_path):
        # 只允许删除回收站内的目录，防止脏数据误删用户磁盘上的真实文件夹
        if _is_path_inside(trash_dir, local_path) and os.path.isdir(local_path):
            shutil.rmtree(local_path, ignore_errors=True)
        _cleanup_synced_data(row['owner_id'], filebase_id)
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
        _invalidate_list_cache(*invalidate_users)
        return jsonify({'success': True, 'message': '文件库已彻底删除'})

    # 程序自身管理、位于运行时数据目录内的库（示例文件库等）：
    # 内容由应用生成，删除时连同目录一起清理，不留残留
    if _is_internal_fb_dir(local_path):
        if os.path.isdir(local_path):
            shutil.rmtree(local_path, ignore_errors=True)
        _cleanup_synced_data(row['owner_id'], filebase_id)
        db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
        db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
        db.commit()
        _invalidate_list_cache(*invalidate_users)
        return jsonify({'success': True, 'message': '示例文件库已删除'})

    # 用户自有目录（手动添加的文件夹、历史遗留的桌面库等）：与网络文件库机制一致，
    # 仅解除关联，不移动、不删除本地文件夹
    _cleanup_synced_data(row['owner_id'], filebase_id)
    db.execute("DELETE FROM filebase_permissions WHERE filebase_id = ?", (filebase_id,))
    db.execute("DELETE FROM filebases WHERE id = ?", (filebase_id,))
    db.commit()
    _invalidate_list_cache(*invalidate_users)
    return jsonify({'success': True, 'message': '已从文件库移除，本地文件夹保留'})


def _get_trash_dir():
    """获取回收站目录（位于运行时数据目录下）"""
    from server.workspace import _get_runtime_dir
    trash_dir = os.path.join(_get_runtime_dir(), 'trash')
    os.makedirs(trash_dir, exist_ok=True)
    return trash_dir


# ==================== 示例文件库（首次引导） ====================

_SAMPLE_FB_NAME = '示例文件库'


def _sample_filebase_path():
    """示例文件库所在目录（运行时数据目录内，程序自产自销）"""
    from server.workspace import _get_runtime_dir
    return os.path.join(_get_runtime_dir(), 'libraries', _SAMPLE_FB_NAME)


def _is_internal_fb_dir(path):
    """判断路径是否为程序自身在运行时数据目录内管理的文件库目录"""
    from server.workspace import _get_runtime_dir
    if not path:
        return False
    return _is_path_inside(_get_runtime_dir(), path)


def _write_sample_files(lib_dir):
    """写入示例文件库的入门说明文档"""
    docs = {
        '欢迎使用 Docflowing.md': (
            '# 欢迎使用 Docflowing（文澜）\n\n'
            '这是一个**示例文件库**，用来演示文件库是怎么工作的。\n\n'
            '## 文件库能做什么\n\n'
            '- 集中管理分散在磁盘各处的文档目录，统一检索与预览\n'
            '- 一键把文件库内容「同步到知识库」，变成可对话、可检索的知识资产\n'
            '- 用顶部工具栏的文档工具集处理文档（提取、转 PDF、加页码、套红、比较、索引）\n'
            '- 通过 P2P 与可信节点共享文件库\n\n'
            '## 下一步\n\n'
            '读完本目录的「快速上手.md」后，你可以：\n\n'
            '1. 右键本示例库 → **删除**（仅移除该示例，不残留）\n'
            '2. 点击 **📂 添加本地文件库**，把你的真实资料文件夹加进来\n'
        ),
        '快速上手.md': (
            '# 快速上手\n\n'
            '## 1. 添加已有的资料文件夹\n\n'
            '- 点击顶部 **📂 添加本地文件库**，选择磁盘上的任意文件夹即可\n'
            '- 添加后应用**不会改动、移动你的文件夹**，只是建立索引关联\n'
            '- 没有现成文件夹？先在系统资源管理器里建一个空文件夹，再添加进来即可\n\n'
            '## 2. 把文件库内容变成知识库\n\n'
            '- 进入文件库后右键卡片选择 **同步到知识库**，或在文件库设置里开启同步\n\n'
            '## 3. 用工具集处理文档\n\n'
            '- 顶部「工具」页签提供：文档提取、转 PDF、添加页码、文档套红、文档比较、构建索引\n\n'
            '## 删除文件库\n\n'
            '- **用户自己的文件夹**：删除仅移除关联，磁盘文件原样保留\n'
            '- **程序创建的示例库**：删除会一并清理程序生成的目录\n'
        ),
    }
    for filename, content in docs.items():
        try:
            with open(os.path.join(lib_dir, filename), 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass


def _ensure_sample_filebase(user_id):
    """首次进入（当前用户尚无任何本地文件库）时，在运行时数据目录内创建示例文件库。

    幂等：由应用设置 sample_fb_created 控制，创建过一次后不再重复出现
    （即使示例库后来被删除，也不打扰用户）。
    """
    from server.settings import _load_app_settings, _save_app_settings
    try:
        settings = _load_app_settings()
        if settings.get('sample_fb_created'):
            return

        db = get_db()
        cnt = db.execute(
            "SELECT COUNT(*) AS c FROM filebases WHERE owner_id = ? "
            "AND COALESCE(filebase_type, 'local') != 'net' "
            "AND COALESCE(status, 'active') != 'trashed'",
            (user_id,)
        ).fetchone()['c']
        if cnt > 0:
            # 已有自己的文件库，不需要示例；记录初始化避免每次扫描
            settings['sample_fb_created'] = True
            _save_app_settings(settings)
            return

        lib_dir = _sample_filebase_path()
        os.makedirs(lib_dir, exist_ok=True)
        _write_sample_files(lib_dir)

        sample_id = str(uuid.uuid4())
        now = time.time()
        db.execute(
            "INSERT INTO filebases (id, name, owner_id, filebase_type, local_path, created_at, is_synced_to_kb) "
            "VALUES (?, ?, ?, 'local', ?, ?, 0)",
            (sample_id, _SAMPLE_FB_NAME, user_id, lib_dir, now)
        )
        db.execute(
            "INSERT INTO filebase_permissions (filebase_id, user_id, permission_level) VALUES (?, ?, 'manage')",
            (sample_id, user_id)
        )
        db.commit()

        settings['sample_fb_created'] = True
        _save_app_settings(settings)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning('创建示例文件库失败: %s', e)
