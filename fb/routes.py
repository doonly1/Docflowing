"""
文件库路由主入口

按功能模块拆分为多个子模块：
- decorators: 公共装饰器
- routes_base: 基础 CRUD
- routes_trash: 回收站
- routes_members: 成员权限
- routes_search: 全文搜索
- routes_files: 文件操作（浏览、上传）
- routes_files_ops: 文件操作（下载、预览）
- routes_files_edit: 文件操作（编辑、移动、删除）
- routes_sync: KB 同步
- routes_p2p: P2P 共享
- routes_tools: 工具执行
"""

from fb.decorators import (
    _is_remote_fb, _get_node_identity, _ensure_local_fb_route,
    _check_fb_permission, _require_fb_permission, _is_admin,
    PERMISSION_LEVELS
)

from fb.routes_base import (
    fb_bp, _get_user_workspace, _get_trash_dir, _cleanup_synced_data
)

from fb.routes_trash import (
    clear_trash, list_trash, restore_from_trash, delete_trash_item
)
fb_bp.add_url_rule('/trash', 'clear_trash', clear_trash, methods=['DELETE'])
fb_bp.add_url_rule('/trash-list', 'list_trash', list_trash, methods=['GET'])
fb_bp.add_url_rule('/trash-restore', 'restore_from_trash', restore_from_trash, methods=['POST'])
fb_bp.add_url_rule('/trash-item', 'delete_trash_item', delete_trash_item, methods=['DELETE'])

from fb.routes_search import search_documents
fb_bp.add_url_rule('/search', 'search_documents', search_documents, methods=['GET'])

from fb.routes_files import (
    upload_local_files, create_local_dir, create_local_file, create_office_file,
    list_local_files, list_local_categories,
    _resolve_local_path, _trigger_fb_sync
)
fb_bp.add_url_rule('/<fb_id>/local-files', 'upload_local_files', upload_local_files, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/dir', 'create_local_dir', create_local_dir, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/create', 'create_local_file', create_local_file, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/create-office', 'create_office_file', create_office_file, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files', 'list_local_files', list_local_files, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/local-categories', 'list_local_categories', list_local_categories, methods=['GET'])

from fb.routes_files_ops import (
    save_local_file_content, get_local_file_content, file_preview,
    download_local_file, batch_download_local, save_local_file_as,
    batch_save_local_files, open_local_file, open_with_app
)
fb_bp.add_url_rule('/<fb_id>/local-files/content', 'save_local_file_content', save_local_file_content, methods=['PUT'])
fb_bp.add_url_rule('/<fb_id>/local-files/content', 'get_local_file_content', get_local_file_content, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/local-files/preview', 'file_preview', file_preview, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/local-files/download', 'download_local_file', download_local_file, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/local-files/batch-download', 'batch_download_local', batch_download_local, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/save-as', 'save_local_file_as', save_local_file_as, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/batch-save-as', 'batch_save_local_files', batch_save_local_files, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/open', 'open_local_file', open_local_file, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/local-files/open-with-app', 'open_with_app', open_with_app, methods=['GET'])

from fb.routes_files_edit import (
    replace_local_file, move_local_items, delete_local_items,
    rename_local_item, copy_local_items,
    list_file_trash, restore_file_trash, delete_file_trash_item
)
fb_bp.add_url_rule('/<fb_id>/local-files/replace', 'replace_local_file', replace_local_file, methods=['PUT'])
fb_bp.add_url_rule('/<fb_id>/local-files/move', 'move_local_items', move_local_items, methods=['PUT'])
fb_bp.add_url_rule('/<fb_id>/local-files', 'delete_local_items', delete_local_items, methods=['DELETE'])
fb_bp.add_url_rule('/<fb_id>/local-files/rename', 'rename_local_item', rename_local_item, methods=['PUT'])
fb_bp.add_url_rule('/<fb_id>/local-files/copy', 'copy_local_items', copy_local_items, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/trash-items', 'list_file_trash', list_file_trash, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/local-files/trash-restore', 'restore_file_trash', restore_file_trash, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/local-files/trash-item', 'delete_file_trash_item', delete_file_trash_item, methods=['DELETE'])

from fb.routes_sync import toggle_sync, sync_now, get_sync_status
fb_bp.add_url_rule('/<fb_id>/sync', 'toggle_sync', toggle_sync, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/sync-now', 'sync_now', sync_now, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/sync-status', 'get_sync_status', get_sync_status, methods=['GET'])

from fb.routes_p2p import (
    share_filebase, list_shared_nodes, revoke_share, batch_share,
    get_p2p_node_info, update_p2p_node_info, get_discovered_nodes
)
fb_bp.add_url_rule('/<fb_id>/share', 'share_filebase', share_filebase, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/shared-nodes', 'list_shared_nodes', list_shared_nodes, methods=['GET'])
fb_bp.add_url_rule('/<fb_id>/shared-nodes/<node_id>', 'revoke_share', revoke_share, methods=['DELETE'])
fb_bp.add_url_rule('/share-batch', 'batch_share', batch_share, methods=['POST'])
fb_bp.add_url_rule('/p2p/node', 'get_p2p_node_info', get_p2p_node_info, methods=['GET'])
fb_bp.add_url_rule('/p2p/node', 'update_p2p_node_info', update_p2p_node_info, methods=['PUT'])
fb_bp.add_url_rule('/p2p/discovered-nodes', 'get_discovered_nodes', get_discovered_nodes, methods=['GET'])

from fb.routes_tools import run_tool_on_fb, convert_doc_files
fb_bp.add_url_rule('/<fb_id>/run-tool', 'run_tool_on_fb', run_tool_on_fb, methods=['POST'])
fb_bp.add_url_rule('/<fb_id>/convert-doc', 'convert_doc_files', convert_doc_files, methods=['POST'])
