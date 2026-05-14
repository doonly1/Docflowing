# FB 文件库同步到 KB 技术设计方案

> 本文档详细描述了将 FB 文件库中的文档文件自动同步转换为 Markdown 并存储到 KB 的完整技术方案。

## 1. 需求概述

### 1.1 核心功能
- 将 FB 文件库中的文档（doc/docx/pdf/md/txt）自动转换为 Markdown 格式
- 同步存储到用户 KB 的 `imported/{filebase_id}/` 目录
- 保持原目录结构和文件名
- 实现增量同步，跟随原文件的修改和删除

### 1.2 设计原则
- **简单实用**：先实现核心功能，预留扩展接口
- **用户可控**：用户可开关同步，手动触发同步
- **性能优先**：后台异步处理，不影响主业务
- **数据安全**：只读原文件，不修改用户数据

## 2. 技术架构

### 2.1 整体架构
```
┌─────────────────────────────────────────────────────────────┐
│                      Flask Web 应用                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  FB Routes   │  │  KB Routes   │  │  Sync Worker     │   │
│  │  (文件管理)   │  │  (知识库)    │  │  (后台线程)      │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
└─────────┼─────────────────┼───────────────────┼─────────────┘
          │                 │                   │
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                      数据存储层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ fb/fb.db     │  │ kb/wiki.db  │  │ workspaces/      │   │
│  │ (文件库信息) │  │ (FTS索引)    │  │ {user_id}/kb/    │   │
│  └──────────────┘  └──────────────┘  │ imported/{fb_id}/ │   │
│                                       └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 组件说明

| 组件 | 职责 | 实现方式 |
|------|------|---------|
| **Sync Worker** | 后台轮询 + 同步执行 | 独立线程，每 60 秒扫描 |
| **File Converter** | 文件格式转换 | 可扩展的转换器注册表 |
| **Sync State Manager** | 同步状态记录 | JSON 文件 + 内存缓存 |
| **FB Routes** | 前端交互接口 | 右键菜单、状态显示 |
| **KB Importer** | KB 文件写入 | 调用现有 KB Routes |

## 3. 数据模型

### 3.1 数据库变更

```sql
-- fb/models.py
ALTER TABLE knowledge_bases ADD COLUMN sync_to_kb BOOLEAN DEFAULT FALSE;
```

### 3.2 同步状态文件

```json
// workspaces/{user_id}/kb/imported/{filebase_id}/_sync_state.json
{
  "filebase_id": "xxx-xxx-xxx",
  "last_sync": 1706123456,
  "total_files": 523,
  "syncable_files": 500,
  "synced_files": 498,
  "failed_files": [
    {
      "path": "subdir/protected.docx",
      "reason": "file_locked",
      "retry_count": 3,
      "last_retry": 1706123000
    }
  ],
  "files": {
    "subdir1/file1.md": {
      "source": "subdir1/file1.docx",
      "source_mtime": 1706123000,
      "target_mtime": 1706123050,
      "status": "synced",
      "error": null
    }
  }
}
```

### 3.3 KB 目录结构

```
workspaces/{user_id}/kb/
├── wiki.db              # 现有 FTS 数据库
├── data/
│   └── state.db         # 现有会话数据库
├── memories/            # 现有记忆文件
├── skills/              # 现有技能
└── imported/            # FB 同步文件（新）
    └── {filebase_id}/   # 按 filebase_id 隔离
        ├── _sync_state.json
        ├── readme.md
        ├── doc1.md
        ├── doc2.md
        └── subdir/
            ├── file3.md
            └── file4.md
```

## 4. 文件转换模块

### 4.1 转换器注册表

```python
# kb/sync_converters.py
from abc import ABC, abstractmethod
from typing import Optional

