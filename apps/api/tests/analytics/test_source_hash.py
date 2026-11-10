"""learning-feed-sha256-v1 固定合成向量与单字段变更反例（#79 decisions.md 2026-11-03）。

金标值由独立脚本按规格手工拼装 canonical JSON 计算得出，非被测实现自证。
纯单元测试：不需要数据库。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.domains.analytics.pg_consumer import SOURCE_HASH_PROTOCOL, _source_hash

GOLDEN = "3903e04529fc7a10326e2740153396d0e63fdf85131dce32429944493d12744e"
GOLDEN_RECORDED_VARIANT = "180f230ea4f405fd6f7426c93420e8d1f96d401744ccbae74504fb3cf6fefce4"
GOLDEN_CLASS_VARIANT = "9fbf1a02ac14c8dc61157b6646472ecd62cf2c4b2ca6eb735e7b970aff430532"

OCCURRED_UTC = datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=UTC)


def _row(**overrides: Any) -> dict[str, Any]:
    """固定合成向量的 feed 行（与金标脚本字段一一对应）。"""
    base: dict[str, Any] = {
        "id": "event_3333",
        "event_type": "chapter_viewed",
        "user_id": "user_5555",
        "course_id": "course_2222",
        "class_id": "class_1111",
        "occurred_at": OCCURRED_UTC,
        "recorded_at": None,
        "trace_id": "req_4444",
        "schema_version": "1.0",
        "payload": {"attempts": 2, "chapterId": "chapter_1"},
    }
    base.update(overrides)
    return base


def test_protocol_name_frozen() -> None:
    """协议名与 #79 decisions.md 冻结名一致。"""
    assert SOURCE_HASH_PROTOCOL == "learning-feed-sha256-v1"


def test_fixed_synthetic_vector() -> None:
    """固定合成向量：金标由独立脚本按规格手工拼装计算（非实现自证）。"""
    assert _source_hash(_row()) == GOLDEN


def test_class_id_single_field_change_detected() -> None:
    """单字段反例——class 变更（转班/错归班）必须改变摘要。"""
    assert _source_hash(_row(class_id="class_9999")) == GOLDEN_CLASS_VARIANT
    assert _source_hash(_row(class_id="class_9999")) != GOLDEN


def test_recorded_at_included() -> None:
    """单字段反例——recorded_at 纳入摘要，None 与具体时刻不同。"""
    variant = _row(recorded_at=datetime(2026, 1, 2, 4, 0, 0, tzinfo=UTC))
    assert _source_hash(variant) == GOLDEN_RECORDED_VARIANT
    assert _source_hash(variant) != GOLDEN


def test_timezone_representation_invariant() -> None:
    """等价时刻的时区表示（+08:00 vs UTC）摘要一致：UTC 规范化。"""
    tz8 = timezone(timedelta(hours=8))
    shifted = _row(occurred_at=datetime(2026, 1, 2, 11, 4, 5, 6, tzinfo=tz8))
    assert _source_hash(shifted) == _source_hash(_row())


def test_naive_timestamp_treated_as_utc() -> None:
    """naive 时间按 UTC 规范化（timestamptz 正常返回 aware，此为防御口径）。"""
    naive = _row(occurred_at=OCCURRED_UTC.replace(tzinfo=None))
    assert _source_hash(naive) == _source_hash(_row())


def test_null_fields_included() -> None:
    """含 NULL 的行参与摘要；course/class 置 NULL 改变摘要。"""
    assert _source_hash(_row(course_id=None, class_id=None)) != GOLDEN


def test_payload_integer_type_preserved() -> None:
    """整数保持整数：字符串化数字改变摘要（不做 default=str 兜底）。"""
    assert _source_hash(_row(payload={"attempts": "2", "chapterId": "chapter_1"})) != GOLDEN
