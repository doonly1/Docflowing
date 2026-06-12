import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .usage import (
    list_records,
    get_record,
    _latest_activity_at,
    _parse_iso,
    _now_iso,
    lifecycle_check,
    archive_skill,
    mark_stale,
    _get_user_skills_dir,
    STATE_ACTIVE,
    STATE_STALE,
    STATE_ARCHIVED,
)
from .manager import list_skills, get_skill

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 168
DEFAULT_MIN_IDLE_HOURS = 2
DEFAULT_STALE_AFTER_DAYS = 30
DEFAULT_ARCHIVE_AFTER_DAYS = 90

_CURATOR_REVIEW_PROMPT = """你正在运行知识库的技能审查器（Curator）。这是一次伞形整合审查，不是被动审计，也不是简单去重。

技能库的目标是**类级别的指令和经验知识集合**。数百个每个只记录一次会话特定 bug 的窄技能是库的失败——不是特性。代理搜索技能时按描述匹配，不是按精确名称；一个带有标记子节的宽泛伞形技能比五个窄兄弟技能更易发现。

正确的目标形态是**类级别技能**，包含丰富的 SKILL.md 主体 + `references/`、`templates/`、`scripts/` 子文件——而不是一个会话一个技能的微条目。

硬性规则——不可违反：
1. 不要触碰用户手动创建的技能。下面的候选列表已过滤为仅代理创建的技能。
2. 不要删除任何技能。归档（将技能目录移入 .archive/）是最大破坏性操作。归档可恢复；删除不可恢复。
3. 不要触碰标记为 pinned=yes 的技能。完全跳过。
4. 不要以使用计数为零作为跳过整合的理由。计数是新的且通常为零。按内容判断重叠。
5. 不要以"每个技能有不同触发条件"为由拒绝整合。两两不同是错误的标准。正确的标准是："人类维护者会将其写为 N 个独立技能，还是一个带 N 个标记子节的技能？"当答案是后者时，合并。

工作方式——必须遵守：
1. 扫描完整候选列表。识别前缀集群（共享首词或领域关键词的技能）。
2. 对于每个有 2+ 成员的集群，不要问"这些是否重叠？"——问"这些技能共同服务的伞形类是什么？维护者会命名该类并为它写一个技能吗？"如果是，选择（或创建）伞形并将兄弟技能吸收进去。
3. 三种整合方式——每个集群选择正确的：
   a. 合并到现有伞形——集群中一个技能已足够宽泛作为伞形。修补它以添加每个兄弟独特见解的标记子节，然后归档兄弟。
   b. 创建新伞形 SKILL.md——没有现有成员足够宽泛。使用 skill_manage action=create 写一个新的类级别技能，其 SKILL.md 涵盖共享工作流并有短标记子节。归档已吸收的窄兄弟。
   c. 降级为 references/templates/scripts——兄弟有窄但有价值的会话特定内容。将其移入伞形的适当支持目录。
4. 还要标记名称太窄的技能（包含特定错误字符串、会话工件）。这些几乎总是应作为类级别伞形的子节或支持文件。
5. 迭代。在一轮整合后，扫描剩余集合寻找下一个伞形机会。

你的工具集：
  - skill_manage action=list — 读取当前技能列表
  - skill_manage action=view — 查看特定技能内容
  - skill_manage action=patch — 向伞形添加子节
  - skill_manage action=create — 创建新伞形 SKILL.md

'keep' 只有在技能已经是类级别伞形且没有建议的合并会改善可发现性时才是合法决策。

完成后，写一个人类摘要和一个结构化机器可读块。格式：

## 结构化摘要（必需）
```yaml
consolidations:
  - from: <旧技能名>
    into: <伞形技能名>
    reason: <一句话——为什么合并>
prunings:
  - name: <技能名>
    reason: <一句话——为什么归档无合并目标>
```"""

_CURATOR_DRY_RUN_BANNER = """
═══════════════════════════════════════════════════════════════
DRY-RUN — 仅报告模式。不要修改技能库。
═══════════════════════════════════════════════════════════════

这是预览模式。遵循以下指令，但：

  • 不要调用 skill_manage 执行 patch、create 操作。
  • 只描述你将要采取的行动，而不是已采取的行动。
  • skill_manage action=list 和 action=view 可以使用——尽情阅读。

你的输出就是交付物。生成与实时运行相同的摘要和结构化 YAML 块——但描述你将要采取的行动。
═══════════════════════════════════════════════════════════════
"""


def _curator_state_file(user_id: str):
    return _get_user_skills_dir(user_id) / ".curator_state.json"


