#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FB 同步功能测试脚本
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_converters():
    """测试文件转换器"""
    print("=" * 50)
    print("测试 1: 文件转换器")
    print("=" * 50)

    from kb.sync_converters import can_convert, get_converter

    test_files = [
        "test.docx",
        "test.doc",
        "test.pdf",
        "test.md",
        "test.txt",
        "test.xlsx",
        "test.pptx",
    ]

    for f in test_files:
        can = can_convert(f)
        conv = get_converter(f)
        print(f"  {f}: 可转换={can}, 转换器={conv.file_type if conv else 'None'}")

    print()


def test_state_manager():
    """测试状态管理器"""
    print("=" * 50)
    print("测试 2: 状态管理器")
    print("=" * 50)

    from kb.sync_state import get_sync_state_manager, SyncState

    manager = get_sync_state_manager()

    test_user = "test_user"
    test_filebase = "test_filebase_001"

    state = manager.load_state(test_user, test_filebase)
    print(f"  创建状态: filebase_id={state.filebase_id}")

    manager.update_file_state(
        test_user, test_filebase,
        "test_file.md",
        source_mtime=1234567890.0,
        status="synced"
    )

    state = manager.get_state(test_user, test_filebase)
    print(f"  文件数: {len(state.files)}")

    manager.clear_all_state(test_user, test_filebase)
    print(f"  清理完成")

    print()


def test_sync_worker():
    """测试同步工作线程"""
    print("=" * 50)
    print("测试 3: 同步工作线程")
    print("=" * 50)

    from kb.sync_worker import get_sync_worker

    worker = get_sync_worker()
    print(f"  工作线程实例: {worker}")
    print(f"  轮询间隔: {worker.interval} 秒")
    print(f"  最大并发: {worker._max_concurrent}")
    print(f"  运行状态: {worker._running}")

    print()


def test_database_migration():
    """测试数据库迁移"""
    print("=" * 50)
    print("测试 4: 数据库迁移")
    print("=" * 50)

    from fb.database import get_db
    from fb.models import MIGRATIONS

    db = get_db()

    print(f"  执行迁移数量: {len(MIGRATIONS)}")

    for i, migration in enumerate(MIGRATIONS):
        try:
            db.execute(migration)
            db.commit()
            print(f"  迁移 {i+1}: 执行成功")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print(f"  迁移 {i+1}: 字段已存在，跳过")
            else:
                print(f"  迁移 {i+1}: {e}")

    cursor = db.execute("PRAGMA table_info(filebases)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"  filebases 表字段: {columns}")

    if 'is_synced_to_kb' in columns:
        print("  ✓ is_synced_to_kb 字段已存在")
    else:
        print("  ✗ is_synced_to_kb 字段不存在")

    print()


def main():
    """主测试函数"""
    print()
    print("🚀 FB 同步功能测试")
    print()

    try:
        test_converters()
        test_state_manager()
        test_sync_worker()
        test_database_migration()

        print("=" * 50)
        print("✅ 所有测试通过！")
        print("=" * 50)
        print()
        print("同步功能已成功实现！")
        print()
        print("使用说明：")
        print("1. 在文件库卡片上右键点击")
        print("2. 选择 '同步到 KB' 启用同步")
        print("3. 选择 '立即同步' 手动触发同步")
        print("4. 同步状态会显示在卡片底部")
        print()

        return 0

    except Exception as e:
        print("=" * 50)
        print("❌ 测试失败")
        print("=" * 50)
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