class BaseConverter(ABC):
    @abstractmethod
    def can_convert(self, file_path: str) -> bool:
        pass

    @abstractmethod
    def convert(self, source_path: str) -> Optional[str]:
        """返回转换后的 Markdown 文本，失败返回 None"""
        pass

    def get_metadata(self, file_path: str) -> dict:
        """返回文件元数据"""
        return {
            "source_type": self.file_type,
            "converted_at": time.time()
        }

# 注册默认转换器
CONVERTERS = {
    ".docx": DOCXConverter(),
    ".doc": DOCConverter(),      # 先转 docx，再转 md
    ".pdf": PDFConverter(),
    ".md": MDConverter(),        # 直接复制，可能需要处理 frontmatter
    ".txt": TXTConverter(),
}
```

### 4.2 转换器实现要点

#### 4.2.1 DOCX 转换器
- 使用 `python-docx` 库
- 提取段落文本，识别标题样式
- 保留表格为 Markdown 表格
- 提取图片元数据（暂不处理图片内容）

#### 4.2.2 PDF 转换器
- 使用 `pdfplumber` 库
- 按页提取文本
- 保留段落结构

#### 4.2.3 MD 转换器
- 读取原文件
- 如果已有 frontmatter，保留
- 如果没有，添加基本 frontmatter

#### 4.2.4 TXT 转换器
- 直接读取文本内容
- 添加 frontmatter

### 4.3 Markdown Frontmatter 格式

```markdown
---
source_file: subdir/report.docx
source_type: docx
source_size: 102400
source_mtime: 1706123000
filebase_id: xxx-xxx-xxx
synced_at: 1706123456
---

# 文档标题

正文内容...
```

### 4.4 转换错误类型

| 错误类型 | 说明 | 处理方式 |
|---------|------|---------|
| `file_not_found` | 文件不存在 | 删除同步记录 |
| `permission_denied` | 权限不足 | 标记为失败 |
| `file_locked` | 文件被占用 | 等待后重试 |
| `corrupted_file` | 文件损坏 | 标记为失败 |
| `encrypted_file` | 文件加密 | 标记为失败 |
| `conversion_failed` | 转换失败 | 标记为失败 |

## 5. 同步机制

### 5.1 后台同步线程

```python
import threading
import time
from typing import Set

class SyncWorker:
    def __init__(self, interval: int = 60):
        self.interval = interval
        self._running = False
        self._thread = None
        self._processing_filebases: Set[str] = set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                self._sync_all_enabled_filebases()
            except Exception as e:
                logger.error(f"Sync worker error: {e}")
            time.sleep(self.interval)

    def _sync_all_enabled_filebases(self):
        """扫描所有启用了同步的文件库"""
        for filebase in get_enabled_filebases():
            if filebase.id not in self._processing_filebases:
                self._sync_filebase(filebase)

    def _sync_filebase(self, filebase):
        """同步单个文件库"""
        self._processing_filebases.add(filebase.id)
        try:
            # 1. 扫描文件库，获取当前文件列表
            current_files = scan_filebase(filebase)

            # 2. 加载同步状态
            state = load_sync_state(filebase)

            # 3. 比较并处理变化
            self._process_changes(filebase, current_files, state)

            # 4. 更新状态文件
            save_sync_state(filebase, state)

            # 5. 清理已删除的文件
            self._cleanup_deleted(filebase, current_files, state)

        finally:
            self._processing_filebases.discard(filebase.id)

    def _process_changes(self, filebase, current_files, state):
        """处理新增和修改的文件"""
        for file_path in current_files:
            if not self._is_syncable(file_path):
                continue

            source_mtime = get_file_mtime(file_path)
            existing = state.files.get(file_path)

            # 判断是否需要同步
            needs_sync = (
                existing is None or  # 新文件
                existing["source_mtime"] < source_mtime  # 已修改
            )

            if needs_sync:
                self._convert_and_sync(filebase, file_path, state)

    def _convert_and_sync(self, filebase, file_path, state):
        """转换并同步单个文件"""
        try:
            # 1. 读取并转换
            converter = get_converter(file_path)
            md_content = converter.convert(file_path)

            if md_content is None:
                raise ConversionError(f"Failed to convert {file_path}")

            # 2. 写入 KB
            target_path = get_target_path(filebase, file_path)
            write_kb_file(target_path, md_content)

            # 3. 更新状态
            state.files[file_path] = {
                "source": file_path,
                "source_mtime": get_file_mtime(file_path),
                "target_mtime": time.time(),
                "status": "synced",
                "error": None
            }

        except Exception as e:
            state.files[file_path] = {
                "source": file_path,
                "status": "failed",
                "error": str(e),
                "retry_count": state.files.get(file_path, {}).get("retry_count", 0) + 1
            }