def _load_curator_state(user_id: str) -> Dict[str, Any]:
    sf = _curator_state_file(user_id)
    if sf.exists():
        try:
            return json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_curator_state(user_id: str, state: Dict[str, Any]):
    sf = _curator_state_file(user_id)
    sf.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(sf.parent), suffix=".tmp", prefix=".curator_state_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, sf)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _reports_dir(user_id: str) -> Path:
    from server.workspace import _get_workspace_dir
    base = _get_workspace_dir(user_id)
    d = Path(base) / "data" / "kb" / "data" / "curator_reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def should_run(
    user_id: str,
    now: Optional[datetime] = None,
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
    min_idle_hours: int = DEFAULT_MIN_IDLE_HOURS,
) -> bool:
    state = _load_curator_state(user_id)
    last_run_raw = state.get("last_run_at")
    last_run = _parse_iso(last_run_raw)

    if now is None:
        now = datetime.now(timezone.utc)

    if last_run:
        elapsed = (now - last_run).total_seconds()
        if elapsed < interval_hours * 3600:
            return False

    return True


def run_review(
    user_id: str,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    agent_created = list_records(user_id, created_by_filter="agent")
    report: Dict[str, Any] = {
        "success": True,
        "timestamp": now.isoformat(),
        "total_skills_reviewed": 0,
        "transitions": [],
        "stale_count": 0,
        "archived_count": 0,
        "active_count": 0,
        "recommendations": [],
    }

    for skill_name, record in agent_created.items():
        if record.get("pinned"):
            report["active_count"] += 1
            continue

        report["total_skills_reviewed"] += 1
        state = lifecycle_check(user_id, skill_name, stale_after_days=stale_after_days, archive_after_days=archive_after_days)

        if state == STATE_ARCHIVED:
            report["archived_count"] += 1
            report["transitions"].append({
                "skill": skill_name,
                "action": "archived",
                "reason": f"Inactive for {archive_after_days}+ days",
            })
        elif state == STATE_STALE:
            report["stale_count"] += 1
            report["transitions"].append({
                "skill": skill_name,
                "action": "marked_stale",
                "reason": f"Inactive for {stale_after_days}+ days",
            })
            report["recommendations"].append({
                "skill": skill_name,
                "type": "review_or_archive",
                "message": f"Skill '{skill_name}' is stale. Consider updating or archiving.",
            })
        else:
            report["active_count"] += 1

    all_skills = list_skills(user_id)
    for skill_info in all_skills:
        name = skill_info["name"]
        usage = skill_info.get("usage", {})

        if usage and usage.get("created_by") == "agent" and usage.get("state") == STATE_ACTIVE:
            use_count = usage.get("use_count", 0)
            view_count = usage.get("view_count", 0)

            if use_count == 0 and view_count > 0:
                report["recommendations"].append({
                    "skill": name,
                    "type": "never_used",
                    "message": f"Skill '{name}' has been viewed {view_count} times but never used. Consider improving or removing it.",
                })

            if use_count > 50 and usage.get("patch_count", 0) == 0:
                report["recommendations"].append({
                    "skill": name,
                    "type": "high_use_no_patch",
                    "message": f"Skill '{name}' is heavily used ({use_count} times) but has never been patched. It may be stable and effective.",
                })

    state = _load_curator_state(user_id)
    state["last_run_at"] = _now_iso()
    state["last_review_count"] = report["total_skills_reviewed"]
    _save_curator_state(user_id, state)

    return report


def _build_curator_prompt(user_id: str, dry_run: bool = False) -> str:
    agent_created = list_records(user_id, created_by_filter="agent", state_filter=STATE_ACTIVE)
    if not agent_created:
        return ""

    skills_info = []
    for skill_name, record in agent_created.items():
        if record.get("pinned"):
            continue

        skill_data = get_skill(user_id, skill_name)
        content = ""
        if skill_data and skill_data.get("success"):
            content = skill_data.get("content", "")

        desc = record.get("description", "")
        use_count = record.get("use_count", 0)
        view_count = record.get("view_count", 0)
        patch_count = record.get("patch_count", 0)
        created_at = record.get("created_at", "")

        content_preview = content[:800] if content else "(empty)"
        if len(content) > 800:
            content_preview += "..."

        skills_info.append(
            f"### 技能: {skill_name}\n"
            f"- 描述: {desc or '(无)'}\n"
            f"- 使用次数: {use_count}, 查看次数: {view_count}, 修补次数: {patch_count}\n"
            f"- 创建时间: {created_at}\n"
            f"- 内容预览:\n{content_preview}\n"
        )

    if not skills_info:
        return ""

    prompt = _CURATOR_REVIEW_PROMPT
    if dry_run:
        prompt = _CURATOR_DRY_RUN_BANNER + "\n\n" + prompt

    prompt += f"\n\n## 候选技能列表（共 {len(skills_info)} 个）\n\n"
    prompt += "\n---\n".join(skills_info)

    return prompt


def run_llm_review(user_id: str, dry_run: bool = False) -> Dict[str, Any]:
    from ..llm import call_llm_with_tools, is_llm_available
    from ..agent_tools import ALL_TOOL_SCHEMAS, execute_tool_call

    now = datetime.now(timezone.utc)
    report: Dict[str, Any] = {
        "success": True,
        "timestamp": now.isoformat(),
        "dry_run": dry_run,
        "review_type": "llm",
        "skills_reviewed": 0,
        "tool_calls_made": [],
        "summary": "",
    }

    if not is_llm_available(user_id):
        report["success"] = False
        report["error"] = "LLM 不可用，无法执行审查"
        return report

    prompt = _build_curator_prompt(user_id, dry_run=dry_run)
    if not prompt:
        report["summary"] = "没有需要审查的代理创建技能"
        return report

    agent_created = list_records(user_id, created_by_filter="agent", state_filter=STATE_ACTIVE)
    report["skills_reviewed"] = len([n for n, r in agent_created.items() if not r.get("pinned")])

    if dry_run:
        from ..llm import call_llm
        summary = call_llm(
            system_prompt=prompt,
            user_query="请审查以上技能列表，输出你的整合建议和结构化摘要。",
            temperature=0.3,
            max_tokens=4000,
            user_id=user_id,
        )
        report["summary"] = summary or ""
    else:
        def _tool_exec(name, args):
            return execute_tool_call(name, args, user_id)

        result = call_llm_with_tools(
            system_prompt=prompt,
            user_query="请审查以上技能列表，执行必要的整合操作，并输出结构化摘要。",
            tools=ALL_TOOL_SCHEMAS,
            max_tool_rounds=10,
            tool_executor=_tool_exec,
            temperature=0.3,
            max_tokens=4000,
            user_id=user_id,
        )
        report["summary"] = result.get("content", "")
        report["tool_calls_made"] = [
            {"name": tc.get("name"), "arguments": tc.get("arguments")}
            for tc in result.get("tool_calls_made", [])
        ]

    report_path = _save_review_report(user_id, report)
    report["report_path"] = str(report_path)

    state = _load_curator_state(user_id)
    state["last_run_at"] = _now_iso()
    state["last_llm_review"] = report["timestamp"]
    state["last_report_path"] = str(report_path)
    _save_curator_state(user_id, state)

    return report


def _save_review_report(user_id: str, report: Dict[str, Any]) -> str:
    reports_d = _reports_dir(user_id)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{ts}.json"
    filepath = reports_d / filename

    fd, tmp_path = tempfile.mkstemp(dir=str(reports_d), suffix=".tmp", prefix=f".report_{ts}_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return str(filepath)


def list_review_reports(user_id: str) -> List[Dict[str, Any]]:
    reports_d = _reports_dir(user_id)
    reports = []
    for f in sorted(reports_d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "id": f.stem,
                "timestamp": data.get("timestamp"),
                "dry_run": data.get("dry_run", False),
                "review_type": data.get("review_type", "unknown"),
                "skills_reviewed": data.get("skills_reviewed", 0),
                "tool_calls_count": len(data.get("tool_calls_made", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return reports


def get_review_report(user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    reports_d = _reports_dir(user_id)
    filepath = reports_d / f"{report_id}.json"
    if not filepath.exists():
        return None
    try:
        return json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def get_curator_status(user_id: str) -> Dict[str, Any]:
    state = _load_curator_state(user_id)

    all_records = list_records(user_id)
    counts = {STATE_ACTIVE: 0, STATE_STALE: 0, STATE_ARCHIVED: 0}
    for name, record in all_records.items():
        s = record.get("state", STATE_ACTIVE)
        if s in counts:
            counts[s] += 1

    return {
        "last_run_at": state.get("last_run_at"),
        "last_review_count": state.get("last_review_count", 0),
        "last_llm_review": state.get("last_llm_review"),
        "last_report_path": state.get("last_report_path"),
        "total_skills": len(all_records),
        "active": counts[STATE_ACTIVE],
        "stale": counts[STATE_STALE],
        "archived": counts[STATE_ARCHIVED],
    }
