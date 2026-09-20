import { ApiError } from '../api/http-client'
import type { Chapter, Course, Paginated, TutoringResponse } from '../types'
import { ALL_COURSES, CHAPTERS_BY_COURSE, COURSES_PAGE } from './courses-fixtures'
import {
  noEvidence,
  summaryAfterAttempt,
  thoughtWithCitation,
  type Fixture,
} from './tutoring-fixtures'

/**
 * Mock 层：S0 阶段没有后端可联调，所有数据来自这里的示意数据。
 *
 * **每个返回值都带 `_fixture: true`**，界面据此渲染「示意数据」标识。
 * 这不是可选的装饰：`AGENTS.md:8` 要求 Mock 必须明确标记、不能当生产完成证据。
 *
 * ## 为什么场景是「传入参数」而不是「读 URL」
 *
 * 这里刻意**不读 `window.location`**。URL 的真相来源是应用的 router，不是 `window`：
 * 在测试里用 `createMemoryRouter` 时，它有自己的 history，不会改动 `window.location`，
 * 于是「按 URL 切换场景」在测试中会静默失效——所有用例都跑在默认场景上，测试全绿却
 * 什么都没验证。让调用方把 URL 传进来，既消除了这个隐患，也让场景成为显式输入。
 */

/**
 * 响应场景，通过 URL 查询参数 `?mock=` 切换，便于演示与验证错误态：
 *
 * - 缺省 / `normal` —— 正常返回
 * - `empty` —— 返回空列表，验证空态
 * - `error` —— 返回**符合契约结构**的 404 错误体
 * - `error-raw` —— 返回**不符合契约结构**的错误体（模拟代理/网关/HTML 错误页），
 *   用于验证 HTTP 客户端的兜底分支
 * - `slow` —— 拉长响应时间，验证加载态
 */
export type MockScenario = 'normal' | 'empty' | 'error' | 'error-raw' | 'slow'

const SCENARIOS: readonly MockScenario[] = ['normal', 'empty', 'error', 'error-raw', 'slow']

/** 从 URL 查询串解析场景。传入 `useLocation().search`。 */
export function parseScenario(search: string): MockScenario {
  const raw = new URLSearchParams(search).get('mock')
  return SCENARIOS.find((candidate) => candidate === raw) ?? 'normal'
}

/** 演示哪一轮回答。传入 `useLocation().search`。 */
export type TutoringTurnKind = 'thought' | 'summary' | 'noEvidence'

export function parseTutoringTurnKind(search: string): TutoringTurnKind {
  const raw = new URLSearchParams(search).get('turn')
  if (raw === 'summary' || raw === 'noEvidence') return raw
  return 'thought'
}

const DELAY_MS: Record<MockScenario, number> = {
  normal: 120,
  empty: 120,
  error: 120,
  'error-raw': 120,
  slow: 2500,
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 符合契约结构的错误（`code` / `message` / `requestId` / `details`）。 */
function contractShapedError(): ApiError {
  return new ApiError({
    kind: 'notFound',
    status: 404,
    message: '未找到课程',
    requestId: 'req_0123456789ab4def8123456789abcdef',
    code: 'COURSE_NOT_FOUND',
  })
}

/**
 * 不符合契约结构的错误：模拟代理、网关返回的 HTML 错误页。
 *
 * HTTP 客户端此时应**不解析内部结构**、使用兜底文案、**不伪造 requestId**。
 */
function nonContractShapedError(): ApiError {
  return new ApiError({
    kind: 'server',
    status: 502,
    message: '服务暂时不可用，请稍后重试',
    requestId: undefined,
    code: undefined,
  })
}

/**
 * 按场景模拟延迟并抛出错误场景。返回即表示应当继续正常返回数据。
 *
 * 这不是「错误处理」——错误场景就是要让调用方抛错，从而走到错误渲染路径。
 */
async function applyScenario(scenario: MockScenario): Promise<void> {
  await delay(DELAY_MS[scenario])
  if (scenario === 'error') throw contractShapedError()
  if (scenario === 'error-raw') throw nonContractShapedError()
}

/* ------------------------------------------------------------------ 课程页 */

export async function fetchCourses(scenario: MockScenario): Promise<Fixture<Paginated<Course>>> {
  await applyScenario(scenario)
  if (scenario === 'empty') {
    return { ...COURSES_PAGE, items: [], total: 0 }
  }
  return COURSES_PAGE
}

export async function fetchCourse(
  courseId: string,
  scenario: MockScenario,
): Promise<Fixture<Course>> {
  await applyScenario(scenario)
  const found = ALL_COURSES.find((course) => course.id === courseId)
  if (found === undefined) {
    throw new ApiError({
      kind: 'notFound',
      status: 404,
      message: '未找到',
      requestId: 'req_0123456789ab4def8123456789abcdef',
      code: 'COURSE_NOT_FOUND',
    })
  }
  return found
}

export async function fetchChapters(
  courseId: string,
  scenario: MockScenario,
): Promise<Fixture<Paginated<Chapter>>> {
  await applyScenario(scenario)
  const items = CHAPTERS_BY_COURSE[courseId] ?? []
  return {
    _fixture: true,
    // 契约要求按 order 升序展示。
    items: [...items].sort((a, b) => a.order - b.order),
    total: items.length,
    page: 1,
    pageSize: 50,
  }
}

/* -------------------------------------------------------------------- 答疑页 */

const TUTORING_TURNS: Record<TutoringTurnKind, Fixture<TutoringResponse>> = {
  thought: thoughtWithCitation,
  summary: summaryAfterAttempt,
  noEvidence,
}

/**
 * 取一轮答疑回答。
 *
 * S0 不做流式——SSE 解析与增量渲染留给下一个子 Issue（本 Issue 声明的范围是
 * 「路由骨架」，不含流式交互）。这里返回完整的一轮回答，用于验证契约字段的渲染。
 */
export async function fetchTutoringTurn(
  kind: TutoringTurnKind,
  scenario: MockScenario,
): Promise<Fixture<TutoringResponse>> {
  await applyScenario(scenario)
  return TUTORING_TURNS[kind]
}
