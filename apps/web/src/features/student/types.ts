/**
 * 契约类型。字段名与结构严格对应 packages/contracts/ 下的契约文件，
 * 不自行增删字段——契约是唯一来源（docs/code-standards.md:69）。
 */

/* ---------------------------------------------------------------- tutoring */

/** 教学阶段。由服务端状态机计算，客户端**不得**自行推进（tutoring-response.md）。 */
export type TutoringStage = 'thought' | 'hint' | 'step' | 'summary'

/** 引用。documentTitle 是不可信输入，展示前需净化。 */
export type Citation = {
  citationId: string
  documentId: string
  documentTitle: string
  /** 1 基，必须 ≥ 1。 */
  pageNumber: number
  snippet: string
}

/** 一次答疑回答。不变量见 tutoring-response.md 末节。 */
export type TutoringResponse = {
  turnId: string
  sessionId: string
  stage: TutoringStage
  content: string
  /** 无依据时为空数组，**不得为 null**。 */
  citations: Citation[]
  /** `hasEvidence === false` 与 `citations` 为空数组互为充要条件。 */
  hasEvidence: boolean
  /** 最多 3 条，每条最多 200 字符。 */
  followUps: string[]
  /**
   * 数字人情绪。取值集合由 M4 冻结中，当前契约里是占位值。
   *
   * 这里刻意用 `string` 而不是占位值的联合类型：联合类型会**拒绝** M4 冻结后的
   * 真实取值，是「看起来有类型安全、实际是错的」。渲染层对未知取值走默认分支。
   * TODO: M4 冻结 emotion/action 枚举后改为联合类型，并同步 packages/contracts。
   */
  emotion: string
  action: string
  /** 运行时来源标记：该轮是否由 MockModelClient 生成。不是「这份数据是假数据」的意思。 */
  isMock: boolean
  promptVersion: string
  createdAt: string
}

/* ----------------------------------------------------------------- courses */

/** 学科。未知取值回退显示原值，不报错不隐藏。 */
export type Course = {
  id: string
  title: string
  description: string | null
  subject: string
  coverImageUrl: string | null
  teacherId: string
  teacherName: string | null
  studentCount: number | null
  chapterCount: number | null
  createdAt: string
  updatedAt: string
}

export type Chapter = {
  id: string
  courseId: string
  title: string
  /** 从 1 开始，同课程内唯一。前端按此升序展示。 */
  order: number
  description: string | null
  documentId: string | null
  createdAt: string
  updatedAt: string
}

/** 常规列表分页结构（docs/code-standards.md:71）。items 不得为 null。 */
export type Paginated<T> = {
  items: T[]
  total: number
  page: number
  pageSize: number
}

/* ---------------------------------------------------------------- platform */

/** 统一错误结构（docs/code-standards.md:73-80）。 */
export type ApiErrorBody = {
  code: string
  message: string
  requestId: string
  details: Record<string, unknown>
}
