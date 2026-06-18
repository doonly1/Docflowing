import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .usage import (
    _get_user_skills_dir,
    bump_use,
    bump_patch,
    bump_view,
    delete_record,
    get_record,
    list_records,
    _ensure_record,
)

logger = logging.getLogger(__name__)

_THREAT_PATTERNS = [
    (r'os\.system\s*\(', "os_system_exec"),
    (r'subprocess\.(call|run|Popen)\s*\(', "subprocess_exec"),
    (r'eval\s*\(', "eval_exec"),
    (r'exec\s*\(', "exec_exec"),
    (r'__import__\s*\(', "dunder_import"),
    (r'rm\s+-rf\s+/', "rm_rf"),
    (r'curl\s+[^\n]*\|\s*(bash|sh)', "curl_pipe_shell"),
    (r'wget\s+[^\n]*-O\s*-', "wget_pipe_stdout"),
]


def scan_skill_for_security(skill_dir: Path) -> Optional[str]:
    if not skill_dir.exists():
        return None
    for md_file in skill_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            for pattern, pid in _THREAT_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    return f"Security scan failed: {md_file.name} matches threat pattern '{pid}'."
        except (OSError, IOError):
            pass
    return None


def _parse_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return None
    fm_text = match.group(1)
    try:
        import yaml
        result = yaml.safe_load(fm_text)
        if isinstance(result, dict):
            return result
    except ImportError:
        pass
    except Exception:
        pass
    fm = {}
    for line in fm_text.split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    return fm


def _validate_frontmatter(content: str) -> Optional[str]:
    fm = _parse_frontmatter(content)
    if not fm:
        return "Missing frontmatter (--- block at the top)."
    if 'name' not in fm:
        return "Frontmatter must include 'name' field."
    return None


def _validate_name(name: str) -> Optional[str]:
    if not name:
        return "Name is required."
    if not re.match(r'^[a-z0-9][a-z0-9_-]*$', name):
        return "Name must be lowercase alphanumeric with hyphens or underscores."
    if len(name) > 50:
        return "Name too long (max 50 chars)."
    return None


