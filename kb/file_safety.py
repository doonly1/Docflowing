import os
from typing import Optional


def build_write_denied_paths(home: str) -> set:
    return {
        os.path.realpath(p)
        for p in [
            os.path.join(home, ".ssh", "authorized_keys"),
            os.path.join(home, ".ssh", "id_rsa"),
            os.path.join(home, ".ssh", "id_ed25519"),
            os.path.join(home, ".ssh", "config"),
            os.path.join(home, ".bashrc"),
            os.path.join(home, ".zshrc"),
            os.path.join(home, ".profile"),
            os.path.join(home, ".bash_profile"),
            os.path.join(home, ".zprofile"),
            os.path.join(home, ".netrc"),
            os.path.join(home, ".pgpass"),
            os.path.join(home, ".npmrc"),
            os.path.join(home, ".pypirc"),
            "/etc/sudoers",
            "/etc/passwd",
            "/etc/shadow",
        ]
    }


def build_write_denied_prefixes(home: str) -> list:
    return [
        os.path.realpath(p) + os.sep
        for p in [
            os.path.join(home, ".ssh"),
            os.path.join(home, ".aws"),
            os.path.join(home, ".gnupg"),
            os.path.join(home, ".kube"),
            os.path.join(home, ".docker"),
            os.path.join(home, ".azure"),
            os.path.join(home, ".config", "gh"),
            "/etc/sudoers.d",
            "/etc/systemd",
        ]
    ]


def is_write_denied(path: str) -> bool:
    home = os.path.realpath(os.path.expanduser("~"))
    try:
        resolved = os.path.realpath(os.path.expanduser(str(path)))
    except Exception:
        return True

    if resolved in build_write_denied_paths(home):
        return True

    for prefix in build_write_denied_prefixes(home):
        if resolved.startswith(prefix):
            return True

    return False


def validate_skill_path(user_id: str, skill_name: str, file_path: str) -> Optional[str]:
    if not skill_name or not skill_name.strip():
        return "技能名称不能为空"

    dangerous_chars = ['/', '\\', '\0', '\n', '\r']
    for ch in dangerous_chars:
        if ch in skill_name:
            return f"技能名称包含非法字符"

    if skill_name.startswith('.') or skill_name.startswith('-'):
        return "技能名称不能以 . 或 - 开头"

    if file_path:
        normalized = os.path.normpath(file_path)
        if normalized.startswith('..') or os.path.isabs(normalized):
            return "文件路径不能包含路径穿越或绝对路径"

        dangerous_extensions = ['.exe', '.bat', '.cmd', '.ps1', '.vbs', '.js', '.wsf', '.scr']
        _, ext = os.path.splitext(normalized)
        if ext.lower() in dangerous_extensions:
            return f"不允许的文件类型: {ext}"

    return None


def validate_content_safety(content: str) -> Optional[str]:
    from .memory import scan_content
    return scan_content(content)
