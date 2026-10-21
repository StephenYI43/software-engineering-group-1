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

/** 消费完整度声明：页面不得把 `partial` / `unknown` 当作完整统计展示。 */
export type Consumption = {
  dataState: 'complete' | 'partial' | 'unknown'
  /** 上游事件源已知的最新事件位置；null 表示上游尚无事件或水位不可得。 */
  upstreamWatermark: string | null
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

/** 学生明细分页信封（契约修订：students 不再是全量数组）。 */
export type StudentPage = {
  page: number
  pageSize: number
  total: number
  items: StudentOverview[]
}

export type ClassOverview = {
  classId: string
  /** `classId` 关联的课程 ID；页面可经 M5 章节接口解析章节标题，映射缺失时为 null。 */
  courseId: string | null
  period: Period
  /** 本响应纳入的最新事件发生时间（限定查询周期）；不是可恢复的消费位点。 */
  dataThrough: string | null
  consumption: Consumption
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
  students: StudentPage
}

/** 示意数据的显式标记（`AGENTS.md:4`：Mock 必须明确标记）。 */
export type TeacherFixture<T> = T & { _fixture: true }
