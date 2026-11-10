"""日统计的纯计算逻辑：时区日界切分与会话推断时长（B 批最小版）。

口径与 ``packages/contracts/analytics/statistics-api.md``「时长口径」一致：
``session_inference_v1``——相邻事件间隔 ≤15 分钟视为同一会话；
会话时长 = 首末事件间隔，下限 60 秒、上限 3600 秒；按 IANA 时区日历日切分。

迟到事件不按到账顺序累加：消费侧对受影响的 (学生, 课程, 班级, 日) 键
**整体重算**，本模块只提供无状态函数，供 ``pg_consumer`` 在事务内调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SESSION_GAP = timedelta(minutes=15)
SESSION_MIN_SECONDS = 60
SESSION_MAX_SECONDS = 3600


@dataclass(frozen=True)
class DailyKey:
    """一条日统计行的自然键（对应 analytics_daily_metrics 的唯一约束列）。"""

    student_user_id: str
    course_id: str | None
    class_id: str | None
    metric_date: date


def local_metric_date(occurred_at: datetime, tz: ZoneInfo) -> date:
    """事件发生时刻在指定时区日历下所处的本地日。"""
    return occurred_at.astimezone(tz).date()


def key_for_event(
    *,
    student_user_id: str,
    course_id: str | None,
    class_id: str | None,
    occurred_at: datetime,
    tz: ZoneInfo,
) -> DailyKey:
    """由一条事件推导它归属的日统计键。"""
    return DailyKey(
        student_user_id=student_user_id,
        course_id=course_id,
        class_id=class_id,
        metric_date=local_metric_date(occurred_at, tz),
    )


def infer_daily_seconds(occurred_ats: list[datetime]) -> int | None:
    """按 session_inference_v1 推断一天内的学习秒数。

    输入须为同一 (学生, 课程, 班级, 日) 键下的事件时刻；内部按升序处理，
    乱序输入也被接受（迟到事件重算场景）。无输入返回 ``None``
    （调用方据此不落行——无观测是 unknown，不是 0）。
    """
    if not occurred_ats:
        return None
    ordered = sorted(occurred_ats)
    total = 0
    session_start = ordered[0]
    session_end = ordered[0]
    for current in ordered[1:]:
        if current - session_end <= SESSION_GAP:
            session_end = current
            continue
        total += _session_seconds(session_start, session_end)
        session_start = current
        session_end = current
    total += _session_seconds(session_start, session_end)
    return total


def _session_seconds(start: datetime, end: datetime) -> int:
    seconds = int((end - start).total_seconds())
    return max(SESSION_MIN_SECONDS, min(SESSION_MAX_SECONDS, seconds))
