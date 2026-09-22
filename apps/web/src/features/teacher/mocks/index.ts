import type { ClassOverview, TeacherFixture } from '../types'

/**
 * 教师端示意数据（M6）。
 *
 * 数据来源是 M6 自己的契约样例，不是随手编的数字：
 * `packages/contracts/analytics/samples/01-class-overview-ok.json`（含已知、未知、
 * 样本不足三种情形）与 `02-class-overview-no-data.json`（全班无数据）。
 * 两者的数字都可由 `docs/prototypes/samples/learning-events-synthetic.jsonl`
 * 的 11 条合成事件推导，因此「样例事件 → 页面显示」这条链路是可核对、可复现的。
 *
 * 本模块**只在开发环境被加载**：调用方用 `import.meta.env.DEV` 守卫动态 import，
 * 生产构建会把这段与数据一起剥离，不会让示意数据进入产物
 * （对比 `features/student` 当前的静态 import，那一点已在 PR #36 评审中提出）。
 *
 * 演示场景通过查询参数 `?mock=` 切换，与 M2 学生端保持一致的用法：
 * - 缺省 / `normal`：契约样例 01（含 unknown 学生与样本不足条目）
 * - `no-data`：契约样例 02（全班无数据）
 * - `error`：符合契约结构的错误体（404 `CLASS_NOT_FOUND`）
 */

export type MockScenario = 'normal' | 'no-data' | 'error'

const SCENARIOS: readonly MockScenario[] = ['normal', 'no-data', 'error']

/** 从 URL 查询串解析场景。真相来源是 router，故由调用方传入 `useLocation().search`。 */
export function parseMockScenario(search: string): MockScenario {
  const raw = new URLSearchParams(search).get('mock')
  return SCENARIOS.find((candidate) => candidate === raw) ?? 'normal'
}

/** 契约样例 01：混合情形（2 名有数据 + 1 名无事件 + 样本不足标记）。 */
const OVERVIEW_WITH_DATA: ClassOverview = {
  classId: 'class_mock_c01',
  courseId: 'course_mock_c01',
  period: {
    from: '2026-09-09T16:00:00Z',
    to: '2026-09-16T16:00:00Z',
    timezone: 'Asia/Shanghai',
    days: 7,
  },
  dataThrough: '2026-09-16T09:20:00Z',
  consumption: { dataState: 'complete', upstreamWatermark: '2026-09-16T09:20:00Z' },
  generatedAt: '2026-09-17T01:00:00Z',
  summary: {
    totalDurationSeconds: { state: 'known', value: 3540, algorithm: 'session_inference_v1' },
    activeStudentCount: { state: 'known', value: 2 },
    submissionCount: { state: 'known', value: 3 },
    coverage: { studentCount: 3, studentsWithData: 2, studentsWithoutData: 1 },
  },
  weakPoints: {
    byQuestionType: [
      {
        key: 'single_choice',
        label: null,
        errorRate: 0.5,
        sampleSize: 2,
        insufficientSample: true,
      },
      { key: 'short_answer', label: null, errorRate: 1, sampleSize: 1, insufficientSample: true },
    ],
    byChapter: [
      {
        key: 'chapter_mock_c02',
        label: null,
        mistakeCount: 1,
        resolvedCount: 1,
        sampleSize: 1,
        insufficientSample: true,
      },
    ],
  },
  students: {
    page: 1,
    pageSize: 50,
    total: 3,
    items: [
      {
        userId: 'user_mock_s01',
        displayName: '合成学生 01',
        dataState: 'known',
        durationSeconds: { state: 'known', value: 1680, algorithm: 'session_inference_v1' },
        submissionCount: { state: 'known', value: 2 },
        weakestChapter: {
          key: 'chapter_mock_c02',
          label: null,
          mistakeCount: 1,
          resolvedCount: 1,
          sampleSize: 1,
          insufficientSample: true,
        },
      },
      {
        userId: 'user_mock_s02',
        displayName: '合成学生 02',
        dataState: 'known',
        durationSeconds: { state: 'known', value: 1860, algorithm: 'session_inference_v1' },
        submissionCount: { state: 'known', value: 1 },
        weakestChapter: null,
      },
      {
        userId: 'user_mock_s03',
        displayName: '合成学生 03',
        dataState: 'unknown',
        durationSeconds: { state: 'unknown', reason: 'no_events_in_period' },
        // 无事件学生的提交数是已知 0（契约修订：无活动 ≠ 未知）
        submissionCount: { state: 'known', value: 0 },
        weakestChapter: null,
      },
    ],
  },
}

/** 契约样例 02：全班无活动（计数为已知 0，时长因缺乏观测为未知）。 */
const OVERVIEW_WITHOUT_DATA: ClassOverview = {
  classId: 'class_mock_c01',
  courseId: 'course_mock_c01',
  period: {
    from: '2026-09-09T16:00:00Z',
    to: '2026-09-16T16:00:00Z',
    timezone: 'Asia/Shanghai',
    days: 7,
  },
  dataThrough: null,
  consumption: { dataState: 'complete', upstreamWatermark: null },
  generatedAt: '2026-09-17T01:00:00Z',
  summary: {
    totalDurationSeconds: { state: 'unknown', reason: 'no_events_in_period' },
    activeStudentCount: { state: 'known', value: 0 },
    submissionCount: { state: 'known', value: 0 },
    coverage: { studentCount: 3, studentsWithData: 0, studentsWithoutData: 3 },
  },
  weakPoints: {
    byQuestionType: [],
    byChapter: [],
  },
  students: {
    page: 1,
    pageSize: 50,
    total: 3,
    items: OVERVIEW_WITH_DATA.students.items.map((student) => ({
      ...student,
      dataState: 'unknown' as const,
      durationSeconds: { state: 'unknown' as const, reason: 'no_events_in_period' as const },
      submissionCount: { state: 'known' as const, value: 0 },
      weakestChapter: null,
    })),
  },
}

/** 契约错误体（`{ code, message, requestId, details }`，code-standards.md:73）。 */
export const CONTRACT_ERROR_BODY = {
  code: 'CLASS_NOT_FOUND',
  message: '未找到班级',
  requestId: 'req_mock_9001',
  details: {},
} as const

/** 供调用方在 `error` 场景抛出，保持错误形状与真实响应一致。 */
export class MockContractError extends Error {
  readonly body: typeof CONTRACT_ERROR_BODY

  constructor() {
    super(CONTRACT_ERROR_BODY.message)
    this.name = 'MockContractError'
    this.body = CONTRACT_ERROR_BODY
  }
}

export function fetchClassOverview(scenario: MockScenario): Promise<TeacherFixture<ClassOverview>> {
  if (scenario === 'error') {
    return Promise.reject(new MockContractError())
  }
  if (scenario === 'no-data') {
    return Promise.resolve({ ...OVERVIEW_WITHOUT_DATA, _fixture: true })
  }
  return Promise.resolve({ ...OVERVIEW_WITH_DATA, _fixture: true })
}