```

### 5.2 同步策略

| 场景 | 处理方式 |
|------|---------|
| **首次启用同步** | 全量扫描 + 分批处理（每批 50 个） |
| **定时同步** | 增量同步，只处理修改的文件 |
| **手动触发** | 立即执行一次完整扫描 |
| **同步失败** | 等待 5 分钟重试，最多重试 3 次 |
| **原文件删除** | 级联删除 KB 中的同步文件 |
| **文件库删除** | 级联删除 `imported/{filebase_id}/` |

### 5.3 性能控制

- **并发限制**：最多同时同步 3 个文件
- **批量大小**：首次同步每批 50 个文件
- **重试间隔**：失败后 5 分钟再重试
- **超时设置**：单个文件转换超时 30 秒

## 6. 前端交互

### 6.1 右键菜单

在 FB 文件库卡片上右键显示菜单：

```
┌─────────────────────────────┐
│ 📂 在文件管理器中打开        │
│ 🔄 刷新                      │
├─────────────────────────────┤
│ ☑ 同步到 KB                  │  ← 开关选项
│ 🔄 立即同步                  │  ← 仅在启用同步时显示
├─────────────────────────────┤
│ ✏️ 重命名                    │
│ 🗑️ 删除                      │
└─────────────────────────────┘
```

### 6.2 文件库列表显示

文件库卡片显示同步状态：

```
┌─────────────────────────────┐
│ 📁 项目文档库                │
│                             │
│ 文件数: 523                 │
│ 同步: 523/500/498          │
│                             │
│ [查看文件库]                │
└─────────────────────────────┘
```

格式说明：
- **未启用同步**：`523`（只显示总文件数）
- **已启用同步**：`523/500/498`（总文件数/可同步/已同步）

### 6.3 API 接口

```python
# fb/routes.py

@fb_bp.route('/filebase/<kb_id>/sync', methods=['POST'])
@login_required
def toggle_sync(kb_id):
    """切换文件库同步状态"""
    data = request.get_json()
    enabled = data.get('enabled', False)

    # 验证权限（必须是 owner）
    if not is_owner(kb_id, g.user_id):
        return jsonify({'success': False, 'error': '权限不足'}), 403

    # 更新数据库
    update_filebase_sync(kb_id, enabled)

    # 如果启用，立即触发一次同步
    if enabled:
        trigger_sync(kb_id)

    return jsonify({'success': True})

@fb_bp.route('/filebase/<kb_id>/sync-now', methods=['POST'])
@login_required
def sync_now(kb_id):
    """手动触发立即同步"""
    if not is_owner(kb_id, g.user_id):
        return jsonify({'success': False, 'error': '权限不足'}), 403

    # 触发后台同步
    trigger_sync(kb_id)

    return jsonify({'success': True, 'message': '同步已触发'})

@fb_bp.route('/filebase/<kb_id>/sync-status', methods=['GET'])
@login_required
def get_sync_status(kb_id):
    """获取同步状态"""
    state = get_sync_state(kb_id)

    return jsonify({
        'success': True,
        'enabled': is_sync_enabled(kb_id),
        'status': {
            'total_files': state.total_files,
            'syncable_files': state.syncable_files,
            'synced_files': state.synced_files,
            'failed_count': len(state.failed_files),
            'last_sync': state.last_sync
        }
    })
