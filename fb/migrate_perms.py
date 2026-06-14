"""
数据迁移脚本：将旧版 filebase_permissions 迁移到新的 filebase_perm_v2 表

在更新代码后运行此脚本，将现有权限数据迁移到新的位掩码格式。

运行方式：
    python fb/migrate_perms.py

或通过 API 触发：
    curl -X POST http://localhost:5000/api/fb/admin/migrate-perms
"""

import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fb.database import get_db
from fb.decorators import ROLE_TEMPLATES

LEVEL_TO_MASK = {
    'view':   ROLE_TEMPLATES['view'],
    'edit':   ROLE_TEMPLATES['edit'],
    'manage': ROLE_TEMPLATES['manage'],
}


def migrate_permissions():
    """将 filebase_permissions 表中所有记录迁移到 filebase_perm_v2"""
    db = get_db()
    rows = db.execute(
        "SELECT filebase_id, user_id, permission_level, created_at FROM filebase_permissions"
    ).fetchall()

    if not rows:
        print("没有需要迁移的权限记录。")
        return {'migrated': 0, 'skipped': 0, 'errors': 0}

    migrated = 0
    skipped = 0
    errors = 0
    now = time.time()

    for row in rows:
        perm_mask = LEVEL_TO_MASK.get(row['permission_level'])
        if perm_mask is None:
            print("  警告: 未知权限级别 %s，跳过 %s/%s" % (row['permission_level'], row['filebase_id'], row['user_id']))
            errors += 1
            continue

        try:
            existing = db.execute(
                "SELECT perm_mask FROM filebase_perm_v2 WHERE filebase_id = ? AND user_id = ?",
                (row['filebase_id'], row['user_id'])
            ).fetchone()

            if existing:
                new_mask = existing['perm_mask'] | perm_mask
                if new_mask != existing['perm_mask']:
                    db.execute(
                        "UPDATE filebase_perm_v2 SET perm_mask = ?, updated_at = ? WHERE filebase_id = ? AND user_id = ?",
                        (new_mask, now, row['filebase_id'], row['user_id'])
                    )
                    migrated += 1
                else:
                    skipped += 1
            else:
                created = row['created_at'] or now
                db.execute(
                    "INSERT INTO filebase_perm_v2 (filebase_id, user_id, perm_mask, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (row['filebase_id'], row['user_id'], perm_mask, created, now)
                )
                migrated += 1
        except Exception as e:
            print("  错误: 迁移 %s/%s 失败: %s" % (row['filebase_id'], row['user_id'], e))
            errors += 1

    db.commit()
    print("\n迁移完成: %d 条迁移, %d 条已存在跳过, %d 条错误" % (migrated, skipped, errors))
    return {'migrated': migrated, 'skipped': skipped, 'errors': errors}


def migrate_owner_permissions():
    """确保所有文件库的所有者在 filebase_perm_v2 中有 manage 权限"""
    db = get_db()
    rows = db.execute("SELECT id, owner_id, created_at FROM filebases").fetchall()
    now = time.time()
    migrated = 0
    for row in rows:
        existing = db.execute(
            "SELECT perm_mask FROM filebase_perm_v2 WHERE filebase_id = ? AND user_id = ?",
            (row['id'], row['owner_id'])
        ).fetchone()
        if existing:
            new_mask = existing['perm_mask'] | ROLE_TEMPLATES['manage']
            if new_mask != existing['perm_mask']:
                db.execute(
                    "UPDATE filebase_perm_v2 SET perm_mask = ?, updated_at = ? WHERE filebase_id = ? AND user_id = ?",
                    (new_mask, now, row['id'], row['owner_id'])
                )
                migrated += 1
        else:
            created = row['created_at'] or now
            db.execute(
                "INSERT INTO filebase_perm_v2 (filebase_id, user_id, perm_mask, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (row['id'], row['owner_id'], ROLE_TEMPLATES['manage'], created, now)
            )
            migrated += 1
    db.commit()
    print("所有者权限迁移: %d 条记录已更新/添加" % migrated)
    return migrated


if __name__ == '__main__':
    print("=" * 50)
    print("Docflowing 权限迁移脚本 v1.0")
    print("=" * 50)
    r1 = migrate_permissions()
    r2 = migrate_owner_permissions()
    total = r1['migrated'] + (r2 if isinstance(r2, int) else 0)
    print("\n总计: %d 条记录已迁移" % total)
    print("迁移完成！请检查应用是否正常运行。")
