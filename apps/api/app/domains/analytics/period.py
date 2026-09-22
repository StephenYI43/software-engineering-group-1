"""统计周期解析。

`last7d` / `last30d` 以查询时区下生成时刻所处日的 00:00 为终点（不含今天），
按本地日历日向前取 7 / 30 个自然日，区间左闭右开。日界时区必须显式确定，
因为「学生 × 日」是聚合维度。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domains.analytics.errors import InvalidQueryError

PERIOD_LAST_7_DAYS = "last7d"
PERIOD_LAST_30_DAYS = "last30d"
PERIOD_CUSTOM = "custom"
DEFAULT_TIMEZONE = "Asia/Shanghai"

PERIOD_DAYS: dict[str, int] = {
    PERIOD_LAST_7_DAYS: 7,
    PERIOD_LAST_30_DAYS: 30,
}


@dataclass(frozen=True)
class PeriodQuery:
    """原始查询参数（未校验）。"""

    period: str = PERIOD_LAST_7_DAYS
    from_: str | None = None
    to: str | None = None
    timezone: str = DEFAULT_TIMEZONE


@dataclass(frozen=True)
class Period:
    """解析后的统计周期。`start` 含、`end` 不含，均为 UTC。"""

    start: datetime
    end: datetime
    timezone: ZoneInfo
    days: int

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


def resolve_period(query: PeriodQuery, now: datetime) -> Period:
    """把查询参数解析成具体区间；非法参数抛 `InvalidQueryError`。"""
    tz = _parse_timezone(query.timezone)

    if query.period in PERIOD_DAYS:
        days = PERIOD_DAYS[query.period]
        end_local = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)
        # 按本地日历日回退，而不是从 end_local 做绝对 24h×days 回退：
        # DST 时区下绝对回退的起点会落在相邻日期，区间变成 8/31 个自然日。
        start_local = datetime.combine(end_local.date() - timedelta(days=days), time.min, tzinfo=tz)
        return Period(
            start=start_local.astimezone(UTC),
            end=end_local.astimezone(UTC),
            timezone=tz,
            days=_local_day_count(start_local, end_local, tz),
        )

    if query.period == PERIOD_CUSTOM:
        if query.from_ is None or query.to is None:
            raise InvalidQueryError({"period": "custom 时 from 与 to 均为必填"})
        start = _parse_moment(query.from_, "from")
        end = _parse_moment(query.to, "to")
        if start >= end:
            raise InvalidQueryError({"from": "必须早于 to"})
        return Period(
            start=start,
            end=end,
            timezone=tz,
            days=_local_day_count(start, end, tz),
        )

    allowed = ", ".join(sorted([*PERIOD_DAYS, PERIOD_CUSTOM]))
    raise InvalidQueryError({"period": f"取值必须是 {allowed}"})


def _local_day_count(start: datetime, end: datetime, tz: ZoneInfo) -> int:
    """区间覆盖的自然日数（按查询时区）。`end` 不含，故取最后一个被包含的时刻定日。

    这样 `days` 与「学生 × 日」聚合的粒度一致：7 天周期恰好覆盖 7 个自然日。
    """
    last_included = end.astimezone(tz) - timedelta(microseconds=1)
    return (last_included.date() - start.astimezone(tz).date()).days + 1


def _parse_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise InvalidQueryError({"timezone": "必须是合法的 IANA 时区名"}) from error


def _parse_moment(value: str, field: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as error:
        raise InvalidQueryError({field: "必须是 ISO 8601 时间"}) from error
    if moment.tzinfo is None:
        raise InvalidQueryError({field: "必须带时区（UTC ISO 8601）"})
    return moment.astimezone(UTC)