```

### 6.4 WebSocket 推送（可选）

如果需要实时更新同步状态，可以添加 WebSocket 推送：

```javascript
// 前端监听同步状态变化
socket.on('sync_status_update', (data) => {
    updateFilebaseCard(data.kb_id, data.status);
});
```

## 7. 实现步骤

### Phase 1: 核心功能
1. 实现文件转换器注册表和基础转换器
2. 实现同步状态管理器
3. 实现后台同步线程
4. 实现 KB 文件写入功能
5. 实现 API 接口

### Phase 2: 前端集成
1. 右键菜单添加同步选项
2. 文件库卡片显示同步状态
3. 自动刷新逻辑

### Phase 3: 完善功能
1. 错误处理和重试机制
2. 性能优化（并发控制）
3. 日志记录

### Phase 4: 扩展功能（预留）
1. 更多文件类型支持
2. 图片处理（OCR）
3. LLM 智能优化

## 8. 关键文件清单

| 文件路径 | 说明 |
|---------|------|
| `kb/sync_worker.py` | 同步工作线程 |
| `kb/sync_converters.py` | 文件转换器 |
| `kb/sync_state.py` | 同步状态管理 |
| `kb/sync_api.py` | 同步相关 API |
| `fb/routes.py` | 修改：添加同步接口 |
| `fb/models.py` | 修改：添加 sync_to_kb 字段 |
| `ui/js/fb.js` | 修改：右键菜单和状态显示 |
| `server/__init__.py` | 修改：启动同步线程 |

## 9. 扩展性设计

### 9.1 添加新文件类型

```python
# kb/sync_converters.py

class XLSXConverter(BaseConverter):
    @property
    def file_type(self):
        return "xlsx"

    def can_convert(self, file_path: str) -> bool:
        return file_path.lower().endswith('.xlsx')

    def convert(self, source_path: str) -> Optional[str]:
        # 实现转换逻辑
        pass

# 注册新转换器
CONVERTERS[".xlsx"] = XLSXConverter()
```

### 9.2 添加图片处理

```python
class ImageConverter(BaseConverter):
    def convert(self, source_path: str) -> Optional[str]:
        # 1. 提取图片元数据
        metadata = extract_image_metadata(source_path)

        # 2. 调用 OCR（如果有配置）
        if config.get('enable_ocr'):
            text = ocr_image(source_path)
            return self._build_md_with_text(metadata, text)

        # 3. 只返回元数据
        return self._build_md_with_metadata(metadata)
```

### 9.3 LLM 优化（未来）

```python
class LLMOptimizer:
    def optimize(self, md_content: str, context: dict) -> str:
        """使用 LLM 优化 Markdown 内容"""
        prompt = f"""
请优化以下 Markdown 文档：
1. 修正格式错误
2. 改善结构
3. 添加适当的标题层级

文档内容：
{md_content}
"""
        return call_llm(prompt)
```

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 大文件转换超时 | 单个文件同步失败 | 30 秒超时限制 |
| 磁盘空间不足 | 同步中断 | 转换前检查空间 |
| 文件被占用 | 转换失败 | 重试机制 |
| 同步线程异常 | 同步停止 | 异常捕获 + 日志 |
| 状态文件损坏 | 状态丢失 | 定期备份 + 重新扫描 |

## 11. 测试计划

### 单元测试
- 每个转换器的转换逻辑
- 状态管理器的读写操作
- 文件比较逻辑

### 集成测试
- 完整同步流程
- 右键菜单交互
- 前端状态显示

### 性能测试
- 500+ 文件的首次同步
- 增量同步性能
- 并发同步测试

---

**文档版本**: 1.0
**创建日期**: 2026-05-14
**状态**: 待实施
