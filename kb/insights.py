import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .session_db import get_session_db
from .skills.usage import list_records
from .memory import get_memory_store

logger = logging.getLogger(__name__)


class InsightsEngine:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = get_session_db(user_id)

    def generate(self, days: int = 30) -> Dict[str, Any]:
        cutoff = time.time() - (days * 86400)

        sessions = self._get_sessions(cutoff)
        message_stats = self._get_message_stats(cutoff)
        tool_usage = self._get_tool_usage(cutoff)

        if not sessions:
            return {
                "days": days,
                "empty": True,
                "overview": {},
                "tool_breakdown": [],
                "skill_breakdown": [],
                "activity": {},
                "top_sessions": [],
                "memory_usage": {},
            }

        overview = self._compute_overview(sessions, message_stats)
        tool_breakdown = self._compute_tool_breakdown(tool_usage)
        skill_breakdown = self._compute_skill_breakdown()
        activity = self._compute_activity_patterns(sessions)
        top_sessions = self._compute_top_sessions(sessions)
        memory_usage = self._compute_memory_usage()

        return {
            "days": days,
            "empty": False,
            "generated_at": time.time(),
            "overview": overview,
            "tool_breakdown": tool_breakdown,
            "skill_breakdown": skill_breakdown,
            "activity": activity,
            "top_sessions": top_sessions,
            "memory_usage": memory_usage,
        }

    def _get_sessions(self, cutoff: float) -> List[Dict]:
        with self.db._lock:
            cursor = self.db._conn.execute(
                "SELECT id, user_id, model, title, started_at, ended_at, "
                "message_count, token_count FROM sessions "
                "WHERE started_at >= ? ORDER BY started_at DESC",
                (cutoff,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def _get_message_stats(self, cutoff: float) -> Dict:
        with self.db._lock:
            cursor = self.db._conn.execute(
                """SELECT
                     COUNT(*) as total_messages,
                     SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) as user_messages,
                     SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages,
                     SUM(CASE WHEN m.role = 'tool' THEN 1 ELSE 0 END) as tool_messages
                   FROM messages m
                   JOIN sessions s ON s.id = m.session_id
                   WHERE s.started_at >= ?""",
                (cutoff,),
            )
            row = cursor.fetchone()
            return dict(row) if row else {
                "total_messages": 0, "user_messages": 0,
                "assistant_messages": 0, "tool_messages": 0,
            }

    def _get_tool_usage(self, cutoff: float) -> List[Dict]:
        tool_counts = Counter()

        with self.db._lock:
            cursor = self.db._conn.execute(
                """SELECT m.tool_name, COUNT(*) as count
                   FROM messages m
                   JOIN sessions s ON s.id = m.session_id
                   WHERE s.started_at >= ?
                     AND m.role = 'tool' AND m.tool_name IS NOT NULL
                   GROUP BY m.tool_name
                   ORDER BY count DESC""",
                (cutoff,),
            )
            for row in cursor.fetchall():
                tool_counts[row["tool_name"]] += row["count"]

        return [
            {"tool_name": name, "count": count}
            for name, count in tool_counts.most_common()
        ]

    def _compute_overview(self, sessions: List[Dict], message_stats: Dict) -> Dict:
        total_messages = sum(s.get("message_count", 0) or 0 for s in sessions)
        total_tokens = sum(s.get("token_count", 0) or 0 for s in sessions)

        durations = []
        for s in sessions:
            start = s.get("started_at")
            end = s.get("ended_at")
            if start and end and end > start:
                durations.append(end - start)

        total_hours = sum(durations) / 3600 if durations else 0
        avg_duration = sum(durations) / len(durations) if durations else 0

        started_timestamps = [s["started_at"] for s in sessions if s.get("started_at")]
        date_range_start = min(started_timestamps) if started_timestamps else None
        date_range_end = max(started_timestamps) if started_timestamps else None

        return {
            "total_sessions": len(sessions),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "total_hours": round(total_hours, 2),
            "avg_session_duration": round(avg_duration, 1),
            "avg_messages_per_session": round(total_messages / len(sessions), 1) if sessions else 0,
            "user_messages": message_stats.get("user_messages") or 0,
            "assistant_messages": message_stats.get("assistant_messages") or 0,
            "tool_messages": message_stats.get("tool_messages") or 0,
            "date_range_start": date_range_start,
            "date_range_end": date_range_end,
        }

    def _compute_tool_breakdown(self, tool_usage: List[Dict]) -> List[Dict]:
        return tool_usage

    def _compute_skill_breakdown(self) -> List[Dict]:
        records = list_records(self.user_id)
        skill_stats = []
        for name, record in records.items():
            skill_stats.append({
                "name": name,
                "state": record.get("state", "active"),
                "created_by": record.get("created_by", "user"),
                "use_count": record.get("use_count", 0),
                "view_count": record.get("view_count", 0),
                "patch_count": record.get("patch_count", 0),
                "pinned": record.get("pinned", False),
            })

        skill_stats.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        return skill_stats[:20]

    def _compute_activity_patterns(self, sessions: List[Dict]) -> Dict:
        daily = Counter()
        hourly = Counter()
        weekday = Counter()

        for s in sessions:
            ts = s.get("started_at")
            if not ts:
                continue
            try:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                daily[dt.strftime("%Y-%m-%d")] += 1
                hourly[dt.hour] += 1
                weekday[dt.strftime("%A")] += 1
            except (ValueError, OSError):
                continue

        return {
            "daily": dict(sorted(daily.items())),
            "hourly": {str(h): hourly.get(h, 0) for h in range(24)},
            "weekday": dict(weekday),
            "peak_hour": hourly.most_common(1)[0][0] if hourly else None,
            "peak_day": weekday.most_common(1)[0][0] if weekday else None,
        }

    def _compute_top_sessions(self, sessions: List[Dict]) -> List[Dict]:
        sorted_sessions = sorted(
            sessions,
            key=lambda s: s.get("message_count", 0) or 0,
            reverse=True,
        )
        top = sorted_sessions[:10]
        return [
            {
                "id": s.get("id"),
                "title": s.get("title", "(untitled)"),
                "message_count": s.get("message_count", 0),
                "started_at": s.get("started_at"),
                "duration": round(s.get("ended_at", 0) - s.get("started_at", 0), 1)
                    if s.get("ended_at") and s.get("started_at") and s["ended_at"] > s["started_at"]
                    else None,
            }
            for s in top
        ]

    def _compute_memory_usage(self) -> Dict:
        try:
            store = get_memory_store(self.user_id)
            return store.get_usage_info()
        except Exception:
            return {}
