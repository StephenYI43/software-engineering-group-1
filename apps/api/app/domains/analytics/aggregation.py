"""读侧聚合：把聚合状态换算成交付给 M2 的指标。

算法参数集中在本模块顶部，改动必须同步
`packages/contracts/analytics/statistics-api.md`「聚合口径」。
所有函数都是纯读取，不修改状态。

所有查询都带 `course_id` 过滤：状态里的每条记录都记录了归属课程，
只统计 `record.course_id == course_id` 的记录，同一学生跨班时数据互不串班；
`courseId` 为 None 的事件因不等于任何具体课程 ID，永远不进任何班级。
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domains.analytics.period import Period
from app.domains.analytics.state import AnalyticsState

SESSION_GAP_THRESHOLD = timedelta(minutes=15)
"""相邻事件间隔不超过该值视为同一学习会话。"""

SESSION_MIN_SECONDS = 60
"""单个会话的最低计时长（单事件会话按此计）。"""

SESSION_MAX_SECONDS = 3600
"""单个会话的时长上限，防止长间隔挂机虚增。"""

MIN_SAMPLE_SIZE = 5
"""薄弱点样本量下限；低于此值的条目必须标注样本不足。"""

ALGORITHM_SESSION_INFERENCE = "session_inference_v1"
"""时长算法标识：会话推断（过渡口径，待 M4 专注计时事件就绪后切换）。"""

UNKNOWN_KEY = "unknown"
"""题型或章节缺失时的归集键。"""


@dataclass(frozen=True)
class QuestionTypeWeakPoint:
    key: str
    error_rate: float
    sample_size: int
    insufficient_sample: bool


@dataclass(frozen=True)
class ChapterWeakPoint:
    key: str
    mistake_count: int
    resolved_count: int
    sample_size: int
    insufficient_sample: bool


def has_activity_in_period(
    state: AnalyticsState, user_id: str, period: Period, course_id: str
) -> bool:
    """该生在周期内是否有任何本课程事件。无事件 = 未知，不能用 0 代替。"""
    moments = state.activity.get(user_id, {}).get(course_id, ())
    return any(period.contains(moment) for moment in moments)


def duration_seconds(
    state: AnalyticsState, user_id: str, period: Period, course_id: str
) -> int | None:
    """该生周期内本课程学习时长（秒）；周期内无事件返回 None。"""
    times = [
        moment
        for moment in state.activity.get(user_id, {}).get(course_id, ())
        if period.contains(moment)
    ]
    if not times:
        return None
    return session_seconds(times, period.timezone)


def submission_count(state: AnalyticsState, user_id: str, period: Period, course_id: str) -> int:
    """该生周期内本课程提交数（按 `submissionId` 去重）。

    计数永远是已知数字：没有可归属的提交就是 0，不用 unknown
    （statistics-api.md 契约修订「计数 known 0」）。
    """
    return sum(
        1
        for record in state.submissions.values()
        if record.user_id == user_id
        and record.course_id == course_id
        and period.contains(record.occurred_at)
    )


def session_seconds(times: Sequence[datetime], timezone: ZoneInfo) -> int:
    """按查询时区切「日」，再在每日内做会话推断。

    跨日会话按两段分别计（契约已写明日界按 `timezone` 确定）。
    """
    buckets: dict[date, list[datetime]] = {}
    for moment in times:
        buckets.setdefault(moment.astimezone(timezone).date(), []).append(moment)
    return sum(_day_session_seconds(sorted(bucket)) for bucket in buckets.values())


def question_type_weak_points(
    state: AnalyticsState, period: Period, user_ids: Collection[str], course_id: str
) -> list[QuestionTypeWeakPoint]:
    """题型错误率：只统计已判分的提交，未判分（isCorrect 为 null）不入分母。"""
    counts: dict[str, list[int]] = {}
    for judgement in state.judgements.values():
        if (
            judgement.course_id != course_id
            or judgement.user_id not in user_ids
            or not period.contains(judgement.occurred_at)
        ):
            continue
        bucket = counts.setdefault(judgement.question_type or UNKNOWN_KEY, [0, 0])
        bucket[1] += 1
        if not judgement.is_correct:
            bucket[0] += 1

    items = [
        QuestionTypeWeakPoint(
            key=key,
            error_rate=wrong / total,
            sample_size=total,
            insufficient_sample=total < MIN_SAMPLE_SIZE,
        )
        for key, (wrong, total) in counts.items()
    ]
    return sorted(
        items,
        key=lambda item: (item.insufficient_sample, -item.sample_size, -item.error_rate, item.key),
    )


def chapter_weak_points(
    state: AnalyticsState, period: Period, user_ids: Collection[str], course_id: str
) -> list[ChapterWeakPoint]:
    """章节错题：本周期无错题的章节不出现（不返回 0 行）。"""
    counts: dict[str, list[int]] = {}
    for mistake in state.mistakes.values():
        if (
            mistake.course_id != course_id
            or mistake.user_id not in user_ids
            or not period.contains(mistake.recorded_at)
        ):
            continue
        bucket = counts.setdefault(mistake.chapter_id or UNKNOWN_KEY, [0, 0])
        bucket[0] += 1
        if mistake.resolved:
            bucket[1] += 1

    items = [
        ChapterWeakPoint(
            key=key,
            mistake_count=total,
            resolved_count=resolved,
            sample_size=total,
            insufficient_sample=total < MIN_SAMPLE_SIZE,
        )
        for key, (total, resolved) in counts.items()
    ]
    return sorted(
        items,
        key=lambda item: (
            item.insufficient_sample,
            -item.sample_size,
            -item.mistake_count,
            item.key,
        ),
    )


def weakest_chapter(
    state: AnalyticsState, user_id: str, period: Period, course_id: str
) -> ChapterWeakPoint | None:
    """该生本课程内错题最多的章节；本周期无错题返回 None（已知事实，不是未知）。"""
    items = chapter_weak_points(state, period, {user_id}, course_id)
    if not items:
        return None
    return sorted(items, key=lambda item: (-item.mistake_count, item.key))[0]


def _day_session_seconds(times: Sequence[datetime]) -> int:
    """单个自然日内的会话时长合计。`times` 必须已升序。"""
    total = 0
    session_start = times[0]
    previous = times[0]
    for moment in times[1:]:
        if moment - previous > SESSION_GAP_THRESHOLD:
            total += _clamp_seconds(previous - session_start)
            session_start = moment
        previous = moment
    return total + _clamp_seconds(previous - session_start)


def _clamp_seconds(span: timedelta) -> int:
    seconds = int(span.total_seconds())
    return min(max(seconds, SESSION_MIN_SECONDS), SESSION_MAX_SECONDS)
