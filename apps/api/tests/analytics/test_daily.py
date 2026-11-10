"""daily.py 纯逻辑单测：日界切分与 session_inference_v1（无需数据库）。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domains.analytics.daily import infer_daily_seconds, key_for_event, local_metric_date

TZ = ZoneInfo("Asia/Shanghai")


def _ts(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 11, 3, hour, minute, second, tzinfo=TZ)


def test_metric_date_uses_local_calendar_day() -> None:
    """UTC 16:00+08:00 是上海次日 00:00：日界按本地日历，不按 UTC。"""
    utc_evening = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
    assert local_metric_date(utc_evening, TZ) == date(2026, 11, 3)


def test_key_for_event_carries_class_snapshot() -> None:
    key = key_for_event(
        student_user_id="user_a",
        course_id="course_1",
        class_id="class_1",
        occurred_at=_ts(9),
        tz=TZ,
    )
    assert key.student_user_id == "user_a"
    assert key.class_id == "class_1"
    assert key.metric_date == date(2026, 11, 3)


def test_single_event_counts_minimum() -> None:
    """单事件会话按最低 60 秒计（statistics-api.md 时长口径）。"""
    assert infer_daily_seconds([_ts(9)]) == 60


def test_gap_over_fifteen_minutes_splits_sessions() -> None:
    """相邻间隔 >15 分钟切成新会话：两段各按会话下限 60 秒，共 120（非交换，重算不追加）。"""
    events = [_ts(9, 0), _ts(9, 0, 4), _ts(9, 30)]
    assert infer_daily_seconds(events) == 120


def test_long_high_frequency_session_caps_at_3600() -> None:
    """每 10 分钟一条、连续 70 分钟 → 计 3600 秒（上限防挂机虚增）。"""
    base = _ts(9, 0)
    events = [base + timedelta(minutes=10 * i) for i in range(8)]
    assert infer_daily_seconds(events) == 3600


def test_out_of_order_input_is_sorted() -> None:
    """迟到事件重算场景：乱序输入与升序输入结果一致。"""
    shuffled = [_ts(10), _ts(9, 0), _ts(9, 0, 30)]
    ordered = [_ts(9, 0), _ts(9, 0, 30), _ts(10)]
    assert infer_daily_seconds(shuffled) == infer_daily_seconds(ordered)


def test_empty_input_is_none_not_zero() -> None:
    """无观测返回 None（unknown），不是 0。"""
    assert infer_daily_seconds([]) is None
