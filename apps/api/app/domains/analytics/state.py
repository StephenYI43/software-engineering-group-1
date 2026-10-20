"""聚合状态：只由学习事件派生，可重放。

状态是 `(occurredAt, eventId)` 顺序下逐条应用事件的函数式结果，
因此「重置游标到更早位置并重放」与「正常消费」得到相同结果
（`packages/contracts/analytics/event-consumption.md`「推进规则」）。

幂等由两层保证：`processed_event_ids` 账本按 `eventId` 去重；
各指标自身的更新规则也是幂等的（提交按 `submissionId` 取首次、
判分取最新、错题按 `mistakeId` 去重）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime

from app.domains.analytics.cursor import Cursor
from app.domains.analytics.events import (
    EventType,
    LearningEvent,
    optional_bool,
    optional_str,
    required_str,
)


@dataclass
class SubmissionRecord:
    """一次作业提交（以 `submissionId` 为业务键）。

    `occurred_at` 取首次到达的时间，决定提交数归属哪个统计周期；
    `question_type` 记录题目类型——它属于题目属性，只有提交事件携带，
    判分事件不带（M5 契约），故必须独立于判分结果保存；
    `course_id` 记录事件归属的课程，同一学生跨班时按课程隔离，防止串班。
    """

    submission_id: str
    user_id: str
    occurred_at: datetime
    course_id: str | None = None
    question_type: str | None = None


@dataclass(frozen=True)
class Judgement:
    """一次判分结果（同一 `submissionId` 保留最新的一次）。"""

    submission_id: str
    user_id: str
    question_type: str | None
    occurred_at: datetime
    is_correct: bool
    from_graded_event: bool
    course_id: str | None = None


@dataclass
class MistakeRecord:
    """一道收录的错题；`resolved` 由 `mistake_resolved` 置位。"""

    mistake_id: str
    user_id: str
    chapter_id: str | None
    recorded_at: datetime
    resolved: bool = False
    course_id: str | None = None


@dataclass
class AnalyticsState:
    """聚合状态。只读侧（aggregation）不得修改本对象。"""

    cursor: Cursor | None = None
    processed_event_ids: set[str] = field(default_factory=set)
    submissions: dict[str, SubmissionRecord] = field(default_factory=dict)
    judgements: dict[str, Judgement] = field(default_factory=dict)
    mistakes: dict[str, MistakeRecord] = field(default_factory=dict)
    activity: dict[str, dict[str | None, list[datetime]]] = field(default_factory=dict)
    """`userId` → `courseId` → 事件时刻列表。

    按 `courseId` 二级分组后，跨班级查询只取本课程时刻，避免同一学生跨班时
    数据串班（statistics-api.md「数据隔离」）。`courseId` 为 None 的事件也登记，
    但读侧按具体课程查询时会天然排除（查询 key 是具体 str）。

    S1 保留逐事件时刻是为了在读取时按查询时区切「学生 × 日」并做会话推断；
    真实实现应在会话关闭时把结果落聚合表，而不是长期保留事件级明细
    （见 `statistics-api.md`「时长口径」的过渡说明）。
    """

    def clone(self) -> AnalyticsState:
        """深拷贝。消费方在副本上修改，失败时丢弃副本即可，不污染已保存状态。"""
        return copy.deepcopy(self)

    def is_processed(self, event_id: str) -> bool:
        return event_id in self.processed_event_ids

    def apply(self, event: LearningEvent) -> None:
        """应用一条事件。调用前须用 `is_processed` 过滤已处理事件。"""
        self.processed_event_ids.add(event.event_id)
        self.activity.setdefault(event.user_id, {}).setdefault(event.course_id, []).append(
            event.occurred_at
        )

        if event.event_type in (EventType.ASSIGNMENT_SUBMITTED, EventType.ASSIGNMENT_GRADED):
            self._apply_submission(event)
        elif event.event_type is EventType.MISTAKE_RECORDED:
            self._apply_mistake_recorded(event)
        elif event.event_type is EventType.MISTAKE_RESOLVED:
            self._apply_mistake_resolved(event)
        # 计划、提醒、章节浏览等事件 S1 只计入活跃度，不参与当前指标。

    def _apply_submission(self, event: LearningEvent) -> None:
        submission_id = required_str(event.payload, "submissionId", event)
        question_type = optional_str(event.payload, "questionType", event)

        record = self.submissions.get(submission_id)
        if record is None:
            # 批次按 (occurredAt, eventId) 升序处理（消费契约硬要求），
            # 首次到达即最早一次；`questionType` 由提交事件携带（M5 契约），
            # 故创建时一并登记，重放时结果稳定不变。
            record = SubmissionRecord(
                submission_id=submission_id,
                user_id=event.user_id,
                occurred_at=event.occurred_at,
                course_id=event.course_id,
                question_type=question_type,
            )
            self.submissions[submission_id] = record

        is_correct = optional_bool(event.payload, "isCorrect", event)
        if is_correct is None:
            return  # 主观题未判分：不计入对错统计（未判分不等于错误）

        from_graded_event = event.event_type is EventType.ASSIGNMENT_GRADED
        current = self.judgements.get(submission_id)
        if current is not None and (event.occurred_at, from_graded_event) <= (
            current.occurred_at,
            current.from_graded_event,
        ):
            return  # 更晚的判分胜出；同一时刻以 graded 事件为准

        self.judgements[submission_id] = Judgement(
            submission_id=submission_id,
            user_id=event.user_id,
            # 判分事件不带题型，回落到该提交已登记的题型，避免题型维度丢成 unknown。
            question_type=question_type if question_type is not None else record.question_type,
            occurred_at=event.occurred_at,
            is_correct=is_correct,
            from_graded_event=from_graded_event,
            course_id=event.course_id,
        )

    def _apply_mistake_recorded(self, event: LearningEvent) -> None:
        mistake_id = required_str(event.payload, "mistakeId", event)
        if mistake_id in self.mistakes:
            return  # 契约规定仅首次收录发布事件；重复到达时不覆盖已有状态
        self.mistakes[mistake_id] = MistakeRecord(
            mistake_id=mistake_id,
            user_id=event.user_id,
            chapter_id=optional_str(event.payload, "chapterId", event),
            recorded_at=event.occurred_at,
            course_id=event.course_id,
        )

    def _apply_mistake_resolved(self, event: LearningEvent) -> None:
        mistake_id = required_str(event.payload, "mistakeId", event)
        record = self.mistakes.get(mistake_id)
        if record is None:
            return  # 未见对应收录事件时忽略，不凭空造出错题
        record.resolved = True
