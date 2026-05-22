import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from server.workspace import _get_workspace_dir

logger = logging.getLogger(__name__)

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"

DEFAULT_STALE_AFTER_DAYS = 30
DEFAULT_ARCHIVE_AFTER_DAYS = 90

_lock = threading.Lock()


def _get_user_kb_dir(user_id: str) -> str:
    base = _get_workspace_dir(user_id)
    kb_dir = os.path.join(base, 'data', 'kb')
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


def _get_user_skills_dir(user_id: str) -> Path:
    return Path(_get_user_kb_dir(user_id)) / 'skills'


def _usage_file(user_id: str) -> Path:
    return _get_user_skills_dir(user_id) / '.usage.json'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _load_usage(user_id: str) -> Dict[str, Any]:
    uf = _usage_file(user_id)
    if uf.exists():
        try:
            return json.loads(uf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_usage(user_id: str, data: Dict[str, Any]):
    skills_dir = _get_user_skills_dir(user_id)
    skills_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(skills_dir), suffix=".tmp", prefix=".usage_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, _usage_file(user_id))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _ensure_record(user_id: str, skill_name: str, created_by: str = "user") -> Dict[str, Any]:
    data = _load_usage(user_id)
    if skill_name not in data:
        now = _now_iso()
        data[skill_name] = {
            "created_by": created_by,
            "use_count": 0,
            "view_count": 0,
            "patch_count": 0,
            "last_used_at": None,
            "last_viewed_at": None,
            "last_patched_at": None,
            "created_at": now,
            "state": STATE_ACTIVE,
            "pinned": False,
            "archived_at": None,
        }
        _save_usage(user_id, data)
    return data[skill_name]


def get_record(user_id: str, skill_name: str) -> Optional[Dict[str, Any]]:
    data = _load_usage(user_id)
    return data.get(skill_name)


def list_records(user_id: str, state_filter: str = None, created_by_filter: str = None) -> Dict[str, Dict[str, Any]]:
    data = _load_usage(user_id)
    result = {}
    for name, record in data.items():
        if state_filter and record.get("state") != state_filter:
            continue
        if created_by_filter and record.get("created_by") != created_by_filter:
            continue
        result[name] = record
    return result


def bump_use(user_id: str, skill_name: str):
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return
        record = data[skill_name]
        record["use_count"] = record.get("use_count", 0) + 1
        record["last_used_at"] = _now_iso()
        _save_usage(user_id, data)


def bump_view(user_id: str, skill_name: str):
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return
        record = data[skill_name]
        record["view_count"] = record.get("view_count", 0) + 1
        record["last_viewed_at"] = _now_iso()
        _save_usage(user_id, data)


def bump_patch(user_id: str, skill_name: str):
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return
        record = data[skill_name]
        record["patch_count"] = record.get("patch_count", 0) + 1
        record["last_patched_at"] = _now_iso()
        _save_usage(user_id, data)


def _latest_activity_at(record: Dict) -> Optional[str]:
    latest_dt = None
    latest_raw = None
    for key in ("last_used_at", "last_viewed_at", "last_patched_at"):
        raw = record.get(key)
        dt = _parse_iso(raw)
        if dt and (latest_dt is None or dt > latest_dt):
            latest_dt = dt
            latest_raw = raw
    return latest_raw


def _activity_count(record: Dict) -> int:
    return sum(int(record.get(k) or 0) for k in ("use_count", "view_count", "patch_count"))


def mark_stale(user_id: str, skill_name: str) -> Tuple[bool, str]:
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return False, "Skill not found."
        record = data[skill_name]
        if record.get("state") == STATE_STALE:
            return True, "Already stale."
        record["state"] = STATE_STALE
        _save_usage(user_id, data)
        return True, f"Skill '{skill_name}' marked as stale."


def archive_skill(user_id: str, skill_name: str) -> Tuple[bool, str]:
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return False, "Skill not found."
        record = data[skill_name]
        if record.get("state") == STATE_ARCHIVED:
            return True, "Already archived."
        record["state"] = STATE_ARCHIVED
        record["archived_at"] = _now_iso()
        _save_usage(user_id, data)

        skill_dir = _get_user_skills_dir(user_id) / skill_name
        archive_dir = _get_user_skills_dir(user_id) / ".archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        if skill_dir.exists():
            dest = archive_dir / skill_name
            if dest.exists():
                import shutil
                shutil.rmtree(dest, ignore_errors=True)
            try:
                skill_dir.rename(dest)
            except OSError as e:
                logger.warning("Failed to move skill dir: %s", e)

        return True, f"Skill '{skill_name}' archived."


def restore_skill(user_id: str, skill_name: str) -> Tuple[bool, str]:
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return False, "Skill not found."
        record = data[skill_name]
        record["state"] = STATE_ACTIVE
        record["archived_at"] = None
        _save_usage(user_id, data)

        archive_dir = _get_user_skills_dir(user_id) / ".archive"
        skill_dir = _get_user_skills_dir(user_id) / skill_name
        archived_dir = archive_dir / skill_name

        if archived_dir.exists() and not skill_dir.exists():
            try:
                archived_dir.rename(skill_dir)
            except OSError as e:
                logger.warning("Failed to restore skill dir: %s", e)

        return True, f"Skill '{skill_name}' restored."


def lifecycle_check(user_id: str, skill_name: str, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
                    archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS) -> str:
    record = get_record(user_id, skill_name)
    if not record:
        return "not_found"

    if record.get("pinned") or record.get("state") == STATE_ARCHIVED:
        return record.get("state", STATE_ACTIVE)

    last_activity = _latest_activity_at(record)
    if not last_activity:
        last_activity = record.get("created_at")

    last_dt = _parse_iso(last_activity)
    if not last_dt:
        return STATE_ACTIVE

    now = datetime.now(timezone.utc)
    days_inactive = (now - last_dt).days

    if days_inactive > archive_after_days:
        archive_skill(user_id, skill_name)
        return STATE_ARCHIVED
    elif days_inactive > stale_after_days:
        if record.get("state") != STATE_STALE:
            mark_stale(user_id, skill_name)
        return STATE_STALE
    else:
        if record.get("state") == STATE_STALE:
            with _lock:
                data = _load_usage(user_id)
                if skill_name in data:
                    data[skill_name]["state"] = STATE_ACTIVE
                    _save_usage(user_id, data)
        return STATE_ACTIVE


def delete_record(user_id: str, skill_name: str, absorbed_into: str = None):
    with _lock:
        data = _load_usage(user_id)
        if skill_name in data:
            if absorbed_into:
                if absorbed_into not in data:
                    _ensure_record(user_id, absorbed_into)
                target = data[absorbed_into]
                source = data[skill_name]
                target["use_count"] = target.get("use_count", 0) + source.get("use_count", 0)
                target["view_count"] = target.get("view_count", 0) + source.get("view_count", 0)
                target["patch_count"] = target.get("patch_count", 0) + source.get("patch_count", 0)

                src_last = _latest_activity_at(source)
                tgt_last = _latest_activity_at(target)
                if src_last:
                    src_dt = _parse_iso(src_last)
                    tgt_dt = _parse_iso(tgt_last)
                    if src_dt and (not tgt_dt or src_dt > tgt_dt):
                        target["last_used_at"] = source.get("last_used_at")
                        target["last_viewed_at"] = source.get("last_viewed_at")
                        target["last_patched_at"] = source.get("last_patched_at")

                target["absorbed"] = target.get("absorbed", []) + [skill_name]
            del data[skill_name]
            _save_usage(user_id, data)


def pin_skill(user_id: str, skill_name: str) -> Tuple[bool, str]:
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return False, "Skill not found."
        data[skill_name]["pinned"] = True
        _save_usage(user_id, data)
        return True, f"Skill '{skill_name}' pinned."


def unpin_skill(user_id: str, skill_name: str) -> Tuple[bool, str]:
    with _lock:
        data = _load_usage(user_id)
        if skill_name not in data:
            return False, "Skill not found."
        data[skill_name]["pinned"] = False
        _save_usage(user_id, data)
        return True, f"Skill '{skill_name}' unpinned."
