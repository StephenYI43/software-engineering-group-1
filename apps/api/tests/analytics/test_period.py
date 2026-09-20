"""统计周期解析：区间、日界时区与参数校验。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domains.analytics.errors import InvalidQueryError
from app.domains.analytics.period import PeriodQuery, resolve_period


def test_last_7_days_matches_contract_sample(request_time: datetime) -> None:
    period = resolve_period(PeriodQuery(period="last7d"), request_time)

    assert period.start == datetime(2026, 9, 9, 16, 0, tzinfo=UTC)
    assert period.end == datetime(2026, 9, 16, 16, 0, tzinfo=UTC)
    assert period.days == 7
    assert period.timezone == ZoneInfo("Asia/Shanghai")


def test_last_30_days_spans_30_local_days(request_time: datetime) -> None:
    period = resolve_period(PeriodQuery(period="last30d"), request_time)

    assert period.days == 30
    assert period.end - period.start == timedelta(days=30)


def test_range_is_left_closed_right_open(request_time: datetime) -> None:
    period = resolve_period(PeriodQuery(period="last7d"), request_time)

    assert period.contains(period.start)
    assert not period.contains(period.end)


def test_timezone_changes_day_boundary(request_time: datetime) -> None:
    shanghai = resolve_period(PeriodQuery(period="last7d"), request_time)
    utc = resolve_period(PeriodQuery(period="last7d", timezone="UTC"), request_time)

    assert shanghai.end == datetime(2026, 9, 16, 16, 0, tzinfo=UTC)
    assert utc.end == datetime(2026, 9, 17, 0, 0, tzinfo=UTC)


def test_custom_period_uses_given_instants(request_time: datetime) -> None:
    query = PeriodQuery(
        period="custom",
        from_="2026-09-15T00:00:00Z",
        to="2026-09-17T00:00:00Z",
    )

    period = resolve_period(query, request_time)

    assert period.start == datetime(2026, 9, 15, 0, 0, tzinfo=UTC)
    assert period.end == datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
    assert period.days == 3


def test_custom_period_of_one_local_day_reports_at_least_one_day(request_time: datetime) -> None:
    query = PeriodQuery(
        period="custom",
        from_="2026-09-16T00:00:00Z",
        to="2026-09-16T08:00:00Z",
    )

    assert resolve_period(query, request_time).days == 1


def test_rejects_unknown_period_value(request_time: datetime) -> None:
    with pytest.raises(InvalidQueryError) as error:
        resolve_period(PeriodQuery(period="lastYear"), request_time)

    assert error.value.status_code == 422
    assert "period" in error.value.details


def test_rejects_custom_period_without_bounds(request_time: datetime) -> None:
    with pytest.raises(InvalidQueryError) as error:
        resolve_period(PeriodQuery(period="custom"), request_time)

    assert "from 与 to 均为必填" in error.value.details["period"]


def test_rejects_custom_period_without_to(request_time: datetime) -> None:
    query = PeriodQuery(period="custom", from_="2026-09-15T00:00:00Z")

    with pytest.raises(InvalidQueryError):
        resolve_period(query, request_time)


def test_rejects_reversed_custom_range(request_time: datetime) -> None:
    query = PeriodQuery(
        period="custom",
        from_="2026-09-17T00:00:00Z",
        to="2026-09-15T00:00:00Z",
    )

    with pytest.raises(InvalidQueryError) as error:
        resolve_period(query, request_time)

    assert "必须早于" in error.value.details["from"]


def test_rejects_invalid_timezone(request_time: datetime) -> None:
    with pytest.raises(InvalidQueryError) as error:
        resolve_period(PeriodQuery(timezone="Mars/Olympus"), request_time)

    assert "timezone" in error.value.details


def test_rejects_unparsable_custom_bound(request_time: datetime) -> None:
    query = PeriodQuery(period="custom", from_="yesterday", to="2026-09-17T00:00:00Z")

    with pytest.raises(InvalidQueryError) as error:
        resolve_period(query, request_time)

    assert "from" in error.value.details


def test_rejects_naive_custom_bound(request_time: datetime) -> None:
    query = PeriodQuery(period="custom", from_="2026-09-15T00:00:00", to="2026-09-17T00:00:00Z")

    with pytest.raises(InvalidQueryError) as error:
        resolve_period(query, request_time)

    assert "必须带时区" in error.value.details["from"]
