/**
 * 教师端类型：与 `packages/contracts/analytics/statistics-api.md`（PR #37）一一对应。
 *
 * 手写而非从 OpenAPI 生成：后端 FastAPI 的 schema 快照尚未纳入
 * `apps/web/src/generated/`（`docs/code-standards.md:12` 的目标），
 * 约定生成流程属于 M1 的脚手架任务，此处按契约逐字段对齐并标注依据。
 */

/** 由事件派生的数字：已知值或未知及原因。**不允许用 0 冒充未知**。 */
export type UnknownReason = 'no_events_in_period' | 'duration_source_unavailable'

export type KnownCount = {
  state: 'known'
  value: number
}

export type KnownDuration = {
  state: 'known'
  value: number
  /** 时长口径，如 `session_inference_v1`；页面须向教师显示，避免口径混淆。 */
  algorithm: string
}

export type UnknownNumber = {
  state: 'unknown'
  reason: UnknownReason
}

export type MetricNumber = KnownDuration | KnownCount | UnknownNumber

export type Period = {
  from: string
  to: string
  timezone: string
  days: number
}

export type Coverage = {
  studentCount: number
  studentsWithData: number
  studentsWithoutData: number
}

export type QuestionTypeWeakPoint = {
  key: string
  label: string | null
  errorRate: number
  sampleSize: number
  insufficientSample: boolean
}

export type ChapterWeakPoint = {
  key: string
  label: string | null
  mistakeCount: number
  resolvedCount: number
  sampleSize: number
  insufficientSample: boolean
}

export type StudentOverview = {
  userId: string
  displayName: string | null
  dataState: 'known' | 'unknown'
  durationSeconds: MetricNumber
  submissionCount: MetricNumber
  /** `null` 表示本周期无错题记录（已知事实），与 `dataState='unknown'` 不同。 */
  weakestChapter: ChapterWeakPoint | null
}

export type ClassOverview = {
  classId: string
  period: Period
  /** 消费位点：统计只覆盖到该时刻；`null` 表示尚未消费任何事件。 */
  dataThrough: string | null
  generatedAt: string
  summary: {
    totalDurationSeconds: MetricNumber
    activeStudentCount: MetricNumber
    submissionCount: MetricNumber
    coverage: Coverage
  }
  weakPoints: {
    byQuestionType: QuestionTypeWeakPoint[]
    byChapter: ChapterWeakPoint[]
  }
  students: StudentOverview[]
}

/** 示意数据的显式标记（`AGENTS.md:4`：Mock 必须明确标记）。 */
export type TeacherFixture<T> = T & { _fixture: true }
