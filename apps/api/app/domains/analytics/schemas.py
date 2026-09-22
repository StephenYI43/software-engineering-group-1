"""响应模型：与 `packages/contracts/analytics/statistics-api.md` 一一对应。

Python 侧用 snake_case，JSON 侧用 camelCase（`docs/code-standards.md:55`）。
`MetricNumber` 是判别联合：由事件派生的数字要么是已知值，要么是未知及其原因，
**不允许**用 0 冒充未知（`docs/tasks/m6.md:29` 验收）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel


def _utc_iso(value: datetime) -> str:
    """序列化为契约样例使用的 `Z` 结尾 UTC ISO 8601。"""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcIso = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str)]

UnknownReason = Literal["no_events_in_period", "duration_source_unavailable"]
NO_EVENTS_IN_PERIOD: UnknownReason = "no_events_in_period"
DURATION_SOURCE_UNAVAILABLE: UnknownReason = "duration_source_unavailable"


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class KnownNumber(_CamelModel):
    """已知的计数值（活跃人数、提交数）。"""

    state: Literal["known"] = "known"
    value: int


class KnownDuration(_CamelModel):
    """已知的时长值，必须带算法标识，避免不同口径的时长被混为一谈。"""

    state: Literal["known"] = "known"
    value: int
    algorithm: str


class UnknownNumber(_CamelModel):
    """未知值及其原因。"""

    state: Literal["unknown"] = "unknown"
    reason: UnknownReason


MetricNumber = KnownDuration | KnownNumber | UnknownNumber
"""由事件派生的数字的统一形状。"""


class PeriodResponse(_CamelModel):
    """`from` 是 Python 关键字，故字段名为 `period_from`，序列化输出 `from`。"""

    period_from: UtcIso = Field(serialization_alias="from")
    to: UtcIso
    timezone: str
    days: int


class Coverage(_CamelModel):
    student_count: int
    students_with_data: int
    students_without_data: int


class Summary(_CamelModel):
    total_duration_seconds: MetricNumber
    active_student_count: MetricNumber
    submission_count: MetricNumber
    coverage: Coverage


class QuestionTypeWeakPointResponse(_CamelModel):
    key: str
    label: str | None
    error_rate: float
    sample_size: int
    insufficient_sample: bool


class ChapterWeakPointResponse(_CamelModel):
    key: str
    label: str | None
    mistake_count: int
    resolved_count: int
    sample_size: int
    insufficient_sample: bool


class WeakPoints(_CamelModel):
    by_question_type: list[QuestionTypeWeakPointResponse]
    by_chapter: list[ChapterWeakPointResponse]


class StudentOverview(_CamelModel):
    user_id: str
    display_name: str | None
    data_state: Literal["known", "unknown"]
    duration_seconds: MetricNumber
    submission_count: MetricNumber
    weakest_chapter: ChapterWeakPointResponse | None


class StudentPage(_CamelModel):
    """`students` 列表的分页包装。"""

    page: int
    """页码，从 1 起；超出总页数时 `items` 为空。"""

    page_size: int
    """每页人数（1—200）。"""

    total: int
    """学生总行数（不受分页影响）。"""

    items: list[StudentOverview]


class Consumption(_CamelModel):
    """本域相对上游事件源的消费水位。"""

    data_state: Literal["complete", "partial", "unknown"]
    """`complete`：周期内可消费的事件已全部纳入；`partial`：游标落后于上游；
    `unknown`：上游不可得（未接入或水位读取失败）。"""

    upstream_watermark: UtcIso | None
    """上游已写入的最新事件位置；null 表示上游无事件或水位不可得。"""


class ClassOverview(_CamelModel):
    """`GET /api/v1/analytics/classes/{classId}/overview` 的响应。"""

    class_id: str
    course_id: str | None
    """班级关联的课程 ID（来自 M5 `classes.course_id`）；映射缺失时为 null。"""

    period: PeriodResponse
    data_through: UtcIso | None
    """本响应纳入的最新事件发生时间（限定查询周期），不是消费位点。"""

    generated_at: UtcIso
    consumption: Consumption
    summary: Summary
    weak_points: WeakPoints
    students: StudentPage
