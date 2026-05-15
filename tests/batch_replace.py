import os
import re

def replace_in_sql_strings(file_path, old, new):
    """只替换引号包裹的 SQL 字符串"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则替换
    # 匹配单引号或双引号包裹的内容，只在其中替换
    def replacer(match):
        return match.group(0).replace(old, new)
    
    # 分别处理双引号和单引号
    pattern = r'"[^"]*"'
    content = re.sub(pattern, replacer, content)
    
    pattern = r"'[^']*'"
    content = re.sub(pattern, replacer, content)
    
    return content

def batch_replace_in_file(file_path, replacements):
    content = None
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换所有的键值对，全文件替换
    for old, new in replacements:
        content = content.replace(old, new)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated: {file_path}")

if __name__ == '__main__':
    # 需要修改的文件列表
    files = [
        'fb/routes.py'
    ]
    
    # 只替换 SQL 中常见的模式
    sql_replacements = [
        # 表名
        ('knowledge_bases', 'filebases'),
        ('kb_permissions', 'filebase_permissions'),
        ('file_sync_states', 'filebase_sync_states'),
        
        # 字段替换，只替换SQL相关的
        ('kb_id,', 'filebase_id,'),
        (' kb_id', ' filebase_id'),
        ('kb_id =', 'filebase_id ='),
        ('kb_type,', 'filebase_type,'),
        ('kb_type', 'filebase_type'),
        ('sync_to_kb', 'is_synced_to_kb'),
        ('(kb_id', '(filebase_id'),
        ('kb_id)', 'filebase_id)'),
    ]
    
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    for fpath in files:
        full_path = os.path.join(project_root, fpath)
        if os.path.exists(full_path):
            batch_replace_in_file(full_path, sql_replacements)
        else:
            print(f"File not found: {fpath}")