def create_skill(user_id: str, name: str, content: str, category: str = None, created_by: str = "user") -> Dict[str, Any]:
    from ..file_lock import get_lock

    err = _validate_name(name)
    if err:
        return {"success": False, "error": err}

    err = _validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}

    skill_dir = _get_user_skills_dir(user_id) / name
    if skill_dir.exists():
        return {"success": False, "error": f"Skill '{name}' already exists."}

    try:
        with get_lock(f"skill_{user_id}_{name}"):
            skill_dir.mkdir(parents=True, exist_ok=True)
            for subdir in ("references", "templates", "scripts"):
                (skill_dir / subdir).mkdir(exist_ok=True)
            skill_md = skill_dir / "SKILL.md"
            fd, tmp_path = tempfile.mkstemp(dir=str(skill_dir), suffix=".tmp", prefix=".skill_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, skill_md)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            scan_error = scan_skill_for_security(skill_dir)
            if scan_error:
                import shutil
                shutil.rmtree(skill_dir, ignore_errors=True)
                return {"success": False, "error": scan_error}

            _ensure_record(user_id, name, created_by=created_by)

            return {
                "success": True,
                "name": name,
                "path": str(skill_md),
                "message": f"Skill '{name}' created.",
            }
    except TimeoutError:
        return {"success": False, "error": f"Skill '{name}' is locked by another operation."}
    except Exception as e:
        import shutil
        shutil.rmtree(skill_dir, ignore_errors=True)
        return {"success": False, "error": str(e)}


def _get_system_skills_dir() -> Path:
    """系统技能目录定位。

    - 开发模式：项目根 / kb/skills/system（由 __file__ 向上推导）
    - PyInstaller frozen 模式：sys._MEIPASS/kb/skills/system
    """
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        meipass = getattr(_sys, '_MEIPASS', None)
        if meipass:
            candidate = Path(meipass) / 'kb' / 'skills' / 'system'
            if candidate.exists():
                return candidate
    # 开发模式（或 frozen 下找不到时回退）：基于 __file__
    kb_root = Path(__file__).resolve().parent.parent.parent
    return kb_root / 'kb' / 'skills' / 'system'


def _find_system_skill(name: str) -> Optional[Path]:
    system_dir = _get_system_skills_dir()
    if not system_dir.exists():
        return None
    skill_md = system_dir / name / "SKILL.md"
    if skill_md.exists():
        return skill_md
    return None


def get_skill(user_id: str, name: str) -> Dict[str, Any]:
    skill_dir = _get_user_skills_dir(user_id) / name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        archive_dir = _get_user_skills_dir(user_id) / ".archive" / name / "SKILL.md"
        if archive_dir.exists():
            skill_md = archive_dir
        else:
            system_skill_md = _find_system_skill(name)
            if system_skill_md:
                try:
                    content = system_skill_md.read_text(encoding="utf-8")
                    return {
                        "success": True,
                        "name": name,
                        "content": content,
                        "frontmatter": _parse_frontmatter(content),
                        "path": str(system_skill_md),
                        "source": "system",
                        "usage": None,
                    }
                except (OSError, IOError):
                    pass
            return {"success": False, "error": f"Skill '{name}' not found."}

    try:
        content = skill_md.read_text(encoding="utf-8")
    except (OSError, IOError):
        return {"success": False, "error": f"Failed to read skill '{name}'."}

    bump_view(user_id, name)
    record = get_record(user_id, name)

    return {
        "success": True,
        "name": name,
        "content": content,
        "frontmatter": _parse_frontmatter(content),
        "path": str(skill_md),
        "source": "user",
        "usage": record,
    }


def update_skill(user_id: str, name: str, content: str) -> Dict[str, Any]:
    skill_dir = _get_user_skills_dir(user_id) / name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return {"success": False, "error": f"Skill '{name}' not found."}

    err = _validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}

    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(skill_dir), suffix=".tmp", prefix=".skill_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, skill_md)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        bump_patch(user_id, name)
        return {"success": True, "message": f"Skill '{name}' updated."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def patch_skill(user_id: str, name: str, old_string: str, new_string: str) -> Dict[str, Any]:
    from ..file_lock import get_lock

    skill_dir = _get_user_skills_dir(user_id) / name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return {"success": False, "error": f"Skill '{name}' not found."}

    try:
        with get_lock(f"skill_{user_id}_{name}"):
            content = skill_md.read_text(encoding="utf-8")
            if old_string not in content:
                return {"success": False, "error": f"Old string not found in skill '{name}'."}

            new_content = content.replace(old_string, new_string, 1)

            fd, tmp_path = tempfile.mkstemp(dir=str(skill_dir), suffix=".tmp", prefix=".skill_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, skill_md)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            bump_patch(user_id, name)
            return {"success": True, "message": f"Skill '{name}' patched."}
    except TimeoutError:
        return {"success": False, "error": f"Skill '{name}' is locked by another operation."}


def delete_skill(user_id: str, name: str, absorbed_into: str = None) -> Dict[str, Any]:
    skill_dir = _get_user_skills_dir(user_id) / name

    if not skill_dir.exists():
        archive_dir = _get_user_skills_dir(user_id) / ".archive" / name
        if archive_dir.exists():
            return {"success": False, "error": f"Skill '{name}' is already archived."}
        return {"success": False, "error": f"Skill '{name}' not found."}

    try:
        import shutil
        archive_dir = _get_user_skills_dir(user_id) / ".archive" / name
        archive_dir.parent.mkdir(parents=True, exist_ok=True)

        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)

        shutil.move(str(skill_dir), str(archive_dir))
        delete_record(user_id, name, absorbed_into=absorbed_into)
        msg = f"Skill '{name}' archived."
        if absorbed_into:
            msg += f" Absorbed into '{absorbed_into}'."
        return {"success": True, "message": msg, "archive_path": str(archive_dir)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_skill(user_id: str, name: str) -> Dict[str, Any]:
    archive_dir = _get_user_skills_dir(user_id) / ".archive" / name
    skill_dir = _get_user_skills_dir(user_id) / name

    if not archive_dir.exists():
        return {"success": False, "error": f"Archived skill '{name}' not found."}

    if skill_dir.exists():
        return {"success": False, "error": f"Skill '{name}' already exists in active skills."}

    try:
        import shutil
        shutil.move(str(archive_dir), str(skill_dir))
        _ensure_record(user_id, name, created_by="user")
        return {"success": True, "message": f"Skill '{name}' restored from archive."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_skills(user_id: str, category: str = None, state: str = None) -> List[Dict[str, Any]]:
    all_records = list_records(user_id, state_filter=state)
    skills = []

    for name, record in all_records.items():
        skill_dir = _get_user_skills_dir(user_id) / name
        skill_md = skill_dir / "SKILL.md"

        fm = None
        if skill_md.exists():
            try:
                content = skill_md.read_text(encoding="utf-8")
                fm = _parse_frontmatter(content)
            except (OSError, IOError):
                pass

        if category and fm and fm.get("category") != category:
            continue

        skills.append({
            "name": name,
            "frontmatter": fm,
            "exists": skill_md.exists() or (_get_user_skills_dir(user_id) / ".archive" / name / "SKILL.md").exists(),
            "source": "user",
            "usage": record,
        })

    if state is None or state == "active":
        system_dir = _get_system_skills_dir()
        if system_dir.exists():
            for name in os.listdir(system_dir):
                skill_dir = system_dir / name
                if os.path.isdir(skill_dir):
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        try:
                            content = skill_md.read_text(encoding="utf-8")
                            fm = _parse_frontmatter(content)
                            if category and fm.get("category") != category:
                                continue
                            skills.append({
                                "name": name,
                                "frontmatter": fm,
                                "exists": True,
                                "source": "system",
                                "usage": None,
                            })
                        except (OSError, IOError):
                            pass

    return skills


def get_categories(user_id: str) -> List[str]:
    categories = set()
    all_records = list_records(user_id)
    for name in all_records:
        skill_md = _get_user_skills_dir(user_id) / name / "SKILL.md"
        if skill_md.exists():
            try:
                content = skill_md.read_text(encoding="utf-8")
                fm = _parse_frontmatter(content)
                if fm and "category" in fm:
                    categories.add(fm["category"])
            except (OSError, IOError):
                pass
    return sorted(categories)


def _validate_skill_file_path(skill_dir: Path, file_path: str, allowed_dirs: set) -> tuple[bool, str]:
    """校验 skill 文件路径安全，返回 (是否有效, 错误消息)。"""
    if not file_path:
        return False, "file_path is required."

    # 统一用斜杠拆分，防止 Windows 分隔符绕过
    parts = file_path.replace("\\", "/").split("/")

    # 至少需要一级目录 + 文件名
    if len(parts) < 2:
        return False, f"file_path must be under one of: {', '.join(allowed_dirs)}"

    # 顶级目录必须在白名单中
    if parts[0] not in allowed_dirs:
        return False, f"file_path must be under one of: {', '.join(allowed_dirs)}"

    # 每一级都不能是空串或相对路径符
    for part in parts:
        if part == "" or part == "." or part == "..":
            return False, "file_path cannot contain empty segments, '.', or '..'."

    # 最终路径必须落在 skill_dir 下
    target = (skill_dir / file_path).resolve()
    skill_dir_real = skill_dir.resolve()
    try:
        target.relative_to(skill_dir_real)
    except ValueError:
        return False, "file_path escapes the skill directory."

    # 还要确保不跳出允许的子目录（例如 scripts/.. 形式已经被 parts 检查拦截）
    parent_dir = parts[0]
    allowed_parent = (skill_dir_real / parent_dir)
    try:
        target.relative_to(allowed_parent)
    except ValueError:
        return False, f"file_path must be under '{parent_dir}/'."

    return True, ""


def write_skill_file(user_id: str, skill_name: str, file_path: str, content: str) -> Dict[str, Any]:
    skill_dir = _get_user_skills_dir(user_id) / skill_name
    if not skill_dir.exists():
        return {"success": False, "error": f"Skill '{skill_name}' not found."}

    allowed_dirs = {"references", "templates", "scripts"}
    valid, err = _validate_skill_file_path(skill_dir, file_path, allowed_dirs)
    if not valid:
        return {"success": False, "error": err}

    target = (skill_dir / file_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp", prefix=".sf_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return {"success": True, "message": f"File '{file_path}' written to skill '{skill_name}'."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_skill_file(user_id: str, skill_name: str, file_path: str) -> Dict[str, Any]:
    skill_dir = _get_user_skills_dir(user_id) / skill_name
    if not skill_dir.exists():
        return {"success": False, "error": f"Skill '{skill_name}' not found."}

    allowed_dirs = {"references", "templates", "scripts"}
    valid, err = _validate_skill_file_path(skill_dir, file_path, allowed_dirs)
    if not valid:
        return {"success": False, "error": err}

    target = (skill_dir / file_path).resolve()
    if not target.exists():
        return {"success": False, "error": f"File '{file_path}' not found in skill '{skill_name}'."}

    try:
        target.unlink()
        return {"success": True, "message": f"File '{file_path}' removed from skill '{skill_name}'."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_skill_files(user_id: str, skill_name: str) -> Dict[str, Any]:
    skill_dir = _get_user_skills_dir(user_id) / skill_name
    if not skill_dir.exists():
        return {"success": False, "error": f"Skill '{skill_name}' not found."}

    files = {"references": [], "templates": [], "scripts": []}
    for subdir in files:
        sub_path = skill_dir / subdir
        if sub_path.exists():
            for f in sorted(sub_path.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    files[subdir].append(f.name)

    return {"success": True, "skill": skill_name, "files": files}
